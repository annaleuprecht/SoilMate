from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QDoubleSpinBox, QPushButton, QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from ftd2xx_controllers.lf50_ftd2xx_controller import FTLoadFrameController

class ManualControlPage(QWidget):
    # Signals your MainWindow / hardware layer can connect to
    send_axial_position_requested = pyqtSignal(float)    # mm
    send_axial_velocity_requested = pyqtSignal(float)    # mm/min
    stop_axial_requested          = pyqtSignal()

    send_cell_pressure_requested  = pyqtSignal(float)    # kPa
    stop_cell_pressure_requested  = pyqtSignal()

    send_back_pressure_requested  = pyqtSignal(float)    # kPa
    stop_back_pressure_requested  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Segoe UI", 12))

        # ---- Title ----
        title_bar = QHBoxLayout()
        t = QLabel("Manual Control")
        t.setObjectName("TitleLabel")
        title_bar.addWidget(t)
        title_bar.addStretch(1)

        # ---- Scroll body ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)

        # ---- Axial Position (Load Frame) ----
        self.axial_card = QGroupBox("Axial Position (Load Frame)")
        self.axial_card.setObjectName("Card")
        axial = QFormLayout(self.axial_card)
        axial.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        axial.setHorizontalSpacing(12)
        axial.setVerticalSpacing(8)
        axial.setContentsMargins(12, 10, 12, 12)

        self.axial_status = self._status_badge(False)
        axial.addRow(QLabel("Status:"), self.axial_status)

        self.pos_spin = QDoubleSpinBox()
        self.pos_spin.setRange(FTLoadFrameController.MIN_POSITION_MM, FTLoadFrameController.MAX_POSITION_MM)
        self.pos_spin.setDecimals(3)
        self.pos_spin.setSingleStep(0.1)
        self.pos_spin.setSuffix(" mm")
        axial.addRow("Target Position:", self.pos_spin)

        self.vel_spin = QDoubleSpinBox()
        self.vel_spin.setRange(FTLoadFrameController.MIN_VELOCITY, FTLoadFrameController.MAX_VELOCITY)
        self.vel_spin.setDecimals(3)
        self.vel_spin.setSingleStep(0.1)
        self.vel_spin.setSuffix(" mm/min")
        axial.addRow("Target Velocity:", self.vel_spin)

        ax_btns1 = QHBoxLayout(); ax_btns1.addStretch(1)
        self.ax_send_pos = QPushButton("Send Axial Position")
        self.ax_send_vel = QPushButton("Send Axial Velocity")
        ax_btns1.addWidget(self.ax_send_pos); ax_btns1.addWidget(self.ax_send_vel)
        axial.addRow(ax_btns1)

        ax_btns2 = QHBoxLayout(); ax_btns2.addStretch(1)
        self.ax_stop = QPushButton("Stop Load Frame")
        ax_btns2.addWidget(self.ax_stop)
        axial.addRow(ax_btns2)

        # ---- Cell Pressure ----
        self.cell_card = QGroupBox("Cell Pressure Control (STDDPC)")
        self.cell_card.setObjectName("Card")
        cell = QFormLayout(self.cell_card)
        cell.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cell.setHorizontalSpacing(12)
        cell.setVerticalSpacing(8)
        cell.setContentsMargins(12, 10, 12, 12)

        self.cell_status = self._status_badge(False)
        cell.addRow(QLabel("Status:"), self.cell_status)

        self.cell_spin = QDoubleSpinBox()
        self.cell_spin.setRange(-500.0, 5000.0)
        self.cell_spin.setDecimals(1)
        self.cell_spin.setSingleStep(5.0)
        self.cell_spin.setSuffix(" kPa")
        cell.addRow("Target Pressure:", self.cell_spin)

        c_btns1 = QHBoxLayout(); c_btns1.addStretch(1)
        self.cell_send = QPushButton("Send Cell Pressure")
        c_btns1.addWidget(self.cell_send)
        cell.addRow(c_btns1)

        c_btns2 = QHBoxLayout(); c_btns2.addStretch(1)
        self.cell_stop = QPushButton("Stop Cell Pressure")
        c_btns2.addWidget(self.cell_stop)
        cell.addRow(c_btns2)

        # ---- Back Pressure ----
        self.back_card = QGroupBox("Back Pressure Control (STDDPC)")
        self.back_card.setObjectName("Card")
        back = QFormLayout(self.back_card)
        back.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        back.setHorizontalSpacing(12)
        back.setVerticalSpacing(8)
        back.setContentsMargins(12, 10, 12, 12)

        self.back_status = self._status_badge(False)
        back.addRow(QLabel("Status:"), self.back_status)

        self.back_spin = QDoubleSpinBox()
        self.back_spin.setRange(-500.0, 5000.0)
        self.back_spin.setDecimals(1)
        self.back_spin.setSingleStep(5.0)
        self.back_spin.setSuffix(" kPa")
        back.addRow("Target Pressure:", self.back_spin)

        b_btns1 = QHBoxLayout(); b_btns1.addStretch(1)
        self.back_send = QPushButton("Send Back Pressure")
        b_btns1.addWidget(self.back_send)
        back.addRow(b_btns1)

        b_btns2 = QHBoxLayout(); b_btns2.addStretch(1)
        self.back_stop = QPushButton("Stop Back Pressure")
        b_btns2.addWidget(self.back_stop)
        back.addRow(b_btns2)

        # Compose
        col.addWidget(self.axial_card)
        col.addWidget(self.cell_card)
        col.addWidget(self.back_card)
        col.addStretch(1)

        page = QVBoxLayout(self)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(10)
        page.addLayout(title_bar)
        page.addWidget(scroll)

        # Style to match other pages
        self.setStyleSheet("""
            QWidget { font-size: 18px; }
            QLabel#TitleLabel { font-size: 24px; font-weight: 600; }
            QGroupBox#Card {
                border: 1px solid #ddd; border-radius: 8px;
                margin-top: 10px; background: #fff;
            }
            QGroupBox#Card::title {
                subcontrol-origin: margin; left: 12px; top: -2px;
                padding: 0 4px; font-weight: 600; color: #333;
            }
            QPushButton { padding: 8px 12px; font-weight: 500; }
            QLabel.status-ok  { color: #167c2b; font-weight: 600; }
            QLabel.status-bad { color: #b01c2e; font-weight: 600; }
        """)

        # Wire signals
        self.ax_send_pos.clicked.connect(lambda: self.send_axial_position_requested.emit(self.pos_spin.value()))
        self.ax_send_vel.clicked.connect(lambda: self.send_axial_velocity_requested.emit(self.vel_spin.value()))
        self.ax_stop.clicked.connect(self.stop_axial_requested.emit)

        self.cell_send.clicked.connect(lambda: self.send_cell_pressure_requested.emit(self.cell_spin.value()))
        self.cell_stop.clicked.connect(self.stop_cell_pressure_requested.emit)

        self.back_send.clicked.connect(lambda: self.send_back_pressure_requested.emit(self.back_spin.value()))
        self.back_stop.clicked.connect(self.stop_back_pressure_requested.emit)

        # Start disabled until devices are connected
        self.set_axial_enabled(False)
        self.set_cell_enabled(False)
        self.set_back_enabled(False)

    # ----- helpers -----
    def _status_badge(self, ok: bool) -> QLabel:
        lab = QLabel()
        self._set_status(lab, ok)
        return lab

    def _set_status(self, lab: QLabel, ok: bool):
        lab.setText(("✔ Connected" if ok else "✖ Not Connected"))
        lab.setObjectName("")  # clear
        lab.setProperty("class", None)
        lab.setStyleSheet("")  # reset
        lab.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lab.setObjectName("status")
        lab.setProperty("ok", ok)
        lab.setClass = ("status-ok" if ok else "status-bad")
        # apply CSS class via dynamic property is clunky; easiest:
        lab.setStyleSheet("color:#167c2b;font-weight:600;" if ok else "color:#b01c2e;font-weight:600;")

    # Public API you can call from MainWindow when hardware connects/disconnects
    def set_axial_enabled(self, enabled: bool):
        self._set_status(self.axial_status, enabled)
        for w in (self.pos_spin, self.vel_spin, self.ax_send_pos, self.ax_send_vel, self.ax_stop):
            w.setEnabled(enabled)

    def set_cell_enabled(self, enabled: bool):
        self._set_status(self.cell_status, enabled)
        for w in (self.cell_spin, self.cell_send, self.cell_stop):
            w.setEnabled(enabled)

    def set_back_enabled(self, enabled: bool):
        self._set_status(self.back_status, enabled)
        for w in (self.back_spin, self.back_send, self.back_stop):
            w.setEnabled(enabled)
