from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit
from PyQt5.QtCore import QTimer

class DataViewPage(QWidget):
    def __init__(self, calibration_manager, log=print):
        super().__init__()
        self.serial_pad = None  # set later via .set_serial_pad()
        self.calibration_manager = calibration_manager
        self.log = log

        self.fields = {}

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Live SerialPad Channel Readings"))

        self.form = QFormLayout()
        for ch in range(8):
            field = QLineEdit()
            field.setReadOnly(True)

            cal = self.calibration_manager.get_calibration(ch)
            units = cal.get("units", "units")
            label = cal.get("label", f"Channel {ch}")

            self.form.addRow(f"{label} ({units})", field)
            self.fields[ch] = field

        layout.addLayout(self.form)
        self.setLayout(layout)

        # Start polling
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_readings)
        self.timer.start(1000)

    def set_serial_pad(self, serial_pad_reader):
        self.serial_pad = serial_pad_reader

    def update_readings(self):
        if not self.serial_pad:
            return  # Don't update unless SerialPad is connected
        try:
            values = self.serial_pad.read_channels()
            for ch, val in enumerate(values):
                if val is not None:
                    self.fields[ch].setText(f"{val:.3f}")
                else:
                    self.fields[ch].setText("--")
        except Exception as e:
            self.log(f"[✗] Failed to update readings: {e}")
