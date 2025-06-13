import usb.core
import usb.util
import time
import serial.tools.list_ports
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QPushButton,
    QComboBox, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt
from device_controllers.sttdpc_controller import STTDPCController
from device_controllers.loadframe import LoadFrameController
from device_controllers.serial_pad_reader import SerialPadReader
from manual_control_page import ManualControlPage
from ftdi_device_manager import FtdiDeviceManager
from calibration_wizard import CalibrationManager
from calibration_popup import CalibrationInputDialog

class StationConfigPage(QWidget):
    def __init__(self, main_window, log=print):
        super().__init__()
        self.main_window = main_window
        self.log = log
        self.calibration_manager = main_window.calibration_manager
        self.connected_devices = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # --- Device Type ---
        device_type_section = QWidget()
        device_type_layout = QVBoxLayout(device_type_section)
        device_type_layout.setContentsMargins(0, 0, 0, 0)
        device_type_layout.setSpacing(0)
        device_type_layout.addWidget(QLabel("Device Type"))
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems([
            "Select Device Type",
            "Load Frame",
            "Back Pressure Controller",
            "Cell Pressure Controller",
            "SerialPad"
        ])
        device_type_layout.addWidget(self.device_type_combo)

        # --- Model ---
        model_section = QWidget()
        model_layout = QVBoxLayout(model_section)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(0)
        model_layout.addWidget(QLabel("Model"))
        self.device_model_combo = QComboBox()
        self.device_model_combo.addItem("Select Model")
        model_layout.addWidget(self.device_model_combo)

        # --- Serial ---
        self.serial_section = QWidget()
        serial_layout = QVBoxLayout(self.serial_section)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(0)
        serial_layout.addWidget(QLabel("Serial Number"))
        self.serial_combo = QComboBox()
        self.serial_combo.addItem("Select Serial")
        serial_layout.addWidget(self.serial_combo)
        self.serial_section.setVisible(False)  # hide by default

        self.device_type_combo.setFixedWidth(200)
        self.device_model_combo.setFixedWidth(200)
        self.serial_combo.setFixedWidth(200)
        
        # --- Connect serial visibility signal
        self.device_model_combo.currentTextChanged.connect(self.update_serial_visibility)
        self.device_type_combo.currentTextChanged.connect(self.update_model_options)
        self.add_device_btn = QPushButton("+ Add Device")
        self.add_device_btn.clicked.connect(self.add_device)

        # -- Top Bar --
        top_bar = QHBoxLayout()
        layout.addLayout(top_bar)
        top_bar.addWidget(device_type_section)
        top_bar.addWidget(model_section)
        top_bar.addWidget(self.serial_section)
        top_bar.addStretch()
        top_bar.addWidget(self.add_device_btn)

        # --- Device Display Area ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.device_container = QWidget()
        self.device_layout = QVBoxLayout(self.device_container)
        self.device_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.device_container)
        layout.addWidget(self.scroll_area)

    def update_model_options(self, device_type):
        self.device_model_combo.clear()
        self.device_model_combo.addItem("Select Model")
        self.serial_section.setVisible(False)

        if device_type == "Load Frame":
            self.device_model_combo.addItem("LF50")
        elif device_type in ["Back Pressure Controller", "Cell Pressure Controller"]:
            self.device_model_combo.addItem("STDDPC v2")
        elif device_type == "SerialPad":
            self.device_model_combo.addItem("SerialPad")

    def update_serial_visibility(self, model_text):
        if model_text in ["LF50", "STDDPC v2"]:
            self.serial_section.setVisible(True)
            self.refresh_serial_list()
        else:
            self.serial_section.setVisible(False)
            self.serial_combo.clear()
            self.serial_combo.addItem("Select Serial")

    def claimed_serials(self):
        serials = []
        for ctrl in self.connected_devices.values():
            if hasattr(ctrl, 'serial'):
                serials.append(ctrl.serial)

        if not serials:
            self.serial_combo.addItem("No devices found")
            return
        return serials

    def find_ftdi_by_product(self, keyword, exclude_serials=None):
        exclude_serials = exclude_serials or []
        devices = usb.core.find(find_all=True, idVendor=0x0403, idProduct=0x6001)
        for dev in devices:
            try:
                product = usb.util.get_string(dev, dev.iProduct)
                serial = usb.util.get_string(dev, dev.iSerialNumber)
                if serial in exclude_serials:
                    continue
                if keyword.lower() in product.lower():
                    return dev
            except Exception:
                continue
        return None

    def refresh_serial_list(self):
        self.serial_combo.clear()
        mgr = FtdiDeviceManager(log=self.log)
        serials = mgr.list_serials()

        if not serials:
            self.serial_combo.addItem("No devices found")
            return

        self.serial_combo.addItem("Select Serial")
        for serial in serials:
            if serial.strip():
                self.serial_combo.addItem(serial)

    @staticmethod
    def find_serialpad_com_port(log=print):
        ports = serial.tools.list_ports.comports()
        log(f"[?] Scanning {len(ports)} available COM ports...")
        for port_info in ports:
            port = port_info.device
            log(f"[?] Trying {port}...")
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=4800,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_TWO,
                    timeout=1
                )
                ser.write(b'SS\r\n')
                time.sleep(0.2)
                line = ser.readline().decode(errors='ignore').strip()
                ser.close()
                log(f"[?] Response from {port}: '{line}'")
                if line.lstrip('+-').isdigit():
                    log(f"[✓] Auto-detected SerialPad on {port}")
                    return port
            except Exception as e:
                log(f"[!] Exception trying {port}: {e}")
                continue
        return None

    def add_device(self):
        role = self.device_type_combo.currentText()
        model = self.device_model_combo.currentText()

        if role == "Select Device Type" or model == "Select Model":
            self.log("[✗] Please select device type and model.")
            return

        if role in self.connected_devices:
            self.log(f"[✗] {role} already connected.")
            return

        if "SerialPad" in model:
            port_to_use = self.find_serialpad_com_port(self.log)
            if not port_to_use:
                self.log("[✗] Could not auto-detect SerialPad COM port.")
                return
            try:
                controller = SerialPadReader(
                    port=port_to_use,
                    calibration=self.main_window.calibration_manager,
                    log=self.log
                )
                self.main_window.serial_pad = controller
                self.main_window.data_view_page.set_serial_pad(controller)
                self.connected_devices[role] = controller
                self.log(f"[✓] SerialPad connected successfully on {port_to_use}")
                card = self.create_device_card(model, f"Connected on {port_to_use} ✅", extra_details=[f"Port: {port_to_use}", "Role: SerialPad"])
                self.device_layout.addWidget(card)
                if self.main_window.setup_page:
                    self.main_window.setup_page.update_device_status()
            except Exception as e:
                self.log(f"[✗] Failed to connect SerialPad on {port_to_use}: {e}")
            return

        mgr = FtdiDeviceManager(log=self.log)
        selected_serial = self.serial_combo.currentText().strip()
        if not selected_serial.startswith("GDS"):
            self.log("[✗] Please select a valid device serial before connecting.")
            return

        dev = mgr.open_by_serial(selected_serial)
        if not dev:
            self.log(f"[✗] Failed to open device {selected_serial}.")
            return

        try:
            if "LF50" in model:
                controller = LoadFrameController(log=self.log)
                success = controller.connect(ftdi_device=dev)
                self.main_window.lf_controller = controller

            elif "STDDPC" in model:
                try:
                    self.calibration_manager.get_pressure_calibration(selected_serial)
                except ValueError:
                    dialog = CalibrationInputDialog(serial=selected_serial)
                    if dialog.exec_():
                        values = dialog.get_values()
                        self.calibration_manager.set_pressure_calibration(selected_serial, values)
                        self.log(f"[✓] Calibration saved for {selected_serial}")
                    else:
                        self.log("[✗] Calibration cancelled.")
                        return

                controller = STTDPCController(log=self.log, calibration_manager=self.calibration_manager)
                success = controller.connect(dev)
                if not success:
                    self.log("[✗] STTDPC connect() failed — aborting.")
                    return

                if role == "Back Pressure Controller":
                    self.main_window.back_pressure_controller = controller
                elif role == "Cell Pressure Controller":
                    self.main_window.cell_pressure_controller = controller

            else:
                self.log("Unknown controller type.")
                return

            self.connected_devices[role] = controller
            self.log(f"[✓] {role} connected successfully.")
            card = self.create_device_card(model, "Connected ✅")
            self.device_layout.addWidget(card)

            if self.main_window.manual_page:
                self.main_window.manual_page.set_controllers(
                    lf=self.main_window.lf_controller,
                    back=self.main_window.back_pressure_controller,
                    cell=self.main_window.cell_pressure_controller
                )

            if self.main_window.setup_page:
                self.main_window.setup_page.update_device_status()

        except Exception as e:
            self.log(f"[✗] Exception while connecting {role}: {e}")

    def create_device_card(self, name: str, status: str, extra_details=None):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        name_label = QLabel(f"<b>{name}</b>")
        details = extra_details or []

        if hasattr(self, "serial_combo"):
            serial = self.serial_combo.currentText().strip()
            if serial.startswith("GDS") and "Serial" not in ''.join(details):
                details.append(f"Serial: {serial}")

        role = self.device_type_combo.currentText()
        if role != "Select Device Type":
            details.append(f"Role: {role}")

        status_label = QLabel(f"Status: {status}<br>{'<br>'.join(details)}")

        layout.addWidget(name_label)
        layout.addWidget(status_label)

        box.setStyleSheet("""
            QWidget {
                border: 1px solid #ccc;
                border-radius: 6px;
                background-color: #e8f5e9;
                padding: 10px;
            }
            QLabel {
                font-size: 13px;
            }
        """)
        return box

    def update_com_port_visibility(self, model):
        is_serialpad = "SerialPad" in model
        self.com_port_combo.setEnabled(not is_serialpad)
