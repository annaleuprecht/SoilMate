# stages/saturation_stage.py
import time
import threading
from ctypes import c_void_p
from .base_stage import BaseStage

class SaturationStage(BaseStage):
    """
    Duration-based linear ramp (1 Hz setpoints).
    On start/resume, issues ramps toward target(s).
    Pause halts hardware immediately until resumed.
    """

    def __init__(self, data, lf, cell_pc, back_pc, serial_pad, log):
        super().__init__(data, lf, cell_pc, back_pc, serial_pad, log)

        # targets from StageData (may be blank/None)
        self.target_cell_kpa = getattr(self.data, "cell_pressure", None)
        self.target_back_kpa = getattr(self.data, "back_pressure", None)

        # tolerances & throttles
        self.deadband_kpa = 0.05
        self.rearm_min_interval = 0.75
        self._last_rearm_cell = 0.0
        self._last_rearm_back = 0.0

        # normalize targets: None means "don't control"
        try:
            self.target_cell_kpa = float(self.target_cell_kpa)
        except Exception:
            self.target_cell_kpa = None
        try:
            self.target_back_kpa = float(self.target_back_kpa)
        except Exception:
            self.target_back_kpa = None

    # ---------- helpers ----------
    def _unwrap(self, dev):
        """Shim → backend if present."""
        return getattr(dev, "driver", dev)

    def _ready(self, dev):
        """Quiet readiness check: valid FTDI handle present."""
        d = self._unwrap(dev)
        h = getattr(d, "h", None)
        return isinstance(h, c_void_p) and bool(h)

    def _probe_kpa(self, dev, default=None, retries=2, wait_s=0.15, cache_s=1.0):
        """
        Current pressure: prefer cache (fast), then short live read with optional retries.
        Returns float or `default` if still unknown.
        """
        ctrl = self._unwrap(dev)

        # 1) cached (non-blocking)
        try:
            f = getattr(ctrl, "get_cached_pressure", None)
            if callable(f):
                v = f(cache_s)
                if v is not None:
                    return float(v)
        except Exception:
            pass

        # 2) short live read (+ optional retries)
        for _ in range(max(1, retries)):
            try:
                f = getattr(ctrl, "read_pressure_kpa", None)
                if callable(f):
                    v = f(timeout_s=0.25)
                    if v is not None:
                        return float(v)
            except Exception:
                pass
            if wait_s:
                time.sleep(wait_s)

        return default

    def _at_target(self, cur, target):
        return (cur is not None) and (target is not None) and abs(cur - target) <= self.deadband_kpa

    def _maybe_send(self, dev, setpoint_kpa):
        """Send only if device is ready and we're not already within deadband."""
        if setpoint_kpa is None:
            return
        if not self._ready(dev):
            return

        ctrl = self._unwrap(dev)

        # Skip redundant sends within deadband of current reading (cuts chatter)
        cur = self._probe_kpa(ctrl, default=None, retries=0)
        if cur is not None and self._at_target(cur, setpoint_kpa):
            return

        try:
            if hasattr(ctrl, "send_pressure"):
                ctrl.send_pressure(float(setpoint_kpa))
        except Exception as e:
            self.log(f"[!] Failed to send setpoint ({setpoint_kpa} kPa): {e}")

    # ---------- re-arm on resume ----------
    def _arm_cell(self):
        if self.target_cell_kpa is None:
            return
        now = time.time()
        if now - self._last_rearm_cell < self.rearm_min_interval:
            return
        cur = self._probe_kpa(self.cell_pc)
        if not self._at_target(cur, self.target_cell_kpa):
            if self._ramp_pressure(self._unwrap(self.cell_pc), self.target_cell_kpa, self.rate_kpa_per_min):
                self._last_rearm_cell = now
                self.log(f"[Sat] Cell → {self.target_cell_kpa:.2f} kPa @ {self.rate_kpa_per_min:.2f} kPa/min (cur={cur!s})")

    def _arm_back(self):
        if self.target_back_kpa is None:
            return
        now = time.time()
        if now - self._last_rearm_back < self.rearm_min_interval:
            return
        cur = self._probe_kpa(self.back_pc)
        if not self._at_target(cur, self.target_back_kpa):
            if self._ramp_pressure(self._unwrap(self.back_pc), self.target_back_kpa, self.rate_kpa_per_min):
                self._last_rearm_back = now
                self.log(f"[Sat] Back → {self.target_back_kpa:.2f} kPa @ {self.rate_kpa_per_min:.2f} kPa/min (cur={cur!s})")

    # ---------- lifecycle ----------
    def run(self):
        self.log("[Saturation] Start (duration-based, 1 Hz setpoints)")

        # Inputs from StageData
        try:
            target_cell = float(getattr(self.data, "cell_pressure", 0.0))
        except Exception:
            target_cell = 0.0
        try:
            tb = getattr(self.data, "back_pressure", None)
            target_back = float(tb) if tb not in (None, "") else None
        except Exception:
            target_back = None
        try:
            duration_min = float(getattr(self.data, "duration", 0.0))
        except Exception:
            duration_min = 0.0

        # Duration == 0 → single set & hold
        if duration_min <= 0.0:
            try:
                self._maybe_send(self.cell_pc, target_cell)
                if target_back is not None:
                    self._maybe_send(self.back_pc, target_back)
            except Exception as e:
                self.log(f"[!] Saturation immediate-set error: {e}")
            self.log("[Saturation] Duration=0 → setpoint applied; holding for user.")
            while not self._stop_flag:
                self._pause_barrier()
                time.sleep(0.2)
            return

        # 1 Hz steps over duration
        steps = max(1, int(round(duration_min * 60.0)))

        # Detect starting pressures (cache-first; retry briefly)
        cell_start = self._probe_kpa(self.cell_pc, default=None, retries=2, wait_s=0.15, cache_s=1.0)
        back_start = None
        if target_back is not None:
            back_start = self._probe_kpa(self.back_pc, default=None, retries=2, wait_s=0.15, cache_s=1.0)

        if cell_start is None:
            # If your rig commonly sits around 35 kPa idle, keep this default; otherwise adjust.
            self.log("[Sat] Cell start unknown; assuming 35.0 kPa")
            cell_start = 35.0
        else:
            self.log(f"[Sat] Cell start detected: {cell_start:.2f} kPa")

        if target_back is not None:
            if back_start is None:
                self.log("[Sat] Back start unknown; assuming 0.0 kPa")
                back_start = 0.0
            else:
                self.log(f"[Sat] Back start detected: {back_start:.2f} kPa")

        # Plan
        cell_delta = (target_cell - cell_start)
        back_delta = (target_back - back_start) if (target_back is not None and back_start is not None) else None
        self.log(f"[ramp] Start {cell_start:.3f} → {target_cell:.3f} kPa over {duration_min:.2f} min "
                 f"({steps} steps @ 1 Hz)")

        step_period = 1.0  # seconds between setpoints
        t0 = time.monotonic()

        # Ramp loop
        for i in range(1, steps + 1):
            if self._stop_flag:
                break
            self._pause_barrier()

            frac = i / steps
            cell_sp = cell_start + cell_delta * frac
            cell_sp = min(cell_sp, target_cell) if cell_delta >= 0 else max(cell_sp, target_cell)

            self._maybe_send(self.cell_pc, cell_sp)

            if (target_back is not None) and (back_delta is not None):
                back_sp = back_start + back_delta * frac
                back_sp = min(back_sp, target_back) if back_delta >= 0 else max(back_sp, target_back)
                self._maybe_send(self.back_pc, back_sp)
                self.log(f"[→] Cell {cell_sp:.5f} kPa | Back {back_sp:.5f} kPa")
            else:
                self.log(f"[→] Cell {cell_sp:.5f} kPa")


            target = t0 + i * step_period
            while not self._stop_flag and time.monotonic() < target:
                self._pause_barrier()
                time.sleep(0.02)   # light nap; keeps UI responsive

        # Hold at target until operator advances
        self.log("[Saturation] Ramp complete. Holding at target; waiting for user.")
        while not self._stop_flag:
            self._pause_barrier()
            time.sleep(0.2)

        # Graceful stop
        try:
            if self.cell_pc and hasattr(self._unwrap(self.cell_pc), "stop"):
                self._unwrap(self.cell_pc).stop()
            if self.back_pc and hasattr(self._unwrap(self.back_pc), "stop"):
                self._unwrap(self.back_pc).stop()
        except Exception:
            pass
        self.log("[Saturation] Finished")

    def on_resumed(self):
        # re-arm after a pause (continues from current kPa)
        self._arm_cell()
        self._arm_back()
