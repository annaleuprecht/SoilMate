# station_config_page.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QComboBox, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
import ftd2xx

class StationConfigPage(QWidget):
    config_changed = pyqtSignal(list)   # emits list of device dicts whenever it changes
    connect_requested = pyqtSignal(dict)   # NEW: ask MainWindow to connect one device

    def __init__(self, log=None, parent=None):
        super().__init__(parent)
        self.log = log or (lambda *a, **k: None)
        self.setFont(QFont("Segoe UI", 12))

        self._models_by_type = {
            "Load Frame": ["LF-50"],
            "Cell Pressure Controller": ["STDDPC"],
            "Back Pressure Controller": ["STDDPC"],
            "Serial Pad": ["SerialPad-8ch"],
        }
        self._devices = []  # [{name, type, model}]

        # ===== Title =====
        title_row = QHBoxLayout()
        title = QLabel("Station Configuration")
        title.setObjectName("TitleLabel")
        title_row.addWidget(title)
        title_row.addStretch(1)

        # ===== Scroll body (prevents taskbar clipping) =====
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        body = QWidget()
        scroll.setWidget(body)
        body_col = QVBoxLayout(body)
        body_col.setContentsMargins(0, 0, 0, 0)
        body_col.setSpacing(12)

        # ===== Card: Add Device =====
        add_card = QGroupBox("Add Device")
        add_card.setObjectName("Card")
        add_form = QFormLayout(add_card)
        add_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        add_form.setHorizontalSpacing(12)
        add_form.setVerticalSpacing(8)
        add_form.setContentsMargins(12, 10, 12, 12)

        self.type_combo  = QComboBox()
        self.model_combo = QComboBox()
        self.name_edit   = QLineEdit()
        self.name_edit.setPlaceholderText("Optional nickname (e.g., LF #1)")
        self.name_edit.setMaximumWidth(260)  # ← keep the add-form Name box compact
        self.add_btn     = QPushButton("+ Add Device")   # ← ensure this line exists

        # populate combos
        self.type_combo.addItems(self._models_by_type.keys())
        self._rebuild_model_combo()

        self.type_combo.currentTextChanged.connect(self._rebuild_model_combo)
        self.add_btn.clicked.connect(self._on_add_clicked)

        add_form.addRow("Device Type", self.type_combo)
        add_form.addRow("Model",       self.model_combo)
        add_form.addRow("Name",        self.name_edit)

        add_actions = QHBoxLayout()
        add_actions.addStretch(1)
        add_actions.addWidget(self.add_btn)
        add_form.addRow(add_actions)

        # ===== Card: Configured Devices =====
        list_card = QGroupBox("Configured Devices")
        list_card.setObjectName("Card")
        list_col = QVBoxLayout(list_card)
        list_col.setContentsMargins(12, 10, 12, 12)

        # create the table
        self.table = QTableWidget(0, 6)  # Name, Type, Model, Serial, Actions
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Model", "Serial", "Actions", "Status"])
        # Use explicit widths so Actions is readable
        header = self.table.horizontalHeader()

        header.setSectionResizeMode(0, QHeaderView.Interactive)      # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Type
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Model
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Serial
        header.setSectionResizeMode(4, QHeaderView.Fixed)            # Actions
        header.setSectionResizeMode(5, QHeaderView.Fixed)             # Status

        # Give Name a reasonable width; make Actions wide enough for both buttons
        self.table.setColumnWidth(0, 500)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(3, 250)
        self.table.setColumnWidth(4, 250)
        self.table.setColumnWidth(5, 300)   # Status (✓ / ✗ chip)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        list_col.addWidget(self.table)

        bottom_actions = QHBoxLayout()
        self.clear_btn = QPushButton("Clear All")
        bottom_actions.addStretch(1)
        bottom_actions.addWidget(self.clear_btn)
        list_col.addLayout(bottom_actions)

        self.clear_btn.clicked.connect(self._clear_all)

        # ===== Compose page =====
        body_col.addWidget(add_card)
        body_col.addWidget(list_card)
        body_col.addStretch(1)

        page = QVBoxLayout(self)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(10)
        page.addLayout(title_row)
        page.addWidget(scroll)

        # ===== Styling (match the rest) =====
        self.setStyleSheet("""
            QWidget { font-size: 18px; }
            QLabel#TitleLabel { font-size: 24px; font-weight: 600; }

            QGroupBox#Card {
                border: 1px solid #ddd;
                border-radius: 8px;
                margin-top: 10px;
                background: #fff;
            }
            QGroupBox#Card::title {
                subcontrol-origin: margin; left: 12px; top: -2px;
                padding: 0 4px; font-weight: 600; color: #333;
            }

            QPushButton { padding: 8px 12px; font-weight: 500; }
        """)

    # ---------- Public API ----------
    def set_available_models(self, models_by_type: dict):
        """Replace the type→models mapping and rebuild combos."""
        if not models_by_type:
            return
        self._models_by_type = dict(models_by_type)
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItems(self._models_by_type.keys())
        self.type_combo.blockSignals(False)
        self._rebuild_model_combo()

    def _ftdi_serials(self):
        try:
            devs = ftd2xx.listDevices() or []
            return [(d.decode() if isinstance(d, bytes) else str(d)) for d in devs]
        except Exception:
            return []

    def load_config(self, devices: list):
        """devices: list of dicts like {'type':..., 'model':..., 'name':...}"""
        self._devices = [dict(d) for d in (devices or [])]
        self._rebuild_table()
        self.config_changed.emit(self.get_config())

    def get_config(self) -> list:
        return [dict(d) for d in self._devices]

    # ---------- Internals ----------
    def _rebuild_model_combo(self):
        dtype = self.type_combo.currentText()
        models = self._models_by_type.get(dtype, [])
        self.model_combo.clear()
        self.model_combo.addItems(models)

    def _status_chip(self, ok: bool):
        """Small, centered label that looks like a status pill."""
        from PyQt5.QtWidgets import QLabel
        lbl = QLabel("✓ Connected" if ok else "✗ Not connected")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "QLabel {"
            "  padding: 2px 8px;"
            "  border-radius: 10px;"
            f" background: {'#e6f9ed' if ok else '#fde8e8'};"
            f" color: {'#0b7a34' if ok else '#a40000'};"
            "  font-weight: 600;"
            "}"
        )
        return lbl

    def set_status(self, row: int, ok: bool):
        if not (0 <= row < len(self._devices)):
            return
        # No-op if already in this state
        if self._devices[row].get("connected") is ok:
            return
        self._devices[row]["connected"] = ok

        table = self.table
        table.setUpdatesEnabled(False)
        try:
            if 0 <= row < self.table.rowCount():
                self.table.setCellWidget(row, 5, self._status_chip(ok))
            if 0 <= row < len(self._devices):                # <-- persist it
                self._devices[row]["connected"] = bool(ok)
            pass
        finally:
            table.setUpdatesEnabled(True)

    def _on_add_clicked(self):
        dtype  = self.type_combo.currentText().strip()
        model  = self.model_combo.currentText().strip()
        name   = self.name_edit.text().strip()
        item = {
            "name": self.name_edit.text().strip(),
            "type": self.type_combo.currentText(),
            "model": self.model_combo.currentText(),
            "serial": "",            # none yet
            "connected": False,      # <-- persist status
        }

        self._devices.append(item)
        self._append_row(item)
        self.name_edit.clear()
        self.config_changed.emit(self.get_config())
        self.log(f"[config] Added: {item}")

    def _append_row(self, item):
        # 0) create row
        r = self.table.rowCount()
        self.table.insertRow(r)

        # 1) columns 0–2: Name / Type / Model
        self.table.setItem(r, 0, QTableWidgetItem(item.get("name", "")))
        dtype = item.get("type", "")
        self.table.setItem(r, 1, QTableWidgetItem(dtype))
        self.table.setItem(r, 2, QTableWidgetItem(item.get("model", "")))

        # 2) column 3: Serial (combobox for FTDI devices, line edit for Serial Pad)
        if dtype in ("Load Frame", "Cell Pressure Controller", "Back Pressure Controller"):
            serial_box = QComboBox()
            try:
                devs = ftd2xx.listDevices() or []
                serials = [(d.decode() if isinstance(d, bytes) else str(d)) for d in devs]
            except Exception:
                serials = []
            serial_box.addItems(serials)
            if item.get("serial"):
                idx = serial_box.findText(item["serial"])
                if idx >= 0:
                    serial_box.setCurrentIndex(idx)
            self.table.setCellWidget(r, 3, serial_box)
        elif dtype == "Serial Pad":
            port_edit = QLineEdit(item.get("serial", ""))
            port_edit.setPlaceholderText("COM5")
            self.table.setCellWidget(r, 3, port_edit)
        else:
            self.table.setItem(r, 3, QTableWidgetItem(item.get("serial", "")))

        # 3) column 4: Actions (Connect / Remove)
        wrap = QWidget()
        row_actions = QHBoxLayout(wrap)
        row_actions.setContentsMargins(0, 0, 0, 0)
        btn_connect = QPushButton("Connect")
        btn_remove  = QPushButton("Remove")
        row_actions.addWidget(btn_connect)
        row_actions.addWidget(btn_remove)
        row_actions.addStretch(1)
        self.table.setCellWidget(r, 4, wrap)
        # station_config_page.py, in _append_row (after Actions cell)
        ok = bool(item.get("connected", False))
        self.table.setCellWidget(r, 5, self._status_chip(ok))


        # 4) wire buttons
        btn_connect.clicked.connect(lambda *_: self._emit_connect(r))
        btn_remove.clicked.connect(lambda *_: self._remove_row(r))


    def _emit_connect(self, row):
        if 0 <= row < len(self._devices):
            payload = dict(self._devices[row])
            payload["_row"] = row

            # Read serial/port from the Serial column widget (col 3)
            w = self.table.cellWidget(row, 3)
            if isinstance(w, QComboBox):
                payload["serial"] = w.currentText().strip()
            elif isinstance(w, QLineEdit):
                payload["serial"] = w.text().strip()
            else:
                it = self.table.item(row, 3)
                payload["serial"] = it.text().strip() if it else ""

            self.connect_requested.emit(payload)

    def _remove_row(self, row):
        if 0 <= row < len(self._devices):
            removed = self._devices.pop(row)
            self.table.removeRow(row)
            # fix up button callbacks that captured old row indices
            for r in range(self.table.rowCount()):
                w = self.table.cellWidget(r, 3)
                if isinstance(w, QPushButton):
                    try:
                        for old in w.clicked.disconnect():
                            pass
                    except TypeError:
                        pass
                    w.clicked.connect(lambda _, rr=r: self._remove_row(rr))
            self.config_changed.emit(self.get_config())
            self.log(f"[config] Removed: {removed}")

    def _rebuild_table(self):
        self.table.setRowCount(0)
        for d in self._devices:
            self._append_row(d)

    def _clear_all(self):
        if not self._devices:
            return
        self._devices.clear()
        self._rebuild_table()
        self.config_changed.emit(self.get_config())
        self.log("[config] Cleared all devices")
