from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
)

class CalibrationInputDialog(QDialog):
    def __init__(self, serial, device_type="stddpc", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter Calibration Values")
        self.serial = serial
        self.device_type = device_type
        self.fields = {}

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Enter calibration values for {serial}"))

        keys = ["pressure_quanta", "pressure_offset", "volume_quanta"]
        for key in keys:
            label = QLabel(key.replace("_", " ").title())
            field = QLineEdit()
            self.fields[key] = field
            layout.addWidget(label)
            layout.addWidget(field)

        # Save and Cancel buttons
        btns = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)

        layout.addLayout(btns)
        self.setLayout(layout)

    def get_values(self):
        return {key: float(field.text()) for key, field in self.fields.items()}
