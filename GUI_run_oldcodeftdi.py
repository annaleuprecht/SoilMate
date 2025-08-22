import os
import sys
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QListWidget, QListWidgetItem,
    QComboBox, QTextEdit, QGroupBox, QFormLayout, QLineEdit, QMessageBox, QInputDialog
)
from PyQt5.QtCore import Qt, QSize, QMetaObject, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont, QIcon, QPixmap, QGuiApplication
from device_controllers.loadframe import LoadFrameController
from device_controllers.lf50_movement import LF50Mover
from device_controllers.sttdpc_controller import STTDPCController
from station_config_page import StationConfigPage
from manual_control_page import ManualControlPage
from calibration_wizard import CalibrationManager
from data_view_page import DataViewPage
from device_controllers.serial_pad_reader import SerialPadReader  # You’ll need to create this class next
from triaxial_test_manager import TriaxialTestManager
from test_set_up_page import TestSetupPage
from test_view_page import TestViewPage
from device_settings_page import DeviceSettingsPage
from calibration_popup import CalibrationInputDialog


class HomePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)
        self.setLayout(layout)

        title = QLabel("Welcome to SoilMate v2025")
        title.setStyleSheet("font-size: 22pt; font-weight: bold;")
        layout.addWidget(title)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        btn_layout.setAlignment(Qt.AlignCenter)

        self.prev_tests_button = QPushButton("Previous Tests")
        self.new_test_button = QPushButton("New Test")
        btn_layout.addWidget(self.prev_tests_button)
        btn_layout.addWidget(self.new_test_button)

        layout.addLayout(btn_layout)


    def connect_loadframe(self):
        try:
            usb_dev = self.get_next_unclaimed_ftdi()
            if not usb_dev:
                self.status_label.setText("Status: No unclaimed FTDI devices")
                return

            success = self.lf_controller.connect(usb_device=usb_dev)
            self.status_label.setText("Status: Connected" if success else "Status: Failed")

            if success and self.main_window.manual_page is None:
                self.main_window.manual_page = ManualControlPage(lf_device=self.lf_controller.device)
                self.main_window.stack.insertWidget(4, self.main_window.manual_page)

        except Exception as e:
            self.status_label.setText("Status: Error")
            self.log_area.append(f"[Exception] {repr(e)}")

    def connect_pressure_controller(self):
        self.log_message("[*] Connecting to STTDPC pressure controller...")

        usb_dev = self.get_next_unclaimed_ftdi()
        if not usb_dev:
            self.log_message("[✗] No unclaimed FTDI devices.")
            return

        controller = STTDPCController(log=self.log_message, calibration_manager=self.main_window.calibration_manager)
        success = controller.connect(usb_dev)

        if success:
            serial = controller.serial
            self.log_message(f"[✓] Pressure controller connected (Serial: {serial})")

            # Assign to cell or back depending on what's already set
            if not self.main_window.cell_pressure_controller:
                self.main_window.cell_pressure_controller = controller
                self.log_message(f"[✓] Assigned as Cell Pressure Controller.")
            elif not self.main_window.back_pressure_controller:
                self.main_window.back_pressure_controller = controller
                self.log_message(f"[✓] Assigned as Back Pressure Controller.")
            else:
                self.log_message(f"[!] Both controllers already connected. Extra device not assigned.")
        else:
            self.log_message("[✗] Failed to connect pressure controller.")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoilMate v2025")
        self.setGeometry(100, 100, 1000, 600)

        self.lf_controller = None
        self.back_pressure_controller = None
        self.cell_pressure_controller = None
        self.serial_pad = None
        self.manual_page = None
        self.test_manager = None

        self.setStyleSheet("""
            QWidget {
                font-family: 'Segoe UI', sans-serif;
                font-size: 16px;
                background-color: #f9f9f9;
            }
            QListWidget {
                background-color: #f0f0f0;
                border: none;
            }
            QListWidget::item {
                padding: 12px;
                font-size: 16px;
            }
            QListWidget::item:selected {
                background-color: #d0d0d0;
                border-left: 4px solid #2a82da;
            }
            QPushButton {
                background-color: white;
                border: 1px solid #ccc;
                padding: 8px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e6f0ff;
            }
            QLabel {
                color: #333;
            }
        """)

        central_widget = QWidget()
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)  # only called once

        self.sidebar = QListWidget()
        self.sidebar.setIconSize(QSize(24, 24))

        home_icon = QIcon("icons/house.png")
        wrench_icon = QIcon("icons/wrench.png")
        clipboard_icon = QIcon("icons/clipboard-list.png")
        chart_icon = QIcon("icons/chart-spline.png")
        terminal_icon = QIcon("icons/terminal.png")
        move_icon = QIcon("icons/move.png")
        data_view_icon = QIcon("icons/message-square-text.png")
        data_settings_icon = QIcon("icons/settings.png")

        self.sidebar.addItem(QListWidgetItem(home_icon, "Dashboard"))
        self.sidebar.addItem(QListWidgetItem(wrench_icon, "Station Configuration"))
        self.sidebar.addItem(QListWidgetItem(clipboard_icon, "Test Set Up"))
        self.sidebar.addItem(QListWidgetItem(chart_icon, "Test View"))
        self.sidebar.addItem(QListWidgetItem(move_icon, "Manual Control"))
        self.sidebar.addItem(QListWidgetItem(data_view_icon, "Data View"))
        self.sidebar.addItem(QListWidgetItem(data_settings_icon, "Device Settings"))

        self.sidebar.setFixedWidth(210)
        main_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        self.calibration_manager = CalibrationManager(
            serialpad_dir="calibration/serial_pad",
            pressure_json_path="calibration/stddpc/pressure_calibrations.json",
            log=self.log
        )
        self.home_page = HomePage()
        self.config_page = StationConfigPage(log=self.log)
        self.setup_page = TestSetupPage(device_checker=self._check_devices)
        self.setup_page.start_test_requested.connect(self.start_test)
        self.device_settings_page = DeviceSettingsPage()
        self.device_settings_page.populate_devices(
            self._list_devices(), select=self._current_device_name()
        )

        self.config_page.config_changed.connect(lambda cfg: self.log(f"[config] {cfg}"))

        self.stack.addWidget(self.config_page)


        self.manual_page = ManualControlPage()

        # Route Manual page actions to your real controllers
        self.manual_page.send_axial_position_requested.connect(self._set_axial_position)
        self.manual_page.send_axial_velocity_requested.connect(self._set_axial_velocity)
        self.manual_page.stop_axial_requested.connect(self._stop_axial)

        self.manual_page.send_cell_pressure_requested.connect(self._set_cell_pressure)
        self.manual_page.stop_cell_pressure_requested.connect(self._stop_cell_pressure)

        self.manual_page.send_back_pressure_requested.connect(self._set_back_pressure)
        self.manual_page.stop_back_pressure_requested.connect(self._stop_back_pressure)

        # Initial enable/disable based on current connection state
        self.manual_page.set_axial_enabled(self._is_connected(self.lf_controller))
        self.manual_page.set_cell_enabled(self._is_connected(self.cell_pressure_controller))
        self.manual_page.set_back_enabled(self._is_connected(self.back_pressure_controller))

        # Wire actions
        self.device_settings_page.refresh_devices_requested.connect(
            lambda: self.device_settings_page.populate_devices(
                self._list_devices(), select=self._current_device_name()
            )
        )

        self.device_settings_page.save_device_requested.connect(
            lambda name: self._select_device(name)
        )

        self.device_settings_page.apply_limits_requested.connect(
            lambda lo, hi: self._apply_pressure_limits(lo, hi)
        )

        self.data_view_page = DataViewPage(self.calibration_manager, log=self.config_page.log)
        self.view_page = TestViewPage([], main_window=self)

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.config_page)
        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.view_page)  # now permanent and indexed correctly
        self.stack.addWidget(self.manual_page)
        self.stack.addWidget(self.data_view_page)
        self.stack.addWidget(self.device_settings_page)

        self.sidebar.currentRowChanged.connect(self.display_page)
        self.sttdpc_controller = None

        QTimer.singleShot(0, self._fit_to_screen)

    def _fit_to_screen(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        min_w, min_h = 1000, 650
        w = min(max(min_w, self.width()),  screen.width())
        h = min(max(min_h, self.height()), screen.height())
        self.resize(w, h)
        x = max(screen.left(),  min(self.x(), screen.right()  - w))
        y = max(screen.top(),   min(self.y(), screen.bottom() - h))
        self.move(x, y)

    def _is_connected(self, dev) -> bool:
        if not dev:
            return False
        for attr in ("is_ready", "is_connected", "isConnected", "connected"):
            val = getattr(dev, attr, None)
            try:
                return bool(val() if callable(val) else val)
            except Exception:
                pass
        return True  # fallback: treat existing object as connected

    # --- Axial (load frame) ---
    def _set_axial_position(self, mm: float):
        dev = self.lf_controller
        if not dev: return
        for name in ("set_axial_position", "set_target_position", "move_to"):
            if hasattr(dev, name):
                getattr(dev, name)(mm); return

    def _set_axial_velocity(self, mm_min: float):
        dev = self.lf_controller
        if not dev: return
        for name in ("set_axial_velocity", "set_target_velocity", "jog"):
            if hasattr(dev, name):
                getattr(dev, name)(mm_min); return

    def _stop_axial(self):
        dev = self.lf_controller
        if not dev: return
        for name in ("stop_axial", "stop", "halt"):
            if hasattr(dev, name):
                getattr(dev, name)(); return

    # --- Cell pressure ---
    def _set_cell_pressure(self, kpa: float):
        dev = self.cell_pressure_controller
        if not dev: return
        for name in ("set_pressure", "set_target_pressure", "set_cell_pressure"):
            if hasattr(dev, name):
                getattr(dev, name)(kpa); return

    def _stop_cell_pressure(self):
        dev = self.cell_pressure_controller
        if not dev: return
        for name in ("stop", "stop_pressure", "abort"):
            if hasattr(dev, name):
                getattr(dev, name)(); return

    # --- Back pressure ---
    def _set_back_pressure(self, kpa: float):
        dev = self.back_pressure_controller
        if not dev: return
        for name in ("set_pressure", "set_target_pressure", "set_back_pressure"):
            if hasattr(dev, name):
                getattr(dev, name)(kpa); return

    def _stop_back_pressure(self):
        dev = self.back_pressure_controller
        if not dev: return
        for name in ("stop", "stop_pressure", "abort"):
            if hasattr(dev, name):
                getattr(dev, name)(); return


    # --- MainWindow helpers (put inside the class) -------------------------------
    def _list_devices(self):
        if self.serial_pad:
            return self.serial_pad.list_devices()
        if hasattr(self.calibration_manager, "list_devices"):
            return self.calibration_manager.list_devices()
        return []

    def _current_device_name(self):
        if self.serial_pad and hasattr(self.serial_pad, "current_device_name"):
            return self.serial_pad.current_device_name()
        if hasattr(self.calibration_manager, "current_device_name"):
            return self.calibration_manager.current_device_name()
        return ""


    def _select_device(self, name: str):
        for obj_attr in ("serialpad", "calibration_manager"):
            obj = getattr(self, obj_attr, None)
            if obj and hasattr(obj, "select_device"):
                obj.select_device(name)
                return True
        return False

    def _apply_pressure_limits(self, lo: float, hi: float):
        # point this to wherever you set limits
        if hasattr(self, "pressure") and hasattr(self.pressure, "set_limits"):
            self.pressure.set_limits(lo, hi)
            return True
        if hasattr(self, "calibration_manager") and hasattr(self.calibration_manager, "set_pressure_limits"):
            self.calibration_manager.set_pressure_limits(lo, hi)
            return True
        return False


    def _check_devices(self):
        required = {
            "Cell-pressure Controller": self.cell_pressure_controller,
            "Back-pressure Controller": self.back_pressure_controller,
            "Load Frame": self.lf_controller,
            "Serial Pad": self.serial_pad,
        }
        problems = []
        for name, dev in required.items():
            if dev is None:
                problems.append(f"{name} (not initialized)")
                continue
            ok = None
            for attr in ("is_ready", "is_connected", "isConnected", "connected"):
                if hasattr(dev, attr):
                    try:
                        v = getattr(dev, attr)
                        ok = v() if callable(v) else bool(v)
                    except Exception as e:
                        problems.append(f"{name} check error: {e}")
                        ok = False
                    break
            if ok is None:
                problems.append(f"{name} (no status API)")
            elif ok is False:
                problems.append(f"{name} not ready")
        return (False, " • " + "\n • ".join(problems)) if problems else (True, "")



    def display_page(self, index):
        self.stack.setCurrentIndex(index)

    def handle_live_reading(self, reading):
        self.log(f"[Data] {reading}")
        print("[DEBUG] Got reading:", reading)
        print("[DEBUG] Keys:", list(reading.keys()))

        self.view_page.shared_data = reading
        self.view_page.update_plot(reading)

    def start_test(self, _):
        print("[DEBUG] MainWindow.start_test() called")

        # Prompt user for any missing pressure values (on GUI thread)
        for stage_data in self.setup_page.stage_data_list:
            if stage_data.stage_type in ("Saturation", "Shear"):
                if not hasattr(stage_data, "current_cell_pressure"):
                    val, ok = QInputDialog.getDouble(None, "Current Cell Pressure", "Enter current cell pressure (kPa):", 0, 0, 1000, 1)
                    if not ok:
                        self.log("[✗] Test cancelled by user.")
                        return
                    stage_data.current_cell_pressure = val

                if not hasattr(stage_data, "current_back_pressure"):
                    val, ok = QInputDialog.getDouble(None, "Current Back Pressure", "Enter current back pressure (kPa):", 0, 0, 1000, 1)
                    if not ok:
                        self.log("[✗] Test cancelled by user.")
                        return
                    stage_data.current_back_pressure = val

        self.view_page.start_time = time.time()
        self.view_page.load_stages(self.setup_page.stage_data_list)

        if not (self.lf_controller and self.cell_pressure_controller and self.back_pressure_controller and self.serial_pad):
            self.log("[✗] All devices must be connected before starting a test.")
            return

        test_config = {
            "stages": self.setup_page.stage_data_list
        }

        self.test_manager = TriaxialTestManager(
            lf_controller=self.lf_controller,
            cell_pressure_controller=self.cell_pressure_controller,
            back_pressure_controller=self.back_pressure_controller,
            serial_pad=self.serial_pad,
            test_config=test_config,
            log=self.log
        )

        self.test_manager.stage_changed.connect(lambda name: self.log(f"[Stage] {name}"))
        self.test_manager.reading_updated.connect(self.handle_live_reading)
        self.test_manager.test_finished.connect(lambda: self.log("[✓] Test finished!"))

        self.stack.setCurrentWidget(self.view_page)
        self.sidebar.setCurrentRow(3)  # Index 3 = "Test View"
        self.view_page.add_graph()

        self.test_manager.start()

    def advance_to_next_stage(self):
        if self.test_manager:
            self.test_manager.next_stage()

    def stop_current_stage(self):
        if self.test_manager:
            self.test_manager.stop_stage()


    def log(self, message):
        print(message)
        if message.startswith("[✗]") or "please select" in message.lower():
            QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Error", message))

if __name__ == "__main__":
    import traceback
    try:
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception:
        print("Exception on startup:")
        traceback.print_exc()
