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

class StationConfigPage(QWidget):
    def __init__(self, main_window, log=print):
        super().__init__()
        self.main_window = main_window
        self.log = log
        self.connected_devices = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # --- Add Device Bar ---
        top_bar = QHBoxLayout()
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(["Select Device Type", "Load Frame", "Pressure Controller", "SerialPad"])
        self.device_model_combo = QComboBox()
        self.device_model_combo.addItems(["Select Model", "LF50", "STDDPC v2", "SerialPad"])

        self.add_device_btn = QPushButton("+ Add Device")
        self.add_device_btn.clicked.connect(self.add_device)

        top_bar.addWidget(self.device_type_combo)
        top_bar.addWidget(self.device_model_combo)
        top_bar.addWidget(self.add_device_btn)
        layout.addLayout(top_bar)

        # --- Device Display Area ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.device_container = QWidget()
        self.device_layout = QVBoxLayout(self.device_container)
        self.device_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.device_container)
        layout.addWidget(self.scroll_area)

    def claimed_serials(self):
        serials = []
        for ctrl in self.connected_devices.values():
            if hasattr(ctrl, 'serial'):
                serials.append(ctrl.serial)
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

    @staticmethod
    def find_serialpad_com_port(log=print):
        """Try each available COM port to auto-detect SerialPad."""
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
                if line.lstrip('+-').isdigit():  # SerialPad returns raw ADC values (numbers)
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

        # --- Handle SerialPad ---
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
                card = self.create_device_card(model, f"Connected on {port_to_use} ✅")
                self.device_layout.addWidget(card)
                if self.main_window.setup_page:
                    self.main_window.setup_page.update_device_status()
            except Exception as e:
                self.log(f"[✗] Failed to connect SerialPad on {port_to_use}: {e}")
            return

        # --- Handle FTDI-based devices (LF50, STDDPC) ---

        keyword = "LF50" if "LF50" in model else "STDDPC"
        usb_dev = self.find_ftdi_by_product(keyword, exclude_serials=self.claimed_serials())
        if not usb_dev:
            self.log(f"[✗] No {keyword} device found. Make sure it's plugged in.")
            return

        try:
            if "LF50" in model:
                controller = LoadFrameController(log=self.log)
            elif "STDDPC" in model:
                controller = STTDPCController(log=self.log)
            else:
                self.log("Unknown controller type.")
                return

            success = controller.connect(usb_device=usb_dev)
            if not success:
                self.log(f"[✗] Failed to connect {role}.")
                return

            if "LF50" in model:
                self.main_window.lf_controller = controller
            elif "STDDPC" in model:
                self.main_window.sttdpc_controller = controller

            self.connected_devices[role] = controller
            self.log(f"[✓] {role} connected successfully.")
            card = self.create_device_card(model, "Connected ✅")
            self.device_layout.addWidget(card)

            if self.main_window.manual_page:
                self.main_window.manual_page.lf_controller = self.main_window.lf_controller
                self.main_window.manual_page.sttdpc_controller = self.main_window.sttdpc_controller

            if self.main_window.setup_page:
                self.main_window.setup_page.update_device_status()

        except Exception as e:
            self.log(f"[✗] Exception while connecting {role}: {e}")

    def create_device_card(self, name: str, status: str):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        name_label = QLabel(f"<b>{name}</b>")
        status_label = QLabel(f"Status: {status}")

        layout.addWidget(name_label)
        layout.addWidget(status_label)

        box.setStyleSheet("""
            QWidget {
                border: 1px solid #ccc;
                border-radius: 6px;
                background-color: #f4f4f4;
            }
        """)
        return box

    def update_com_port_visibility(self, model):
        is_serialpad = "SerialPad" in model
        self.com_port_combo.setEnabled(not is_serialpad)
