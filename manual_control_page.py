from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, QGroupBox
)
import time

class ManualControlPage(QWidget):
    def __init__(self, lf_controller=None, back_pressure_controller=None, cell_pressure_controller=None, log=print):
        super().__init__()
        self.lf_controller = lf_controller
        self.back_pressure_controller = back_pressure_controller
        self.cell_pressure_controller = cell_pressure_controller
        self.log = log

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        layout.addWidget(self.create_axial_position_box())
        layout.addWidget(self.create_cell_pressure_box())
        layout.addWidget(self.create_back_pressure_box())
        layout.addWidget(self.create_volume_box())

        self.setLayout(layout)

    def set_controllers(self, lf=None, back=None, cell=None):
        if lf:
            self.lf_controller = lf
        if back:
            self.back_pressure_controller = back
        if cell:
            self.cell_pressure_controller = cell

        self.refresh_status_labels()  # <== Trigger UI update

    def create_axial_position_box(self):
        group = QGroupBox("Axial Position (Load Frame)")
        vbox = QVBoxLayout()

        self.lf_status = QLabel("❌ Not Connected")
        if self.lf_controller:
            self.lf_status.setText("✅ Connected")

        self.axial_input = QLineEdit()
        self.axial_input.setPlaceholderText("Enter target position (mm)")
        send_btn = QPushButton("Send Axial Command")
        send_btn.clicked.connect(self.send_axial_position)

        stop_btn = QPushButton("Stop Load Frame")
        stop_btn.clicked.connect(self.stop_lf50)

        vbox.addWidget(self.lf_status)
        vbox.addWidget(QLabel("Target Position:"))
        vbox.addWidget(self.axial_input)
        vbox.addWidget(send_btn)
        vbox.addWidget(stop_btn)

        group.setLayout(vbox)
        return group

    def create_cell_pressure_box(self):
        group = QGroupBox("Cell Pressure Control (STDDPC)")
        vbox = QVBoxLayout()

        self.cell_pressure_status = QLabel("❌ Not Connected")
        if self.cell_pressure_controller:
            self.cell_pressure_status.setText("✅ Connected")

        self.cell_pressure_input = QLineEdit()
        self.cell_pressure_input.setPlaceholderText("Enter target pressure (kPa)")
        send_btn = QPushButton("Send Cell Pressure")
        send_btn.clicked.connect(self.send_cell_pressure)

        stop_btn = QPushButton("Stop Cell Pressure")
        stop_btn.clicked.connect(self.stop_cell_pressure)

        vbox.addWidget(self.cell_pressure_status)
        vbox.addWidget(QLabel("Target Pressure:"))
        vbox.addWidget(self.cell_pressure_input)
        vbox.addWidget(send_btn)
        vbox.addWidget(stop_btn)

        group.setLayout(vbox)
        return group

    def create_back_pressure_box(self):
        group = QGroupBox("Back Pressure Control (STDDPC)")
        vbox = QVBoxLayout()

        self.back_pressure_status = QLabel("❌ Not Connected")
        if self.back_pressure_controller:
            self.back_pressure_status.setText("✅ Connected")

        self.back_pressure_input = QLineEdit()
        self.back_pressure_input.setPlaceholderText("Enter target pressure (kPa)")
        send_btn = QPushButton("Send Back Pressure")
        send_btn.clicked.connect(self.send_back_pressure)

        stop_btn = QPushButton("Stop Back Pressure")
        stop_btn.clicked.connect(self.stop_back_pressure)

        vbox.addWidget(self.back_pressure_status)
        vbox.addWidget(QLabel("Target Pressure:"))
        vbox.addWidget(self.back_pressure_input)
        vbox.addWidget(send_btn)
        vbox.addWidget(stop_btn)

        group.setLayout(vbox)
        return group

    def create_volume_box(self):
        group = QGroupBox("Volume Control (via Cell Pressure Controller)")
        vbox = QVBoxLayout()

        self.volume_input = QLineEdit()
        self.volume_input.setPlaceholderText("Enter target volume (mm³)")
        send_btn = QPushButton("Send Volume")
        send_btn.clicked.connect(self.send_volume)

        vbox.addWidget(QLabel("Target Volume:"))
        vbox.addWidget(self.volume_input)
        vbox.addWidget(send_btn)

        group.setLayout(vbox)
        return group

    # --- SEND Methods ---
    def send_axial_position(self):
        if not self.lf_controller:
            self.log("[✗] Load Frame not connected.")
            return
        try:
            mm = float(self.axial_input.text())
            self.lf_controller.send_displacement(mm)
            self.axial_input.clear()  # Always clear after attempt (or only if no error, up to you)
        except Exception as e:
            self.log(f"[✗] Failed to send axial command: {e}")

    def send_cell_pressure(self):
        if not self.cell_pressure_controller:
            self.log("[✗] Cell Pressure Controller not connected.")
            return
        try:
            kpa = float(self.cell_pressure_input.text())
            self.cell_pressure_controller.send_pressure(kpa)
            self.cell_pressure_input.clear()
        except Exception as e:
            self.log(f"[✗] Failed to send cell pressure: {e}")

    def send_back_pressure(self):
        if not self.back_pressure_controller:
            self.log("[✗] Back Pressure Controller not connected.")
            return
        try:
            kpa = float(self.back_pressure_input.text())
            self.back_pressure_controller.send_pressure(kpa)
            self.back_pressure_input.clear()
        except Exception as e:
            self.log(f"[✗] Failed to send back pressure: {e}")

    def send_volume(self):
        if not self.cell_pressure_controller:
            self.log("[✗] Cell Pressure Controller not connected (for volume).")
            return
        try:
            mm3 = float(self.volume_input.text())
            self.cell_pressure_controller.send_volume(mm3)
            self.volume_input.clear()
        except Exception as e:
            self.log(f"[✗] Failed to send volume command: {e}")

    # --- STOP Methods ---
    def stop_lf50(self):
        if self.lf_controller:
            try:
                self.lf_controller.stop()
                self.log("[✓] Stopped LF50 load frame.")
            except Exception as e:
                self.log(f"[✗] Error stopping LF50: {e}")

    def stop_cell_pressure(self):
        if self.cell_pressure_controller:
            try:
                self.cell_pressure_controller.stop()
                self.log("[✓] Stopped Cell Pressure Controller.")
            except Exception as e:
                self.log(f"[✗] Error stopping Cell Pressure Controller: {e}")

    def stop_back_pressure(self):
        if self.back_pressure_controller:
            try:
                self.back_pressure_controller.stop()
                self.log("[✓] Stopped Back Pressure Controller.")
            except Exception as e:
                self.log(f"[✗] Error stopping Back Pressure Controller: {e}")

    def refresh_status_labels(self):
        self.lf_status.setText("✅ Connected" if self.lf_controller else "❌ Not Connected")
        self.cell_pressure_status.setText("✅ Connected" if self.cell_pressure_controller else "❌ Not Connected")
        self.back_pressure_status.setText("✅ Connected" if self.back_pressure_controller else "❌ Not Connected")

