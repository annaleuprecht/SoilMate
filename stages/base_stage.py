# stages/base_stage.py
import time
from typing import Dict, Iterable, Optional

class BaseStage:
    def __init__(self, data, lf, cell_pc, back_pc, serial_pad, log):
        self.data = data
        self.lf = lf
        self.cell_pc = cell_pc
        self.back_pc = back_pc
        self.serial_pad = serial_pad
        self.log = log or (lambda *a, **k: None)

        self._paused = False
        self._stop_flag = False

        # Publishing hooks (attached by manager)
        self._emit_reading_cb = None
        self._test_start_ts: Optional[float] = None
        self._stage_index: Optional[int] = None
        self._stage_start_ts: Optional[float] = None

    # ---------------------------
    # Manager wiring / publishing
    # ---------------------------
    def attach_publisher(self, emit_fn, *, test_start_ts=None, stage_index=None):
        """
        Hook provided by TriaxialTestManager so stages can publish live readings
        straight to the GUI. emit_fn should accept a dict (reading).
        """
        self._emit_reading_cb = emit_fn
        self._test_start_ts = test_start_ts
        self._stage_index = stage_index
        # stage_start is set per stage when run() begins
        self._stage_start_ts = None

    def mark_stage_start(self):
        """Call at the very start of run() to anchor stage elapsed time."""
        self._stage_start_ts = time.time()

    def _collect_reading(self):
        """Best-effort snapshot of current sensors."""
        now = time.time()
        # pressures
        cell = self._read_kpa(self.cell_pc)
        back = self._read_kpa(self.back_pc)
        # load frame position
        pos = None
        try:
            if self.lf and hasattr(self.lf, "read_position_mm"):
                pos = float(self.lf.read_position_mm())
        except Exception:
            pass
        # serial pad channels
        chans = []
        try:
            if self.serial_pad and hasattr(self.serial_pad, "read_channels"):
                chans = self.serial_pad.read_channels() or []
        except Exception:
            pass

        reading = {
            "timestamp": now,
            "cell_pressure_kpa": cell,
            "back_pressure_kpa": back,
            "position_mm": pos,
            "serial_channels": chans,
        }

        # Enrich with elapsed times (so X-axes work immediately)
        if self._test_start_ts is not None:
            reading["test_elapsed_s"] = round(now - self._test_start_ts, 3)
        if self._stage_start_ts is not None:
            reading["stage_elapsed_s"] = round(now - self._stage_start_ts, 3)

        # Stage metadata (helps filtering)
        if self._stage_index is not None:
            reading["stage_index"] = int(self._stage_index)

        return reading

    def publish_data(self, reading: dict):
        """Send a reading to the GUI via the manager's signal."""
        if not isinstance(reading, dict):
            return
        # Ensure elapsed fields present even if caller forgot
        now = reading.get("timestamp", time.time())
        if "test_elapsed_s" not in reading and self._test_start_ts is not None:
            reading["test_elapsed_s"] = round(now - self._test_start_ts, 3)
        if "stage_elapsed_s" not in reading and self._stage_start_ts is not None:
            reading["stage_elapsed_s"] = round(now - self._stage_start_ts, 3)
        if "stage_index" not in reading and self._stage_index is not None:
            reading["stage_index"] = int(self._stage_index)

        if len(self.xData) != len(self.yData):
            min_len = min(len(self.xData), len(self.yData))
            self.xData = self.xData[:min_len]
            self.yData = self.yData[:min_len]


        cb = self._emit_reading_cb
        if callable(cb):
            cb(reading)

    # ---------------
    # Lifecycle hooks
    # ---------------
    def pause(self):
        if self._paused:
            return
        self._paused = True
        # best-effort: stop everything once
        try:
            if self._is_ready(self.lf):
                for name in ("stop_motion", "stop", "halt"):
                    if hasattr(self.lf, name):
                        getattr(self.lf, name)(); break
        except Exception:
            pass
        try:
            if self._is_ready(self.cell_pc):
                for name in ("stop", "stop_pressure", "abort"):
                    if hasattr(self.cell_pc, name):
                        getattr(self.cell_pc, name)(); break
        except Exception:
            pass
        try:
            if self._is_ready(self.back_pc):
                for name in ("stop", "stop_pressure", "abort"):
                    if hasattr(self.back_pc, name):
                        getattr(self.back_pc, name)(); break
        except Exception:
            pass
        try: self.on_paused()
        except Exception: pass

    def resume(self):
        self._paused = False
        try: self.on_resumed()
        except Exception: pass


    # NEW: TriaxialTestManager may call this (shortcut for "graceful stop now")
    def request_stop(self, reason: str = ""):
        """Idempotent external stop request used by the manager."""
        self.log(f"[Stage] request_stop: {reason}" if reason else "[Stage] request_stop")
        self.stop()

    # -------------------
    # Live-update support
    # -------------------
    def allowed_live_fields(self) -> Iterable[str]:
        """
        Override in a subclass if you want to restrict which fields can change
        while the stage is running. By default, allow common primitives you
        actually read inside loops.
        """
        return (
            "cell_pressure",
            "back_pressure",
            "duration",
            "axial_velocity",
            "load_threshold",
            "safety_load_kN",
            "dock",
            "hold",
            "name",         # harmless UI update
        )

    def apply_config_update(self, updates: Dict) -> bool:
        """
        Attempt to apply live config changes safely.
        Returns True if any field was applied without requiring a rebuild.
        Subclasses can override for finer control or side effects.
        """
        if not isinstance(updates, dict) or not updates:
            return False

        allowed = set(self.allowed_live_fields())
        applied_any = False

        # If StageData has update_fields(), use it so we don't set unknown attrs.
        update_fields = getattr(self.data, "update_fields", None)
        if callable(update_fields):
            applied = self.data.update_fields(updates, allowed=allowed)
            applied_any = bool(applied)
        else:
            # Fallback: set only known + allowed attributes
            for k, v in updates.items():
                if k in allowed and hasattr(self.data, k):
                    try:
                        setattr(self.data, k, v)
                        applied_any = True
                    except Exception:
                        pass

        if applied_any:
            try:
                self.log(f"[Stage] Live update applied: {updates}")
            except Exception:
                pass
        return applied_any

    # ----------------
    # Stage subclass hooks
    # ----------------
    def on_paused(self): pass
    def on_resumed(self): pass
    def on_stopped(self): pass

    # -------------
    # Tiny helpers
    # -------------
    def _pause_barrier(self, poll_dt=0.05):
        """Call inside long loops to honor pause/stop promptly."""
        while self._paused and not self._stop_flag:
            time.sleep(poll_dt)
        return self._stop_flag  # lets caller early-exit if True

    @staticmethod
    def _read_kpa(ctrl):
        if not ctrl or not BaseStage._is_ready(ctrl):
            return None
        for name in ("read_pressure_kpa", "read_pressure"):
            if hasattr(ctrl, name):
                try:
                    v = getattr(ctrl, name)()
                    return None if v is None else float(v)
                except Exception:
                    pass
        return None

    @staticmethod
    def _ramp_pressure(ctrl, target_kpa, rate_kpa_per_min):
        if not ctrl or not BaseStage._is_ready(ctrl):
            return False
        if hasattr(ctrl, "ramp_pressure"):
            try:
                ctrl.ramp_pressure(float(target_kpa), float(rate_kpa_per_min))
                return True
            except Exception:
                return False
        if hasattr(ctrl, "send_pressure"):
            try:
                ctrl.send_pressure(float(target_kpa))
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def _is_ready(dev) -> bool:
        """Best-effort readiness:
           - If a status attribute exists, use it.
           - If none exists, assume ready (True)."""
        if dev is None:
            return False
        for attr in ("is_ready", "is_connected", "isConnected", "connected"):
            if hasattr(dev, attr):
                try:
                    v = getattr(dev, attr)
                    return bool(v() if callable(v) else v)
                except Exception:
                    return False
        # No explicit status API -> default to ready
        return True

    # stages/base_stage.py  (reuse/extend your helper + call it from stop())
    def _halt_devices(self):
        """Best-effort immediate stop of LF + both pressure controllers."""
        # Load frame — try explicit stop first, then fall back to stop(), then set velocity=0
        try:
            if self.lf:
                for name in ("stop_motion", "send_stop", "stop", "halt"):
                    fn = getattr(self.lf, name, None)
                    if callable(fn):
                        fn(); break
                vsetter = getattr(self.lf, "send_velocity", None)
                if callable(vsetter):
                    try: vsetter(0.0)
                    except Exception: pass
        except Exception:
            pass

        # Cell pressure controller
        try:
            if self.cell_pc:
                for name in ("stop", "stop_pressure", "abort"):
                    fn = getattr(self.cell_pc, name, None)
                    if callable(fn):
                        fn(); break
        except Exception:
            pass

        # Back pressure controller
        try:
            if self.back_pc:
                for name in ("stop", "stop_pressure", "abort"):
                    fn = getattr(self.back_pc, name, None)
                    if callable(fn):
                        fn(); break
        except Exception:
            pass

    def stop(self):
        self._stop_flag = True
        self._halt_devices()              # <— NEW: force hardware halt immediately
        try: self.on_stopped()
        except Exception: pass

