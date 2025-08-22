# test_details_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QDoubleSpinBox, QCheckBox, QLabel
)
from PyQt5.QtCore import Qt

class TestDetailsDialog(QDialog):
    def __init__(self, parent=None, default_sample_id="", default_period_s=0.5):
        super().__init__(parent)
        self.setWindowTitle("Test Details"); self.setModal(True)

        self.sample_id = QLineEdit(default_sample_id)
        self.sample_id.setPlaceholderText("e.g., RMC-2025-08-19-01")

        # seconds between samples (period)
        self.period_s = QDoubleSpinBox()
        self.period_s.setRange(0.05, 60.0)
        self.period_s.setDecimals(3)
        self.period_s.setSingleStep(0.05)
        self.period_s.setValue(float(default_period_s))
        self.period_s.setSuffix(" s")

        # sample size (cm)
        self.height_mm = QDoubleSpinBox()
        self.height_mm.setRange(1.0, 1000.0)   # 1 mm – 1000 mm
        self.height_mm.setDecimals(1)
        self.height_mm.setSuffix(" mm")

        self.diameter_mm = QDoubleSpinBox()
        self.diameter_mm.setRange(1.0, 500.0)  # 1 mm – 500 mm
        self.diameter_mm.setDecimals(1)
        self.diameter_mm.setSuffix(" mm")


        # docked?
        self.is_docked = QCheckBox("Sample is docked")

        form = QFormLayout(self)
        form.addRow(QLabel("Enter details for this run:"))
        form.addRow("Sample ID:", self.sample_id)
        form.addRow("Sampling period:", self.period_s)
        form.addRow("Sample height:", self.height_mm)
        form.addRow("Sample diameter:", self.diameter_mm)
        form.addRow(self.is_docked)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept_if_valid)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _accept_if_valid(self):
        if not self.sample_id.text().strip():
            self.sample_id.setFocus(); self.sample_id.selectAll(); return
        self.accept()

    def values(self):
        """(sample_id: str, period_s: float, height_mm: float, diameter_mm: float, docked: bool)"""
        return (self.sample_id.text().strip(),
                float(self.period_s.value()),
                float(self.height_mm.value()),
                float(self.diameter_mm.value()),
                bool(self.is_docked.isChecked()))
