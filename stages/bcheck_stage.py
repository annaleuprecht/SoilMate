# stages/bcheck_stage.py
from .base_stage import BaseStage
import time

class BCheckStage(BaseStage):
    def run(self):
        self.log("[B Check] Starting B Check stage...")

        # Resolve target (None/'' means do nothing)
        v = getattr(self.data, "cell_pressure", None)
        try:
            self._target_cell_kpa = float(v) if v not in (None, "") else None
        except Exception:
            self._target_cell_kpa = None

        if self._target_cell_kpa is None or not self._is_ready(self.cell_pc):
            self.log("[✗] Cell pressure controller not ready or no target.")
            # Hold until user advances, so UI flow still works
            while not self._stop_flag:
                self._pause_barrier()
                time.sleep(0.2)
            return

        try:
            self.log(f"[B Check] Instantly applying cell pressure: {self._target_cell_kpa:.2f} kPa")
            if hasattr(self.cell_pc, "send_pressure"):
                self.cell_pc.send_pressure(self._target_cell_kpa)
        except Exception as e:
            self.log(f"[!] B Check error: {e}")

        self.log("[B Check] Pressure applied. Monitor B-value in the graph.")
        self.log("[B Check] Waiting for user to continue to next stage.")

        # Idle loop so Pause/Continue/Stop work
        while not self._stop_flag:
            self._pause_barrier()
            time.sleep(0.2)

    # --- Pause only cell pressure ---
    def pause(self):
        self._paused = True
        try:
            if self._is_ready(self.cell_pc):
                for name in ("stop", "stop_pressure", "abort"):
                    if hasattr(self.cell_pc, name):
                        getattr(self.cell_pc, name)(); break
            self.log("[B Check] Paused (cell pressure held).")
        except Exception:
            pass

    def resume(self):
        self._paused = False
        try:
            if (getattr(self, "_target_cell_kpa", None) is not None
                and self._is_ready(self.cell_pc)
                and hasattr(self.cell_pc, "send_pressure")):
                self.cell_pc.send_pressure(self._target_cell_kpa)
            self.log("[B Check] Resumed (reasserted cell setpoint).")
        except Exception:
            pass

    def stop(self):
        # Ensure base stops flags & devices
        super().stop()



## Set cell pressure ONLY
## Changes to that instantaneously 
## Use cell pressure and pore pressure from PPT to calculate B value
## Stops when user presses button for "next stage"
            
