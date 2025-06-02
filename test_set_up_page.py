from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QComboBox, QScrollArea, QFormLayout, QGroupBox, QCheckBox
)
from PyQt5.QtCore import Qt

class TestSetupPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.stage_widgets = []  # Track added stage widgets
        self.stage_count = 0

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # Device status indicators
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self.update_device_status()

        layout.addWidget(QLabel("Sample ID"))
        self.sample_input = QLineEdit()
        layout.addWidget(self.sample_input)

        layout.addWidget(QLabel("Specimen Details"))
        self.height_input = QLineEdit()
        self.height_input.setPlaceholderText("Initial Height (mm)")
        self.diameter_input = QLineEdit()
        self.diameter_input.setPlaceholderText("Initial Diameter (mm)")

        hbox = QHBoxLayout()
        hbox.addWidget(self.height_input)
        hbox.addWidget(self.diameter_input)
        layout.addLayout(hbox)

        # Stage Controls
        layout.addWidget(QLabel("Test Stages"))
        self.stage_area = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content.setLayout(self.stage_area)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        add_stage_btn = QPushButton("+ Add Stage")
        add_stage_btn.clicked.connect(self.add_stage)
        layout.addWidget(add_stage_btn)

        self.start_button = QPushButton("Start Test")
        self.start_button.clicked.connect(self._start_test)
        layout.addWidget(self.start_button)

        self.setLayout(layout)

    def update_device_status(self):
        status_text = "<b>Device Status:</b><br>"
        status_text += f"Load Frame: {'Connected ✅' if self.main_window.lf_controller else 'Not Connected ❌'}<br>"
        status_text += f"Pressure Controller: {'Connected ✅' if self.main_window.sttdpc_controller else 'Not Connected ❌'}<br>"
        status_text += f"SerialPad: {'Connected ✅' if self.main_window.serial_pad else 'Not Connected ❌'}<br>"
        self.status_label.setText(status_text)

    def add_stage(self):
        self.stage_count += 1
        stage_box = QGroupBox(f"Stage {self.stage_count}")
        outer_layout = QVBoxLayout()
        form = QFormLayout()

        stage_type = QComboBox()
        stage_type.addItems(["Saturation", "B Test", "Consolidation", "Shear"])

        pressure_input = QLineEdit()
        back_pressure_input = QLineEdit()
        duration_input = QLineEdit()
        rate_input = QLineEdit()
        control_load_checkbox = QCheckBox("Enable automated docking")
        hold_checkbox = QCheckBox("Hold pressure after stage")

        form.addRow("Stage Type", stage_type)
        form.addRow("Cell Pressure (kPa)", pressure_input)
        form.addRow("Back Pressure (kPa)", back_pressure_input)
        form.addRow("Duration (min)", duration_input)
        form.addRow("Velocity (mm/min)", rate_input)
        form.addRow(control_load_checkbox)
        form.addRow(hold_checkbox)

        # Automated docking UI (hidden by default)
        docking_group = QGroupBox("Automated Docking")
        docking_form = QFormLayout()

        axial_mode = QComboBox()
        axial_mode.addItems(["Axial Load (kN)", "Axial Displacement (mm)"])

        axial_target = QLineEdit()
        zero_displacement = QCheckBox("Zero displacement value")

        docking_form.addRow("Set", axial_mode)
        docking_form.addRow("Target", axial_target)
        docking_form.addRow(zero_displacement)
        docking_group.setLayout(docking_form)
        docking_group.setVisible(False)

        control_load_checkbox.toggled.connect(lambda checked: docking_group.setVisible(checked))

        outer_layout.addLayout(form)
        outer_layout.addWidget(docking_group)
        stage_box.setLayout(outer_layout)
        self.stage_area.addWidget(stage_box)

        self.stage_widgets.append({
            "type": stage_type,
            "pressure": pressure_input,
            "back_pressure": back_pressure_input,
            "duration": duration_input,
            "rate": rate_input,
            "control_load": control_load_checkbox,
            "hold": hold_checkbox,
            "axial_group": docking_group,
            "axial_mode": axial_mode,
            "axial_target": axial_target,
            "zero_displacement": zero_displacement
        })

    def _start_test(self):
        sample_id = self.sample_input.text()
        stages = []

        for w in self.stage_widgets:
            stage_type = w["type"].currentText()
            entry = {"name": stage_type}

            if w["pressure"].text():
                try:
                    entry["pressure_kpa"] = float(w["pressure"].text())
                except ValueError:
                    pass
            if w["back_pressure"].text():
                try:
                    entry["back_pressure_kpa"] = float(w["back_pressure"].text())
                except ValueError:
                    pass
            if w["duration"].text():
                try:
                    entry["duration_min"] = float(w["duration"].text())
                except ValueError:
                    pass
            if w["rate"].text():
                try:
                    entry["displacement_rate"] = float(w["rate"].text())
                except ValueError:
                    pass

            entry["control_load"] = w["control_load"].isChecked()
            entry["hold"] = w["hold"].isChecked()

            if w["control_load"].isChecked():
                entry["axial_control"] = {
                    "mode": w["axial_mode"].currentText(),
                    "target": w["axial_target"].text(),
                    "zero_displacement": w["zero_displacement"].isChecked()
                }

            stages.append(entry)

        config = {
            "sample_id": sample_id,
            "height_mm": self.height_input.text(),
            "diameter_mm": self.diameter_input.text(),
            "stages": stages
        }
        self.main_window.start_test(config)
