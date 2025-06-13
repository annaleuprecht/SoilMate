import os
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QListWidget, QListWidgetItem,
    QComboBox, QTextEdit, QGroupBox, QFormLayout, QLineEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QSize, QMetaObject, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap
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

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

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
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

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
        self.calibration_manager = CalibrationManager(
            serialpad_dir="calibration/serial_pad",
            pressure_json_path="calibration/stddpc/pressure_calibrations.json",
            log=self.log
        )
        self.home_page = HomePage()
        self.config_page = StationConfigPage(self, log=self.log)
        self.setup_page = TestSetupPage(self)
        self.view_page = TestViewPage()
        self.manual_page = ManualControlPage(
            lf_controller=self.lf_controller,
            back_pressure_controller=self.back_pressure_controller,
            cell_pressure_controller=self.cell_pressure_controller,
            log=self.log
        )
        self.data_view_page = DataViewPage(self.calibration_manager, log=self.config_page.log)
        self.device_settings_page = DeviceSettingsPage(self.calibration_manager, log=self.log)

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.config_page)
        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.view_page)
        self.stack.addWidget(self.manual_page)
        self.stack.addWidget(self.data_view_page)
        self.stack.addWidget(self.device_settings_page)

        main_layout.addWidget(self.stack)
        self.sidebar.currentRowChanged.connect(self.display_page)
        self.sttdpc_controller = None

    def display_page(self, index):
        self.stack.setCurrentIndex(index)


    def start_test(self, test_config):
        if not (self.lf_controller and self.cell_pressure_controller and self.back_pressure_controller and self.serial_pad):
            self.log("[✗] All devices must be connected before starting a test.")
            return

        self.test_manager = TriaxialTestManager(
            lf_controller=self.lf_controller,
            cell_pressure_controller=self.cell_pressure_controller,
            back_pressure_controller=self.back_pressure_controller,
            serial_pad=self.serial_pad,
            test_config=test_config,
            log=self.log
        )
        self.test_manager.stage_changed.connect(lambda name: self.log(f"[Stage] {name}"))
        self.test_manager.reading_updated.connect(lambda data: self.log(f"[Data] {data}"))
        self.test_manager.test_finished.connect(lambda: self.log("[✓] Test finished!"))

        self.test_manager.start()

    def log(self, message):
        print(message)

        if message.startswith("[✗]") or "please select" in message.lower():
            # Delay message box to ensure it runs on the main thread
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
