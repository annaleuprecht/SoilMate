# stages/shear_stage.py
from .base_stage import BaseStage
import time

class ShearStage(BaseStage):
    def __init__(self, data, lf, cell_pc, back_pc, serial_pad, log):
        super().__init__(data, lf, cell_pc, back_pc, serial_pad, log)
        self._stop_requested = False
        self._cur_velocity = 0.0
        self._cell_kpa = 0.0

    def stop(self):
        self._stop_requested = True
        super().stop()  # stop flag + device halts

    def pause(self):
        self._paused = True
        try:
            # Command an explicit stop first, if the driver supports it
            if self.lf:
                stopped = False
                for name in ("stop_motion", "send_stop", "stop"):
                    fn = getattr(self.lf, name, None)
                    if callable(fn):
                        try:
                            fn()
                            stopped = True
                            break
                        except Exception:
                            pass

                # Hard fallback: force velocity = 0 so the frame actually halts
                vsetter = getattr(self.lf, "send_velocity", None)
                if callable(vsetter):
                    try:
                        vsetter(0.0)
                        stopped = True
                    except Exception:
                        pass

            self.log("[Shear] Paused (LF commanded to stop; cell pressure held).")
        except Exception:
            pass


    def resume(self):
        self._paused = False
        try:
            # resume at last velocity; cell pressure stays constant on device
            if self.lf and hasattr(self.lf, "send_velocity"):
                self.lf.send_velocity(self._cur_velocity)
            self.log(f"[Shear] Resumed (velocity {self._cur_velocity} mm/min).")
        except Exception:
            pass

    def run(self):
        self._stop_requested = False
        self.log("[Shear] Starting shear stage…")

        # Inputs
        req_v = float(getattr(self.data, "axial_velocity", 0) or 0.0)
        target_delta_kN = float(getattr(self.data, "safety_load_kN", 0) or 0.0)  # interpreted as Δload target

        # Connections required for shear
        if not self.lf:
            self.log("[✗] Load frame not connected."); return
        if not self.cell_pc:
            self.log("[✗] Cell pressure controller not connected."); return
        if not self.serial_pad:
            self.log("[✗] SerialPad not connected — cannot measure Δload."); return

        try:
            # --- 1) Determine the cell pressure to HOLD (live read, with safe fallback) ---
            cell_now, _ = self._read_pressures_kpa()
            hold_kpa = float(cell_now if cell_now is not None else getattr(self.data, "cell_pressure", 0.0) or 0.0)
            if hold_kpa <= 0.0:
                self.log("[✗] Aborting shear: no valid cell pressure to hold."); return
            self._cell_kpa = hold_kpa

            # Try to set/hold the cell pressure
            ok = False
            try:
                if self._is_ready(self.cell_pc) and hasattr(self.cell_pc, "send_pressure"):
                    self.cell_pc.send_pressure(hold_kpa); ok = True
            except Exception:
                ok = False
            if not ok:
                ok = self._ramp_pressure(self.cell_pc, hold_kpa, rate_kpa_per_min=9999.0)
            if not ok:
                self.log("[✗] Failed to command cell controller to hold pressure."); return

            self.log(f"[Shear] Holding cell pressure: {hold_kpa:.3f} kPa (back pressure may change)")

            # --- 2) Velocity clamp / start motion ---
            def _clamp(v, lo, hi): return max(lo, min(hi, v))
            def _sign(v): return 1.0 if v >= 0 else -1.0
            v = _clamp(req_v, -1.0, 1.0)
            if abs(v) < 0.05 and v != 0.0:
                v = 0.05 * _sign(v)
            if req_v != v:
                self.log(f"[Shear] Requested {req_v:.3f} mm/min → clamped to {v:.3f} mm/min")
            self._cur_velocity = v

            if hasattr(self.lf, "send_velocity"):
                self.lf.send_velocity(self._cur_velocity)
            self.log(f"[Shear] Moving at {self._cur_velocity:.3f} mm/min until Δload = {target_delta_kN:+.3f} kN")

            # --- 3) Δload tracking setup ---
            sign = 1.0 if target_delta_kN >= 0 else -1.0
            targetP = abs(target_delta_kN)
            creepP  = 0.50 * targetP
            creep_speed = 0.20 * _sign(self._cur_velocity)
            poll_dt = 0.05
            noise_deadband = 0.005

            # Baseline load over short window
            def read_kn():
                try:
                    ch = self.serial_pad.read_channels()
                    return ch[0] if (ch and ch[0] is not None) else 0.0
                except Exception:
                    return 0.0

            samples = []
            t0 = time.time()
            while time.time() - t0 < 0.20 and not (self._stop_requested or self._stop_flag):
                self._pause_barrier()
                samples.append(read_kn())
                time.sleep(0.02)
            baseline = sum(samples) / max(1, len(samples))
            self.log(f"[Shear] Baseline load: {baseline:.3f} kN")

            # EMA smoother + keep-alive for cell hold
            ema = baseline
            alpha = 0.3
            hold_tol_kpa = 0.5           # allowable drift
            keepalive_sec = 1.5
            last_keep = time.time()

            # --- 4) Main loop ---
            while not (self._stop_requested or self._stop_flag):
                self._pause_barrier()
                if self._stop_requested or self._stop_flag:
                    break

                # Keep cell pressure held (periodic re-apply if it drifts)
                now = time.time()
                if now - last_keep >= keepalive_sec:
                    cell_now, _ = self._read_pressures_kpa()
                    if cell_now is not None and abs(cell_now - hold_kpa) > hold_tol_kpa:
                        # re-assert setpoint
                        try:
                            if hasattr(self.cell_pc, "send_pressure"):
                                self.cell_pc.send_pressure(hold_kpa)
                            else:
                                self._ramp_pressure(self.cell_pc, hold_kpa, rate_kpa_per_min=9999.0)
                            self.log(f"[Shear] Re-holding cell pressure {cell_now:.2f}→{hold_kpa:.2f} kPa")
                        except Exception:
                            pass
                    last_keep = now

                # Load & Δ
                load_kN = read_kn()
                ema = alpha * load_kN + (1 - alpha) * ema
                delta = ema - baseline
                if abs(delta) < noise_deadband:
                    delta = 0.0

                progress = sign * delta
                self.log(f"[Shear] Load {ema:.3f} kN | Δ {delta:+.3f} kN (progress {progress:.3f}/{targetP:.3f})")

                # Stop when Δ achieved
                if progress >= targetP:
                    for name in ("stop_motion", "send_stop", "stop"):
                        if hasattr(self.lf, name):
                            try:
                                getattr(self.lf, name)(); break
                            except Exception:
                                pass
                    self.log(f"[✓] Δload target reached: {delta:+.3f} kN (target {target_delta_kN:+.3f} kN)")
                    break

                # Creep near target
                if progress >= creepP and abs(self._cur_velocity) > abs(creep_speed):
                    if hasattr(self.lf, "send_velocity"):
                        try:
                            self.lf.send_velocity(creep_speed)
                            self._cur_velocity = creep_speed
                            self.log(f"[Shear] Near target Δ. Slowing to {abs(creep_speed):.2f} mm/min")
                        except Exception:
                            pass

                time.sleep(poll_dt)

        except Exception as e:
            self.log(f"[!] Shear stage error: {e}")
        finally:
            # Always stop axial motion when the stage ends
            try:
                if hasattr(self.lf, "stop_motion"):
                    self.lf.stop_motion()
                self._cur_velocity = 0.0
                self.log("[Shear] Done (LF stopped).")
            except Exception:
                pass


    def _read_pressures_kpa(self):
        """Return (cell_kpa, back_kpa) from controllers; fall back to self.data or 0.0."""
        def _read_one(pc, fallback):
            if not pc:
                return float(fallback)
            # Try common call patterns
            for name in ("read_pressure_kpa", "get_pressure_kpa", "read_pressure", "get_pressure"):
                fn = getattr(pc, name, None)
                if callable(fn):
                    try:
                        val = fn()
                        return float(val)
                    except Exception:
                        pass
            # Try cached attributes updated by polling threads
            for attr in ("last_pressure_kpa", "pressure_kpa", "current_pressure_kpa"):
                if hasattr(pc, attr):
                    try:
                        return float(getattr(pc, attr))
                    except Exception:
                        pass
            return float(fallback)

        cell_fallback = float(getattr(self.data, "current_cell_pressure", 0) or 0.0)
        back_fallback = float(getattr(self.data, "current_back_pressure", 0) or 0.0)
        return _read_one(self.cell_pc, cell_fallback), _read_one(self.back_pc, back_fallback)

