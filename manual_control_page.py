from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QLineEdit

class ManualControlPage(QWidget):
    def __init__(self, lf_controller=None, sttdpc_controller=None, log=print):
        super().__init__()
        self.lf_controller = lf_controller
        self.sttdpc_controller = sttdpc_controller
        self.log = log
        self.init_ui()

        self.axial_input = None
        self.pressure_input = None

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Manual Control Page"))

        # Axial Movement Control
        if self.lf_controller:
            layout.addWidget(QLabel("Axial Position (mm):"))
            self.axial_input = QLineEdit()
            move_btn = QPushButton("Send Axial Position")
            move_btn.clicked.connect(self.send_axial_position)
            layout.addWidget(self.axial_input)
            layout.addWidget(move_btn)

        # Pressure Control
        if self.sttdpc_controller:
            layout.addWidget(QLabel("Target Pressure (kPa):"))
            self.pressure_input = QLineEdit()
            pressure_btn = QPushButton("Send Pressure")
            pressure_btn.clicked.connect(self.send_pressure)
            layout.addWidget(self.pressure_input)
            layout.addWidget(pressure_btn)

        self.setLayout(layout)

        # UI logic is now decoupled from controller presence
        # Buttons still appear but check for controller before acting

    def send_axial_position(self):
        if not self.lf_controller:
            self.log("[✗] Load Frame controller not connected.")
            return
        try:
            mm = float(self.axial_input.text())
            self.lf_controller.send_displacement(mm)
        except Exception as e:
            self.log(f"[✗] Failed to send axial movement: {e}")
            
    def send_pressure(self):
        if not self.sttdpc_controller or not self.pressure_input:
            self.log("[✗] Pressure Controller not available.")
            return
        try:
            kpa = float(self.pressure_input.text())
            self.sttdpc_controller.send_pressure(kpa)
        except Exception as e:
            self.log(f"[✗] Failed to send pressure command: {e}")
