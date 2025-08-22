# stages/pauseable.py
import time

class PauseableStage:
    def __init__(self):
        self._paused = False
        self._stop_flag = False

    def pause(self):
        if self._paused:
            return
        self._paused = True
        # Best-effort: stop everything once on pause
        try:
            if getattr(self, "lf", None):
                for name in ("stop_motion", "stop", "halt"):
                    if hasattr(self.lf, name):
                        getattr(self.lf, name)(); break
            if getattr(self, "cell_pc", None):
                for name in ("stop", "stop_pressure", "abort"):
                    if hasattr(self.cell_pc, name):
                        getattr(self.cell_pc, name)(); break
            if getattr(self, "back_pc", None):
                for name in ("stop", "stop_pressure", "abort"):
                    if hasattr(self.back_pc, name):
                        getattr(self.back_pc, name)(); break
        except Exception:
            pass

    def resume(self):
        self._paused = False  # stage will decide what to re-arm

    def stop(self):
        self._stop_flag = True
        # Hard stop on end
        try:
            if getattr(self, "lf", None):
                for name in ("stop_motion", "stop", "halt"):
                    if hasattr(self.lf, name):
                        getattr(self.lf, name)(); break
            if getattr(self, "cell_pc", None):
                for name in ("stop", "stop_pressure", "abort"):
                    if hasattr(self.cell_pc, name):
                        getattr(self.cell_pc, name)(); break
            if getattr(self, "back_pc", None):
                for name in ("stop", "stop_pressure", "abort"):
                    if hasattr(self.back_pc, name):
                        getattr(self.back_pc, name)(); break
        except Exception:
            pass

    def _pause_barrier(self, poll_dt=0.05):
        """Call inside loops to block while paused."""
        while self._paused and not self._stop_flag:
            time.sleep(poll_dt)
