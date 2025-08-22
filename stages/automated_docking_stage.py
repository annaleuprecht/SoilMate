# stages/automated_docking_stage.py
from .base_stage import BaseStage
import time

class AutomatedDockingStage(BaseStage):
    def __init__(self, data, lf, cell_pc, back_pc, serial_pad, log):
        super().__init__(data, lf, cell_pc, back_pc, serial_pad, log)
        self._stop_requested = False
        self._cur_velocity = 0.0

    def stop(self):
        self._stop_requested = True
        super().stop()  # also sets _stop_flag and halts devices best-effort

    def pause(self):
        # set flag first so the loop will block right away
        self._paused = True
        try:
            if self.lf:
                # hard stop so the carriage doesn’t coast
                for name in ("stop_motion", "send_stop", "stop"):
                    if hasattr(self.lf, name):
                        getattr(self.lf, name)()
                        break
            self.log("[Docking] Paused (LF stopped).")
        except Exception:
            pass

    def resume(self):
        self._paused = False
        try:
            if self.lf and hasattr(self.lf, "send_velocity"):
                # reapply last commanded velocity (creep if we’d slowed down)
                self.lf.send_velocity(self._cur_velocity)
            self.log(f"[Docking] Resumed (velocity {self._cur_velocity} mm/min).")
        except Exception:
            pass

    def run(self):
        self._stop_requested = False
        self.log("[Docking] Starting automated docking sequence...")

        velocity = float(getattr(self.data, "axial_velocity", 0) or 0.0)
        threshold_kN = float(getattr(self.data, "load_threshold", 0) or 0.0)

        def _clamp(v, lo, hi):
            return max(lo, min(hi, v))

        def _sign(v):
            return 1.0 if v >= 0 else -1.0

        v_clamped = _clamp(velocity, -1.0, 1.0)
        if abs(v_clamped) < 0.05 and v_clamped != 0.0:
            v_clamped = 0.05 * _sign(v_clamped)
        if velocity != v_clamped:
            self.log(f"[Docking] Requested {velocity:.3f} mm/min → clamped to {v_clamped:.3f} mm/min")

        self._cur_velocity = v_clamped

        # Device presence checks
        if not self.lf or (hasattr(self.lf, "is_ready") and not self.lf.is_ready()):
            self.log("[Docking] Load frame not connected; waiting for user to advance.")
            while not self._stop_flag.is_set():
                self._pause_barrier(); time.sleep(0.2)
            return

        if not self.serial_pad:
            self.log("[Docking] SerialPad not connected; cannot measure load. Waiting for user.")
            while not self._stop_flag.is_set():
                self._pause_barrier(); time.sleep(0.2)
            return

        try:
            # --- before the loop: set up velocity and capture baseline ---
            self.log(f"[Docking] Moving at {velocity:.3f} mm/min until Δload = {threshold_kN:.3f} kN is reached (relative to start).")
            if hasattr(self.lf, "send_velocity"):
                self.lf.send_velocity(velocity)
            self._cur_velocity = velocity

            # Direction based on desired change sign (+ increase compression/tension, – decrease)
            sign = 1.0 if threshold_kN >= 0 else -1.0
            targetP = abs(threshold_kN)         # target progress (always positive)
            creepP  = 0.50 * targetP            # slow down near 80% of the desired change
            poll_dt = 0.05
            creep_velocity = 0.1                # mm/min (tweak)
            noise_deadband = 0.005              # kN; ignore tiny jitter (~5 N)

            # --- measure baseline over a short window to reduce noise ---
            def read_load_kn():
                try:
                    ch = self.serial_pad.read_channels()
                    return ch[0] if (ch and ch[0] is not None) else 0.0
                except Exception:
                    return 0.0

            samples = []
            t0 = time.time()
            while time.time() - t0 < 0.20 and not (self._stop_requested or self._stop_flag):
                self._pause_barrier()
                samples.append(read_load_kn())
                time.sleep(0.02)
            baseline_kN = sum(samples) / max(1, len(samples))
            self.log(f"[Docking] Baseline load: {baseline_kN:.3f} kN")

            # Optional: simple EMA to smooth noisy readings
            ema = baseline_kN
            alpha = 0.3  # 0..1 (higher = less smoothing)

            # --- main loop using Δload relative to baseline ---
            while not (self._stop_requested or self._stop_flag):
                self._pause_barrier()
                if self._stop_requested or self._stop_flag:
                    break

                load_kN = read_load_kn()
                # smooth a bit
                ema = alpha * load_kN + (1 - alpha) * ema
                load_kN_smoothed = ema

                delta_kN = load_kN_smoothed - baseline_kN
                # ignore tiny noise around zero
                if abs(delta_kN) < noise_deadband:
                    delta_kN = 0.0

                progress = sign * delta_kN  # project toward + direction

                self.log(f"[Docking] Load: {load_kN_smoothed:.3f} kN | Δ: {delta_kN:+.3f} kN "
                         f"(progress {progress:.3f}/{targetP:.3f})")

                # Stop when we've achieved the desired change in the chosen direction
                if progress >= targetP:
                    for name in ("stop_motion", "send_stop", "stop"):
                        if hasattr(self.lf, name):
                            try:
                                getattr(self.lf, name)()
                                break
                            except Exception:
                                pass
                    self.log(f"[✓] Δload target reached: {delta_kN:+.3f} kN (target {threshold_kN:+.3f} kN)")
                    break

                # Creep near target (direction-aware), but do NOT stop early
                if progress >= creepP and self._cur_velocity > creep_velocity:
                    if hasattr(self.lf, "send_velocity"):
                        try:
                            self.lf.send_velocity(creep_velocity)
                            self._cur_velocity = creep_velocity
                            self.log(f"[Docking] Nearing target Δ. Slowing to {creep_velocity:.3f} mm/min")
                        except Exception:
                            pass

                time.sleep(poll_dt)



        except Exception as e:
            self.log(f"[!] Docking error: {e}")
        finally:
            # Always stop at the end or on stop
            try:
                if hasattr(self.lf, "stop_motion"):
                    self.lf.stop_motion()
                self._cur_velocity = 0.0
                self.log("[Docking] Done (LF stopped).")
            except Exception:
                pass


    def _pause_barrier(self):
        # wait here while paused, but allow Stop to break out immediately
        while getattr(self, "_paused", False) and not (self._stop_requested or self._stop_flag):
            time.sleep(0.02)

