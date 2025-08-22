# stages/consolidation_stage.py
from .base_stage import BaseStage
import time

class ConsolidationStage(BaseStage):
    def __init__(self, data, lf, cell_pc, back_pc, serial_pad, log):
        super().__init__(data, lf, cell_pc, back_pc, serial_pad, log)
        self._stop_requested = False
        self._paused = False
        self._cell_kpa = 0.0
        self._back_kpa = 0.0

    def stop(self):
        self._stop_requested = True
        super().stop()

    def pause(self):
        self._paused = True
        self.log("[Consolidation] Paused (pressures held).")

    def resume(self):
        self._paused = False
        try:
            # reassert pressures on resume
            if self.cell_pc and hasattr(self.cell_pc, "send_pressure"):
                self.cell_pc.send_pressure(self._cell_kpa)
            if self.back_pc and hasattr(self.back_pc, "send_pressure"):
                self.back_pc.send_pressure(self._back_kpa)
            self.log("[Consolidation] Resumed (pressures re-applied).")
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
                        return float(fn())
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

    def run(self):
        self._stop_requested = False
        self.log("[Consolidation] Starting consolidation stage…")

        # Targets
        target_cell = float(getattr(self.data, "cell_pressure", 0.0) or 0.0)
        target_back = float(getattr(self.data, "back_pressure", 0.0) or 0.0)
        self._cell_kpa, self._back_kpa = target_cell, target_back

        if not self.cell_pc or not self.back_pc:
            self.log("[✗] Cell or Back pressure controller not connected.")
            return

        try:
            # Send once at start
            if hasattr(self.cell_pc, "send_pressure"):
                self.cell_pc.send_pressure(target_cell)
            if hasattr(self.back_pc, "send_pressure"):
                self.back_pc.send_pressure(target_back)

            self.log(f"[Consolidation] Holding: Cell={target_cell:.2f} kPa, Back={target_back:.2f} kPa")

            # Idle loop until stopped
            poll_dt = 1.0
            while not (self._stop_requested or self._stop_flag):
                self._pause_barrier()   # respects pause
                time.sleep(poll_dt)
                # inside while not (self._stop_requested or self._stop_flag):
                cell_now, back_now = self._read_pressures_kpa()
                vol_now = 0.0
                if self.serial_pad:
                    try:
                        ch = self.serial_pad.read_channels()
                        # assume volume/displacement on channel 1?
                        vol_now = ch[1] if len(ch) > 1 else 0.0
                    except Exception:
                        pass

                # Log in a structured way
                self.log(f"[Consolidation] Cell={cell_now:.2f} kPa | Back={back_now:.2f} kPa | Vol={vol_now:.3f} mm³")


        except Exception as e:
            self.log(f"[!] Consolidation stage error: {e}")
        finally:
            self.log("[Consolidation] Done.")
