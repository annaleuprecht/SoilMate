from PyQt5.QtCore import QObject, QTimer, pyqtSignal, QThread, QReadWriteLock
from PyQt5.QtWidgets import QMessageBox
import time
import csv
from stages.automated_docking_stage import AutomatedDockingStage
from stages.saturation_stage import SaturationStage
from stages.bcheck_stage import BCheckStage
from stages.consolidation_stage import ConsolidationStage
from stages.shear_stage import ShearStage
from contextlib import contextmanager
from typing import Optional, Dict, List
from sip import isdeleted


STAGE_CLASS_MAP = {
    "Automated Docking": AutomatedDockingStage,
    "Saturation": SaturationStage,
    "B Check": BCheckStage,
    "Consolidation": ConsolidationStage,
    "Shear": ShearStage,
}

class StageWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, stage_instance):
        super().__init__()
        self.stage = stage_instance

    def run(self):
        try:
            self.stage.run()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        """Forward stop request to the stage instance if supported."""
        try:
            if hasattr(self.stage, "stop"):
                self.stage.stop()
        except Exception:
            pass


class TriaxialTestManager(QObject):
    stage_changed = pyqtSignal(str)
    reading_updated = pyqtSignal(dict)
    test_finished = pyqtSignal()
    test_started = pyqtSignal(float)     
    stage_started = pyqtSignal(float)    
    stage_completed = pyqtSignal(int)    # emits stage index when a stage completes

    def __init__(self, lf_controller, cell_pressure_controller, back_pressure_controller,
                 serial_pad, test_config, main_window=None, log=print):
        super().__init__()
        # --- inside TriaxialTestManager.__init__ ---
        def _unwrap(dev):
            return getattr(dev, "driver", dev)

        self.lf      = _unwrap(lf_controller)
        self.cell_pc = _unwrap(cell_pressure_controller)
        self.back_pc = _unwrap(back_pressure_controller)
        self.serial_pad = serial_pad
        self.log = log

        self.is_paused = False
        self.stop_requested = False
        self._resume_armed = True   # ready to allow first resume
        self.last_stop_requested = False


        self.current_stage_index = -1
        self.start_time = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

        self.data_log = []
        self.running = False
        self.config = test_config
        self.stages = test_config["stages"]  # ✅ ensures it's a list

        self.main_window = main_window

        self.current_index = 0
        self.current_stage = None

        self.test_start_ts = None
        self.stage_start_ts = None
        
        self._last_emit_ts = 0.0
        self.sampling_period_s = float(test_config.get("sampling_period_s", 0.5))
        self._emit_interval_s = max(0.05, self.sampling_period_s)
        self._tick_ms = int(self._emit_interval_s * 1000)

        self.sample_id = test_config.get("sample_id", "")
        self.sample_height_cm = float(test_config.get("sample_height_cm", 0.0))
        self.sample_diameter_cm = float(test_config.get("sample_diameter_cm", 0.0))
        self.is_docked = bool(test_config.get("is_docked", False))
        self.test_date_str = None

        # --- pause-aware timekeeping (monotonic) ---
        self._test_start_mono = None
        self._test_paused_total = 0.0
        self._test_pause_enter_mono = None

        self._stage_start_mono = None
        self._stage_paused_total = 0.0
        self._stage_pause_enter_mono = None

        # event log (simple JSON-serializable dicts)
        self.events = []


    def start(self):
        self.log("[*] Starting triaxial test.")
        #print("[DEBUG] TriaxialTestManager.start() called")
        self.running = True
        self.test_start_ts = time.time()
        import time as _t
        self.test_date_str = _t.strftime("%Y-%m-%d", _t.localtime(self.test_start_ts))
        self._test_start_mono = time.monotonic()
        self._test_paused_total = 0.0
        self._test_pause_enter_mono = None
        self.events.append({"event":"TEST_START","wall_ts": self.test_start_ts})
        self.test_started.emit(self.test_start_ts)          # tell UI when t_test = 0
        self.current_index = 0
        self.run_stage(self.current_index)

    def _on_stage_complete(self):
        self.thread = None
        self.worker = None
        self.timer.stop()
        # event + signal
        if self.stop_requested:
            self.log("[DEBUG] Stage ended by stop request (flag stays True)")
        else:
            self.stop_requested = False
            self.log("[DEBUG] Stage ended naturally (flag cleared)")
            
        try:
            self.events.append({"event":"STAGE_END","stage_index": self.current_index, "wall_ts": time.time()})
        except Exception:
            pass
        try:
            self.stage_completed.emit(self.current_index)
        except Exception:
            pass

        # Continue to next stage logic
        if self.current_index + 1 < len(self.stages):
            self.log("[→] Waiting for 'Next Stage' input...")
        else:
            self.finish()
            
    @staticmethod        
    def _current_kpa(dev, log=None):
        """Read current pressure (kPa) from a controller. Unwrap shim; use cache first."""
        if not dev:
            return None
        ctrl = getattr(dev, "driver", dev)  # unwrap shim → backend

        # 1) cached (fast)
        try:
            f = getattr(ctrl, "get_cached_pressure", None)
            if callable(f):
                v = f(0.8)  # accept cache ≤0.8 s old
                if v is not None:
                    return float(v)
        except Exception:
            pass

        # 2) short live read
        try:
            f = getattr(ctrl, "read_pressure_kpa", None)
            if callable(f):
                v = f(timeout_s=0.25)
                if v is not None:
                    return float(v)
        except Exception as e:
            if log: log(f"[dbg] live read failed: {e}")

        return None

    def stop_current_stage(self):
        """Compatibility alias for GUI."""
        self.stop_stage()

    def _index_of(self, stage_id: str):
        for i, s in enumerate(self.stages):
            if getattr(s, "stage_id", None) == stage_id:
                return i
        return None

    def edit_stage(self, stage_id: str, updates: dict) -> bool:
        """Update fields on a StageData object by id."""
        idx = self._index_of(stage_id)
        if idx is None:
            return False
        s = self.stages[idx]
        if hasattr(s, "update_fields"):
            s.update_fields(updates)
        else:
            for k, v in (updates or {}).items():
                if hasattr(s, k):
                    setattr(s, k, v)
        return True

    def add_stage(self, new_stage, index=None) -> bool:
        """Insert a new stage into the plan."""
        if index is None or index > len(self.stages):
            index = len(self.stages)
        self.stages.insert(index, new_stage)
        return True

    def remove_stage(self, stage_id: str) -> bool:
        """Remove a stage by id."""
        idx = self._index_of(stage_id)
        if idx is None:
            return False
        del self.stages[idx]
        return True


    def run_stage(self, index):
        if 0 <= index < len(self.stages):
            self.current_stage_index = index  # <-- keep _tick() in sync
            self._resume_armed = True
            stage_data = self.stages[index]
            self.stage_start_ts = time.time()
            self._stage_start_mono = time.monotonic()
            self._stage_paused_total = 0.0
            self._stage_pause_enter_mono = None
            self.events.append({"event":"STAGE_START","stage_index": index, "stage_name": stage_data.name, "wall_ts": self.stage_start_ts})
            self.stage_started.emit(self.stage_start_ts) 
            self.log(f"[→] Starting stage: {stage_data.name}")
            self.stage_changed.emit(stage_data.name)

            self.start_time = time.time()
            self.is_paused = False
            self.stop_requested = False
            self.timer.start(getattr(self, "_tick_ms", 500))  # default; we’ll make this user-configurable later

            stage_class = STAGE_CLASS_MAP.get(stage_data.stage_type)
            if stage_class:
                u_lf   = getattr(self.lf, "driver", self.lf)
                u_cell = getattr(self.cell_pc, "driver", self.cell_pc)
                u_back = getattr(self.back_pc, "driver", self.back_pc)

                # ✅ actually create the stage instance first
                stage_instance = stage_class(stage_data, u_lf, u_cell, u_back, self.serial_pad, self.log)
                self.current_stage = stage_instance

                if not self._check_stage_devices(stage_instance):
                    self.log(f"[!] Stage '{stage_data.name}' aborted by user due to missing device(s).")
                    return

                # ✅ now that it's real, you can attach publishers
                stage_instance.attach_publisher(
                    self.reading_updated.emit,
                    test_start_ts=self.test_start_ts,
                    stage_index=self.current_stage_index
                )
                stage_instance.mark_stage_start()  # anchor stage elapsed time

                # Start in new thread
                self.thread = QThread()
                self.worker = StageWorker(stage_instance)
                self.worker.moveToThread(self.thread)

                self.thread.started.connect(self.worker.run)
                self.worker.finished.connect(self.thread.quit)
                self.worker.finished.connect(lambda: self.log(f"[✓] Finished stage: {stage_data.name}"))
                self.worker.finished.connect(self._on_stage_complete)
                self.worker.error.connect(lambda msg: self.log(f"[!] Error running stage: {msg}"))

                self.thread.finished.connect(self.worker.deleteLater)
                self.thread.finished.connect(self.thread.deleteLater)

                self.thread.start()
            else:
                self.log(f"[!] Unknown stage type: {stage_data.stage_type}")


    def _stop_thread(self):
        """Gracefully stop the QThread running the current stage."""
        # Ask the stage to stop
        try:
            if self.current_stage and hasattr(self.current_stage, "stop"):
                self.current_stage.stop()
        except Exception:
            pass

        th = getattr(self, "thread", None)

        # If not a QThread or already deleted, just clear and return
        if not isinstance(th, QThread) or isdeleted(th):
            self.thread = None
            self.worker = None
            return

        try:
            if th.isRunning():
                try: th.requestInterruption()
                except Exception: pass
                try: th.quit()
                except Exception: pass
                if not th.wait(2000):
                    try:
                        th.terminate()
                        th.wait(1000)
                    except Exception:
                        pass
        except RuntimeError:
            # Underlying C++ object may have been deleted between checks
            pass
        finally:
            self.thread = None
            self.worker = None

    def stop_stage(self):
        """Stop the current stage cleanly."""
        self.stop_requested = True
        self.last_stop_requested = True 
        try:
            self.timer.stop()
        except Exception:
            pass
        if hasattr(self, "worker") and self.worker:
            try:
                self.worker.stop()
            except Exception:
                pass
        self._stop_thread()


    def finish(self):
        if getattr(self, "_post_stop_cancelled", False):
            self.log("[DEBUG] Cancel pressed → skipping stage finish and test complete.")
            self._post_stop_cancelled = False  # reset
            return   # <- exit cleanly, do not finalize or end test
        self.running = False
        self.timer.stop()
        self._stop_thread()
        self.log("[✓] Triaxial test complete.")
        self.events.append({"event":"TEST_END","wall_ts": time.time()})
        self.test_finished.emit()
        try:
            with open(f"triaxial_events_{int(time.time())}.jsonl","w") as ef:
                for ev in self.events:
                    import json; ef.write(json.dumps(ev)+"\n")
        except Exception as e:
            self.log(f"[!] Failed to write events log: {e}")

    def abort(self):
        self.running = False
        self.timer.stop()
        self._stop_thread()
        self.log("[✗] Test aborted.")
        self.test_finished.emit()  
            
    def next_stage(self):
        self._stop_thread()
        self._flush_controllers()
        idx = self.current_stage_index + 1

        vp = getattr(self, "view_page", None)
        if vp:
            try:
                # Try reset_graphs(); fall back to reset_for_new_stage()
                reset_fn = getattr(vp, "reset_graphs", None) or getattr(vp, "reset_for_new_stage", None)
                if callable(reset_fn):
                    reset_fn()

                # Init graphs if available
                init_fn = getattr(vp, "init_graphs", None)
                if callable(init_fn):
                    upcoming_type = getattr(self.stages[idx], "stage_type", None) if idx < len(self.stages) else None
                    init_fn(stage_type=upcoming_type)
            except Exception:
                pass

        if idx < len(self.stages):
            self.run_stage(idx)
        else:
            self.finish()


    def _tick(self):
        if self.is_paused:
            return

        now = time.time()

        # Elapsed clocks (robust to None)
        t0 = self.test_start_ts or now
        s0 = self.stage_start_ts or now
        test_elapsed  = now - t0
        stage_elapsed = now - s0

        # Stage label
        try:
            stage_obj = self.stages[self.current_stage_index]
            stage_name = getattr(stage_obj, "name", f"Stage {self.current_stage_index + 1}")
        except Exception:
            stage_name = f"Stage {self.current_stage_index + 1}"

        readings = {
            "timestamp": now,
            "test_elapsed_s": round(test_elapsed, 3),
            "stage_elapsed_s": round(stage_elapsed, 3),
            "time_s": round(stage_elapsed, 3),
            "stage_index": self.current_stage_index,
            "stage_name": stage_name,

            # keep date per row (overnight runs)
            "date": time.strftime("%Y-%m-%d", time.localtime(now)),

            # values filled below...
            "cell_pressure_kpa": None, "back_pressure_kpa": None,
            "cell_volume_mm3": None, "back_volume_mm3": None,
            "position_mm": None, "transducers": [],
        }

        # --- helpers: cached → quick live read fallback
        def _cached(dev, attr, freshness=1.5):
            try:
                fn = getattr(dev, attr, None)
                return float(fn(freshness)) if callable(fn) else None
            except Exception:
                return None

        def _live(dev, attr, **kw):
            try:
                fn = getattr(dev, attr, None)
                val = fn(**kw) if callable(fn) else None
                return float(val) if val is not None else None
            except Exception:
                return None

        # Fill pressures/volumes (don’t block if cache is fresh)
        if self.cell_pc:
            readings["cell_pressure_kpa"] = (
                _cached(self.cell_pc, "get_cached_pressure") or
                _live(self.cell_pc, "read_pressure_kpa", timeout_s=0.15)
            )
            readings["cell_volume_mm3"] = (
                _cached(self.cell_pc, "get_cached_volume") or
                _live(self.cell_pc, "read_volume_mm3", timeout_s=0.15)
            )
        if self.back_pc:
            readings["back_pressure_kpa"] = (
                _cached(self.back_pc, "get_cached_pressure") or
                _live(self.back_pc, "read_pressure_kpa", timeout_s=0.15)
            )
            readings["back_volume_mm3"] = (
                _cached(self.back_pc, "get_cached_volume") or
                _live(self.back_pc, "read_volume_mm3", timeout_s=0.15)
            )

        # Frame position (best-effort)
        if self.lf:
            readings["position_mm"] = (
                _cached(self.lf, "get_cached_position") or
                _live(self.lf, "read_position_mm", timeout_s=0.1)
            )

        # SerialPad channels (if available)
        try:
            if self.serial_pad:
                channels = self.serial_pad.read_channels()
                readings["transducers"] = channels
                if channels and len(channels) >= 3:
                    readings["axial_load_kN"]          = channels[0]
                    readings["pore_pressure_kpa"]      = channels[1]
                    readings["axial_displacement_mm"]  = channels[2]
        except Exception as e:
            self.log(f"[!] Error during reading: {e}")

        # book-keeping + emit (throttled)
        self.data_log.append(readings)
        self.shared_data = readings

        if (now - self._last_emit_ts) >= self._emit_interval_s:
            self._last_emit_ts = now
            self.reading_updated.emit(readings)


    def pause(self):
        self._resume_armed = True   # reset so next resume is allowed
        self.is_paused = True
        try:
            if self._test_pause_enter_mono is None:
                self._test_pause_enter_mono = time.monotonic()
            if self._stage_pause_enter_mono is None:
                self._stage_pause_enter_mono = time.monotonic()
        except Exception:
            pass
        try:
            self.events.append({"event":"PAUSE","wall_ts": time.time(), "stage_index": self.current_stage_index})
        except Exception:
            pass
        # stop manager polling timer
        try:
            if self.timer.isActive():
                self.timer.stop()
        except Exception:
            pass
        # try to pause the stage logic if the stage implements it
        try:
            if self.current_stage and hasattr(self.current_stage, "pause"):
                self.current_stage.pause()
        except Exception:
            pass
        self.log("[⏸] Manager paused.")

    def resume(self):
        if not self._resume_armed:
            self.log("[⚠] Resume ignored (already resumed once).")
            return
        self._resume_armed = False
        self.is_paused = False
        try:
            nowm = time.monotonic()
            if self._test_pause_enter_mono is not None:
                self._test_paused_total += (nowm - self._test_pause_enter_mono)
                self._test_pause_enter_mono = None
            if self._stage_pause_enter_mono is not None:
                self._stage_paused_total += (nowm - self._stage_pause_enter_mono)
                self._stage_pause_enter_mono = None
        except Exception:
            pass
        try:
            self.events.append({"event":"RESUME","wall_ts": time.time(), "stage_index": self.current_stage_index})
        except Exception:
            pass
        # restart manager polling timer
        try:
            if not self.timer.isActive():
                self.timer.start(500)   # same cadence you start with in run_stage()
        except Exception:
            pass
        # try to resume the stage logic if the stage implements it
        try:
            if self.current_stage and hasattr(self.current_stage, "resume"):
                self.current_stage.resume()
        except Exception:
            pass
        self.log("[▶] Manager resumed.")

    def stop_current_stage(self):
        self.stop_requested = True
        try: self.timer.stop()
        except Exception: pass
        self._stop_thread()   # must wait out the QThread (quit/wait/terminate fallback)


    def advance_to_next_stage(self):
        # Use the unified path that flushes devices and advances by current_stage_index
        self.next_stage()



    def send_displacement_ramp(self, target_mm, mode="Constant"):
        try:
            if not self.lf:
                self.log("[!] Load frame not connected.")
                return
            self.log(f"[→] Sending displacement: {target_mm} mm [{mode} mode]")
            self.lf.send_displacement(target_mm)
        except Exception as e:
            self.log(f"[!] Failed to send displacement: {e}")


    def _save_log_to_csv(self):
        filename = f"triaxial_log_{int(time.time())}.csv"
        self.log(f"[*] Saving log to {filename}")
        if not self.data_log:
            return
        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.data_log[0].keys())
            writer.writeheader()
            for row in self.data_log:
                writer.writerow(row)

    def _flush_controllers(self):
        """Abort any lingering device activity and purge FTDI buffers."""
        ctrls = [self.cell_pc, self.back_pc, self.lf]
        for c in ctrls:
            if not c:
                continue
            # 1) best-effort halt/abort
            for name in ("stop", "stop_motion", "abort", "halt"):
                if hasattr(c, name):
                    try:
                        getattr(c, name)()
                        break
                    except Exception:
                        pass
            # 2) purge IO if supported (prevents late TX writes from prior stage)
            for name in ("purge", "purge_io", "flush"):
                if hasattr(c, name):
                    try:
                        getattr(c, name)()
                        break
                    except Exception:
                        pass
        time.sleep(0.15)

    def _check_stage_devices(self, stage) -> bool:
        def _unwrap(dev): return getattr(dev, "driver", dev)
        def _ready(dev):
            dev = _unwrap(dev)
            if dev is None:
                return False
            m = getattr(dev, "is_ready", None)
            try:
                return bool(m()) if callable(m) else True
            except Exception:
                return True  # be permissive during run; stage methods will fail if truly dead

        missing = []
        if hasattr(stage, "cell_pc") and stage.cell_pc and not _ready(stage.cell_pc):
            missing.append("Cell Pressure Controller")
        if hasattr(stage, "back_pc") and stage.back_pc and not _ready(stage.back_pc):
            missing.append("Back Pressure Controller")
        if hasattr(stage, "lf") and stage.lf and not _ready(stage.lf):
            missing.append("Load Frame")
        if hasattr(stage, "serial_pad") and stage.serial_pad and not _ready(stage.serial_pad):
            missing.append("Serial Pad")

        if not missing:
            return True
        # (keep your Yes/No dialog if you like)
        from PyQt5.QtWidgets import QMessageBox
        msg = "The following devices are not connected:\n - " + "\n - ".join(missing) + "\n\nContinue anyway?"
        resp = QMessageBox.warning(None, "Device(s) Not Connected", msg,
                                   QMessageBox.Yes | QMessageBox.No)
        return resp == QMessageBox.Yes




