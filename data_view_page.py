from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLineEdit, QSizePolicy, QScrollArea, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class MetricCard(QGroupBox):
    """A small card with a title and a read-only value + unit."""
    def __init__(self, title: str, unit: str = "", parent=None):
        super().__init__(title, parent)
        self.setObjectName("MetricCard")

        row = QHBoxLayout()
        row.setContentsMargins(12, 10, 12, 12)
        row.setSpacing(8)

        self.value = QLineEdit("—")
        self.value.setReadOnly(True)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.value.setObjectName("MetricValue")

        unit_lbl = QLabel(unit)
        unit_lbl.setObjectName("MetricUnit")
        unit_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        row.addWidget(self.value)
        row.addWidget(unit_lbl)
        self.setLayout(row)

    def set_value(self, v):
        self.value.setText(str(v))


class DataViewPage(QWidget):
    """
    Pretty Data View:
      - Title header (matches Test Set Up)
      - Grid of QGroupBox 'cards' (two columns, responsive)
      - Call set_values({...}) to update readings
    """
    def __init__(self, calibration_manager=None, parent=None, log=None):
        super().__init__(parent)
        self.calibration_manager = calibration_manager
        self.log = log or (lambda *a, **k: None)

        self.setFont(QFont("Segoe UI", 12))

        # -------- Title bar --------
        title_bar = QHBoxLayout()
        title = QLabel("Data View")
        title.setObjectName("TitleLabel")
        title_bar.addWidget(title)
        title_bar.addStretch(1)

        # -------- Card grid in a scroll area --------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        grid_wrap = QWidget()
        self.grid = QGridLayout(grid_wrap)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(12)

        scroll.setWidget(grid_wrap)

        # Which channels to show (name -> unit)
        channels = [
            ("Axial Load", "kN"),
            ("Pore Pressure", "kPa"),
            ("Axial Displacement", "mm"),
            ("Local Axial 1", "mV"),
            ("Local Axial 2", "mV"),
            ("Local Radial", "mV"),
            ("Unused 1", "mV"),
            ("Unused 2", "mV"),

            ("Cell Pressure", "kPa"),
            ("Cell Volume", "mm³"),
            ("Back Pressure", "kPa"),
            ("Back Volume", "mm³"),
        ]

        # Build cards (2 columns)
        self.cards = {}
        for i, (name, unit) in enumerate(channels):
            card = MetricCard(name, unit)
            r, c = divmod(i, 2)     # two columns
            self.grid.addWidget(card, r, c)
            self.cards[name] = card

        # -------- Page layout --------
        page = QVBoxLayout(self)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(10)
        page.addLayout(title_bar)
        page.addWidget(scroll)

        # -------- Styling --------
        self.setStyleSheet("""
            QWidget { font-size: 18px; }  /* match the rest of the app */

            QLabel#TitleLabel {
                font-size: 24px;
                font-weight: 600;
            }

            /* Card look */
            QGroupBox#MetricCard {
                border: 1px solid #dddddd;
                border-radius: 8px;
                margin-top: 10px;     /* space for title */
                background: #ffffff;
            }
            QGroupBox#MetricCard::title {
                subcontrol-origin: margin;
                left: 12px;
                top: -2px;
                padding: 0 4px;
                color: #333;
                font-weight: 600;
            }

            /* Value field */
            QLineEdit#MetricValue {
                min-height: 30px;
                padding: 4px 8px;
                background: #fafafa;
                border: 1px solid #dcdcdc;
                border-radius: 6px;
            }

            QLabel#MetricUnit {
                padding-left: 6px;
                color: #555;
            }
        """)

    # ----- public API -----
    def set_value(self, name: str, value):
        """Update a single channel by display name."""
        card = self.cards.get(name)
        if card:
            card.set_value(value)

    def set_values(self, mapping: dict):
        """Bulk update: {'Axial Load': 12.34, 'Pore Pressure': 100.2, ...}"""
        for k, v in mapping.items():
            self.set_value(k, v)
