from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QGridLayout,
    QFormLayout, QComboBox, QPushButton, QDoubleSpinBox, QScrollArea,
    QMessageBox, QFrame, QSizePolicy, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

class DeviceSettingsPage(QWidget):
    # existing signals
    refresh_devices_requested = pyqtSignal()
    save_device_requested     = pyqtSignal(str)
    apply_limits_requested    = pyqtSignal(float, float)
    apply_lf_limits_requested = pyqtSignal(float, float, float)
    # new/used by MainWindow
    apply_spad_config_requested = pyqtSignal(dict)
    reload_spad_requested       = pyqtSignal()
    apply_stddpc_cal_requested = pyqtSignal(str, float, float, float)   # (serial, p_q, p_off, v_q)
    reload_stddpc_cal_requested = pyqtSignal(str)                       # (serial)


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Segoe UI", 12))

        self._roles = [
            "Axial Load","Pore Pressure","Axial Displacement",
            "Local Axial 1","Local Axial 2","Local Radial","Unused 1","Unused 2"
        ]
        self._assignments = {i: {"role": self._roles[i], "sensor": ""} for i in range(8)}
        self._sensors = {}  # name -> meta

        # ===== Title bar =====
        title_bar = QHBoxLayout()
        title = QLabel("Device Settings")
        title.setObjectName("TitleLabel")
        title_bar.addWidget(title)
        title_bar.addStretch(1)

        # ===== Scroll area =====
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        body_col = QVBoxLayout(body)
        body_col.setContentsMargins(0, 0, 0, 0)
        body_col.setSpacing(12)

        # ===== Card 1: Connected Device =====
        dev_card = QGroupBox("Connected Device")
        dev_card.setObjectName("Card")
        dev_grid = QGridLayout(dev_card)
        dev_grid.setContentsMargins(12, 10, 12, 12)

        self.device_combo = QComboBox()
        self.device_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.refresh_btn  = QPushButton("Refresh")
        self.save_btn     = QPushButton("Save")

        dev_grid.addWidget(QLabel("Select Device"), 0, 0)
        dev_grid.addWidget(self.device_combo, 0, 1)
        btn_row = QHBoxLayout(); btn_row.addStretch(1)
        btn_row.addWidget(self.refresh_btn); btn_row.addWidget(self.save_btn)
        dev_grid.addLayout(btn_row, 1, 0, 1, 2)

        # ===== Card 2: Pressure limits =====
        lim_card = QGroupBox("Pressure Command Limits")
        lim_card.setObjectName("Card")
        lim_form = QFormLayout(lim_card)
        lim_form.setContentsMargins(12, 10, 12, 12)

        self.min_spin = QDoubleSpinBox(); self.max_spin = QDoubleSpinBox()
        for sp in (self.min_spin, self.max_spin):
            sp.setDecimals(1); sp.setRange(-500.0, 5000.0)
            sp.setSingleStep(5.0); sp.setSuffix(" kPa"); sp.setMinimumWidth(180)
        self.min_spin.setValue(-50.0); self.max_spin.setValue(3050.0)

        lim_form.addRow("Minimum Pressure:", self.min_spin)
        lim_form.addRow("Maximum Pressure:", self.max_spin)
        self.apply_btn = QPushButton("Apply Limits")
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(self.apply_btn)
        lim_form.addRow(row)

        # ===== Card 3: Load frame limits =====
        self.grp_lf = QGroupBox("Load Frame Limits")
        lf_form = QFormLayout(self.grp_lf)
        self.lf_min_pos = QDoubleSpinBox(); self.lf_min_pos.setRange(-1e6, 1e6); self.lf_min_pos.setSuffix(" mm")
        self.lf_max_pos = QDoubleSpinBox(); self.lf_max_pos.setRange(-1e6, 1e6); self.lf_max_pos.setSuffix(" mm")
        self.lf_max_vel = QDoubleSpinBox(); self.lf_max_vel.setRange(0, 1e6);   self.lf_max_vel.setSuffix(" mm/min")
        lf_form.addRow("Minimum Position:", self.lf_min_pos)
        lf_form.addRow("Maximum Position:", self.lf_max_pos)
        lf_form.addRow("Maximum Velocity:", self.lf_max_vel)
        self.btn_apply_lf = QPushButton("Apply LF Limits")
        lf_form.addRow(self.btn_apply_lf)

        # ===== Card 4: SerialPad (view first) =====
        self.spad_card = QGroupBox("SerialPad Configuration")
        spad_grid = QGridLayout(self.spad_card)
        spad_grid.setContentsMargins(12, 10, 12, 12)
        spad_grid.setHorizontalSpacing(10); spad_grid.setVerticalSpacing(6)

        self._role_combo = []
        self._sensor_combo = []
        self._new_btns = []

        spad_grid.addWidget(QLabel("Channel"), 0, 0)
        spad_grid.addWidget(QLabel("Role"),    0, 1)
        spad_grid.addWidget(QLabel("Sensor"),  0, 2)
        spad_grid.addWidget(QLabel(""),        0, 3)

        for ch in range(8):
            spad_grid.addWidget(QLabel(f"Channel {ch}"), ch+1, 0, Qt.AlignLeft)
            rc = QComboBox(); rc.addItems(self._roles)
            sc = QComboBox()  # filled in set_serialpad_config
            nb = QPushButton("New…")
            nb.setToolTip("Create a new sensor and assign it to this channel")

            # store
            self._role_combo.append(rc)
            self._sensor_combo.append(sc)
            self._new_btns.append(nb)

            spad_grid.addWidget(rc, ch+1, 1)
            spad_grid.addWidget(sc, ch+1, 2)
            spad_grid.addWidget(nb, ch+1, 3)

            nb.clicked.connect(lambda _, i=ch: self._on_new_sensor(i))

        # bottom row
        self.spad_edit_btn   = QPushButton("Edit")
        self.spad_reload_btn = QPushButton("Reload")
        self.spad_apply_btn  = QPushButton("Apply SerialPad")
        self.spad_cancel_btn = QPushButton("Cancel")

        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self.spad_reload_btn)
        bar.addWidget(self.spad_edit_btn)
        bar.addWidget(self.spad_cancel_btn)
        bar.addWidget(self.spad_apply_btn)
        spad_grid.addLayout(bar, 10, 0, 1, 4)

        # --- STDDPC Calibration -------------------------------------------------
        self.stddpc_card = QGroupBox("STDDPC Calibration")
        st = QGridLayout(self.stddpc_card)
        st.setContentsMargins(12, 10, 12, 12)

        self.stddpc_serial = QComboBox()
        self.stddpc_load   = QPushButton("Load Current")
        self.stddpc_apply  = QPushButton("Apply Calibration")

        self.stddpc_pq = QDoubleSpinBox(); self.stddpc_pq.setDecimals(7); self.stddpc_pq.setRange(0, 0.01); self.stddpc_pq.setSingleStep(0.000001)
        self.stddpc_po = QDoubleSpinBox(); self.stddpc_po.setDecimals(3); self.stddpc_po.setRange(-2000, 2000); self.stddpc_po.setSingleStep(0.1)
        self.stddpc_vq = QDoubleSpinBox(); self.stddpc_vq.setDecimals(5); self.stddpc_vq.setRange(0, 10);    self.stddpc_vq.setSingleStep(0.0001)

        st.addWidget(QLabel("Device Serial"),     0, 0); st.addWidget(self.stddpc_serial, 0, 1); st.addWidget(self.stddpc_load, 0, 2)
        st.addWidget(QLabel("pressure_quanta"),   1, 0); st.addWidget(self.stddpc_pq,     1, 1)
        st.addWidget(QLabel("pressure_offset"),   2, 0); st.addWidget(self.stddpc_po,     2, 1)
        st.addWidget(QLabel("volume_quanta"),     3, 0); st.addWidget(self.stddpc_vq,     3, 1)
        st.addWidget(self.stddpc_apply,           4, 0, 1, 3, alignment=Qt.AlignRight)

        body_col.addWidget(self.stddpc_card)

        # wire up
        self.stddpc_load.clicked.connect(lambda: self.reload_stddpc_cal_requested.emit(self.stddpc_serial.currentText().strip()))
        self.stddpc_apply.clicked.connect(lambda: self.apply_stddpc_cal_requested.emit(
            self.stddpc_serial.currentText().strip(),
            float(self.stddpc_pq.value()),
            float(self.stddpc_po.value()),
            float(self.stddpc_vq.value()),
        ))


        # ===== assemble page =====
        body_col.addWidget(dev_card)
        body_col.addWidget(lim_card)
        body_col.addWidget(self.grp_lf)
        body_col.addWidget(self.spad_card)
        body_col.addStretch(1)

        page = QVBoxLayout(self)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(10)
        page.addLayout(title_bar)
        page.addWidget(scroll)

        # ===== styling =====
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
        """)

        # ===== signals =====
        self.refresh_btn.clicked.connect(self.refresh_devices_requested.emit)
        self.save_btn.clicked.connect(self._emit_save)
        self.apply_btn.clicked.connect(self._emit_apply)
        self.btn_apply_lf.clicked.connect(
            lambda: self.apply_lf_limits_requested.emit(
                float(self.lf_min_pos.value()),
                float(self.lf_max_pos.value()),
                float(self.lf_max_vel.value()),
            )
        )
        self.spad_apply_btn.clicked.connect(self._emit_apply_spad)
        self.spad_reload_btn.clicked.connect(self.reload_spad_requested.emit)
        self.spad_edit_btn.clicked.connect(lambda: self.set_spad_edit_enabled(True))
        self.spad_cancel_btn.clicked.connect(lambda: self.set_spad_edit_enabled(False))

        # start in view mode (MainWindow also ensures this on entry)  # :contentReference[oaicite:2]{index=2}
        self.set_spad_edit_enabled(False)

    # ---------- SerialPad helpers ----------
    def set_serialpad_config(self, assignments: dict, sensors: dict):
        """Fill the card from live/persisted config (view mode by default)."""
        self._assignments = {int(k): dict(v) for k, v in (assignments or {}).items()}
        self._sensors = dict(sensors or {})
        # refresh sensor combos
        names = [""] + sorted(self._sensors.keys())
        for sc in self._sensor_combo:
            sc.blockSignals(True)
            sc.clear()
            sc.addItems(names)
            sc.blockSignals(False)
        # set per-channel selection
        for ch in range(8):
            a = self._assignments.get(ch, {})
            role = a.get("role", self._roles[ch])
            sensor = a.get("sensor", "")
            self._role_combo[ch].setCurrentText(role)
            self._sensor_combo[ch].setCurrentText(sensor)

    def gather_serialpad_config(self) -> dict:
        out = {"assignments": {}, "sensors": dict(self._sensors)}
        for ch in range(8):
            out["assignments"][ch] = {
                "role":   self._role_combo[ch].currentText().strip(),
                "sensor": self._sensor_combo[ch].currentText().strip(),
            }
        return out

    def set_spad_edit_enabled(self, on: bool):
        """Toggle editing; combos disabled in view mode."""
        for w in self._role_combo + self._sensor_combo + self._new_btns:
            w.setEnabled(bool(on))
        self.spad_apply_btn.setEnabled(bool(on))
        self.spad_cancel_btn.setEnabled(bool(on))
        self.spad_edit_btn.setEnabled(not on)

    def set_stddpc_serials(self, serials, select=None):
        self.stddpc_serial.blockSignals(True)
        self.stddpc_serial.clear()
        for s in (serials or []):
            self.stddpc_serial.addItem(str(s))
        self.stddpc_serial.blockSignals(False)
        if select:
            i = self.stddpc_serial.findText(select)
            if i >= 0:
                self.stddpc_serial.setCurrentIndex(i)

    def set_stddpc_values(self, p_q: float, p_off: float, v_q: float):
        self.stddpc_pq.setValue(float(p_q))
        self.stddpc_po.setValue(float(p_off))
        self.stddpc_vq.setValue(float(v_q))

    def current_stddpc_serial(self) -> str:
        return self.stddpc_serial.currentText().strip()


    def _on_new_sensor(self, ch: int):
        # very small dialog: name, units, scale, offset, kind
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self); dlg.setWindowTitle(f"New Sensor (assign to Ch {ch})")
        lay = QFormLayout(dlg)
        name = QLineEdit(); units = QLineEdit(); kind = QLineEdit()
        scale = QDoubleSpinBox(); scale.setRange(-1e9, 1e9); scale.setValue(1.0)
        offset = QDoubleSpinBox(); offset.setRange(-1e9, 1e9); offset.setValue(0.0)
        lay.addRow("Name", name); lay.addRow("Units", units); lay.addRow("Kind", kind)
        lay.addRow("Scale", scale); lay.addRow("Offset", offset)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addRow(btns); btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() != dlg.Accepted:
            return
        nm = name.text().strip()
        if not nm:
            QMessageBox.warning(self, "New Sensor", "Please enter a name."); return
        self._sensors[nm] = {
            "units": units.text().strip(),
            "kind":  kind.text().strip(),
            "scale": float(scale.value()),
            "offset": float(offset.value()),
        }
        # update all sensor combos & select on this row
        names = [""] + sorted(self._sensors.keys())
        for sc in self._sensor_combo:
            cur = sc.currentText()
            sc.blockSignals(True); sc.clear(); sc.addItems(names); sc.setCurrentText(cur); sc.blockSignals(False)
        self._sensor_combo[ch].setCurrentText(nm)

    def _emit_apply_spad(self):
        cfg = self.gather_serialpad_config()
        self.apply_spad_config_requested.emit(cfg)
        self.set_spad_edit_enabled(False)

    # ---------- existing page helpers ----------
    def populate_devices(self, items, select=None):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for it in items:
            self.device_combo.addItem(str(it))
        self.device_combo.blockSignals(False)
        if select:
            idx = self.device_combo.findText(select)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)

    def set_limits(self, lo: float, hi: float):
        self.min_spin.setValue(float(lo)); self.max_spin.setValue(float(hi))

    def limits(self):
        return self.min_spin.value(), self.max_spin.value()

    def _emit_save(self):
        name = self.device_combo.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Save Device", "Please select a device first."); return
        self.save_device_requested.emit(name)

    def _emit_apply(self):
        lo, hi = self.limits()
        if hi < lo:
            QMessageBox.warning(self, "Invalid Limits", "Maximum pressure must be greater than minimum.")
        else:
            self.apply_limits_requested.emit(lo, hi)

    # convenience for LF limits (MainWindow sets/reads these)
    def set_loadframe_limits(self, min_pos, max_pos, max_vel):
        self.lf_min_pos.setValue(float(min_pos))
        self.lf_max_pos.setValue(float(max_pos))
        self.lf_max_vel.setValue(float(max_vel))

    # existing pressure limit accessors (if you use them)
    @property
    def pressure_min_limit(self) -> float: return float(self.min_spin.value())
    @property
    def pressure_max_limit(self) -> float: return float(self.max_spin.value())
    def set_pressure_limits(self, lo_kpa: float, hi_kpa: float) -> None:
        self.set_limits(lo_kpa, hi_kpa)
