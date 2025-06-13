from PyQt5.QtCore import QObject, QTimer, pyqtSignal
import time
import csv

class TriaxialTestManager(QObject):
    stage_changed = pyqtSignal(str)
    reading_updated = pyqtSignal(dict)
    test_finished = pyqtSignal()

    def __init__(self, lf_controller, cell_pressure_controller, back_pressure_controller, serial_pad, test_config, log=print):
        super().__init__()
        self.lf = lf_controller
        self.cell_pc = cell_pressure_controller
        self.back_pc = back_pressure_controller
        self.serial_pad = serial_pad
        self.config = test_config
        self.log = log

        self.current_stage_index = -1
        self.start_time = None
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

        self.data_log = []
        self.running = False

    def start(self):
        self.log("[*] Starting triaxial test.")
        self.running = True
        self.next_stage()

    def next_stage(self):
        self.current_stage_index += 1
        if self.current_stage_index >= len(self.config["stages"]):
            self.finish()
            return

        stage = self.config["stages"][self.current_stage_index]
        self.log(f"[→] Starting stage: {stage['name']}")
        self.stage_changed.emit(stage["name"])

        if "pressure_kpa" in stage and self.cell_pc:
            self.cell_pc.send_pressure(stage["pressure_kpa"])

        if "back_pressure_kpa" in stage and self.back_pc:
            # Volume = back pressure (kPa) × 100 (temporary conversion for now)
            volume_mm3 = stage["back_pressure_kpa"] * 100
            self.back_pc.send_volume(volume_mm3)

        # Axial control (shear stage)
        if stage.get("control_load") and "axial_control" in stage:
            axial = stage["axial_control"]
            self.log(f"[Axial] Mode: {axial['mode']}, Target: {axial['target']}, Type: {axial['type']}")
            try:
                target = float(axial["target"])
                if "Displacement" in axial["mode"]:
                    self.send_displacement_ramp(target, axial["type"])
                else:
                    self.log("[!] Axial load control not yet implemented.")
            except Exception as e:
                self.log(f"[!] Invalid axial control target: {e}")

        self.start_time = time.time()
        if "duration_min" in stage:
            self.timer.start(1000)
        else:
            self.log("[*] No duration set for this stage. Waiting manually or via displacement.")

    def _tick(self):
        elapsed = time.time() - self.start_time
        stage = self.config["stages"][self.current_stage_index]
        duration = stage.get("duration_min", 0) * 60

        readings = {
            "time_s": round(elapsed, 2),
            "stage": stage["name"],
            "pressure": None,
            "volume": None,
            "displacement": None,
            "transducers": [],
            "cell_pressure": None,
            "back_pressure": None,
            "pore_pressure": None,
            "axial_displacement": None,
            "cell_volume": None,
            "back_volume": None,
        }

        try:
            if self.serial_pad:
                channels = self.serial_pad.read_channels()
                readings["transducers"] = channels

                if channels:
                    readings["axial_load"] = channels[0]                 # kN
                    readings["pore_pressure"] = channels[1]              # kPa
                    readings["axial_displacement"] = channels[2]         # mm
                    readings["local_axial_1_mv"] = channels[3]           # mV
                    readings["local_axial_2_mv"] = channels[4]           # mV
                    readings["local_radial_mv"] = channels[5]            # mV

        except Exception as e:
            self.log(f"[!] Error during reading: {e}")

        self.data_log.append(readings)
        self.shared_data = readings
        print("[Graph Debug]", readings)
        self.reading_updated.emit(readings)

        if duration and elapsed >= duration:
            self.timer.stop()
            if stage.get("hold"):
                self.log("[✓] Holding pressure after stage.")
                # no-op if controller naturally holds
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

    def finish(self):
        self.running = False
        self.timer.stop()
        self.log("[✓] Triaxial test complete.")
        self.test_finished.emit()
        self._save_log_to_csv()

    def abort(self):
        self.running = False
        self.timer.stop()
        self.log("[✗] Test aborted.")
        self.test_finished.emit()

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
