from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel, QComboBox, QPushButton, QLineEdit, QFormLayout, QMessageBox
)

class DeviceSettingsPage(QWidget):
    def __init__(self, calibration_manager, log=print):
        super().__init__()
        self.calibration_manager = calibration_manager
        self.log = log
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Edit Calibration Values"))

        self.device_selector = QComboBox()
        self.device_selector.addItem("-- Select Device --")

        # Divider + entries
        self.device_selector.addItem("── STDDPC Controllers ──")
        self.stddpc_serials = self.calibration_manager.get_pressure_device_serials()
        self.device_selector.addItems(self.stddpc_serials)

        self.device_selector.addItem("── SerialPad Channels ──")
        self.transducer_channels = self.calibration_manager.get_all_transducer_channels()
        self.device_selector.addItems(self.transducer_channels)

        self.device_selector.currentTextChanged.connect(self.load_device_cal)
        layout.addWidget(self.device_selector)

        # STDDPC fields inside a group box
        self.stddpc_group = QGroupBox("STDDPC Calibration")
        self.stddpc_fields = {}
        stddpc_form = QFormLayout()
        for key in ["pressure_quanta", "pressure_offset", "volume_quanta"]:
            field = QLineEdit()
            self.stddpc_fields[key] = field
            stddpc_form.addRow(QLabel(key.replace("_", " ").title()), field)
        self.stddpc_group.setLayout(stddpc_form)
        layout.addWidget(self.stddpc_group)

        # Transducer fields inside a group box
        self.transducer_group = QGroupBox("Transducer Calibration")
        self.transducer_fields = {}
        transducer_form = QFormLayout()
        for key in ["adc_range", "full_scale_mv", "sensitivity", "soft_zero_offset"]:
            field = QLineEdit()
            self.transducer_fields[key] = field
            transducer_form.addRow(QLabel(key.replace("_", " ").title()), field)
        self.transducer_group.setLayout(transducer_form)
        layout.addWidget(self.transducer_group)

        # Save button
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)
        layout.addWidget(self.save_btn)

        self.setLayout(layout)

        # Start with fields hidden
        self.show_stddpc_fields(False)
        self.show_transducer_fields(False)


    def show_stddpc_fields(self, show):
        self.stddpc_group.setVisible(show)

    def show_transducer_fields(self, show):
        self.transducer_group.setVisible(show)

    def load_device_cal(self, key):
        if key in self.stddpc_serials:
            self.show_stddpc_fields(True)
            self.show_transducer_fields(False)
            cal = self.calibration_manager.get_pressure_calibration(key) or {}
            for k, f in self.stddpc_fields.items():
                f.setText(str(cal.get(k, "")))

        elif key in self.transducer_channels:
            self.show_stddpc_fields(False)
            self.show_transducer_fields(True)
            cal = self.calibration_manager.get_transducer_calibration(key) or {}
            for k, f in self.transducer_fields.items():
                f.setText(str(cal.get(k, "")))
        else:
            self.show_stddpc_fields(False)
            self.show_transducer_fields(False)

    def save(self):
        key = self.device_selector.currentText()
        try:
            if key in self.stddpc_serials:
                values = {k: float(f.text()) for k, f in self.stddpc_fields.items()}
                self.calibration_manager.set_pressure_calibration(key, values)
                QMessageBox.information(self, "Saved", f"STDDPC calibration for {key} saved.")

            elif key in self.transducer_channels:
                values = {k: float(f.text()) for k, f in self.transducer_fields.items()}
                self.calibration_manager.set_transducer_calibration(key, values)
                QMessageBox.information(self, "Saved", f"Transducer calibration for {key} saved.")
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter valid numeric values for all fields.")
