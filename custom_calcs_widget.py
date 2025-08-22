# custom_calcs_widget.py
from dataclasses import dataclass, asdict
from typing import List
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QCheckBox, QInputDialog, QLineEdit, QLabel, QComboBox
)
from PyQt5.QtCore import pyqtSignal, Qt, QVariant
from calc_editor_dialog import CalcEditorDialog
from typing import List, Dict

@dataclass
class CalcDef:
    key: str
    expr: str
    label: str = ""
    enabled: bool = True
    live: bool = False

    @property
    def name(self) -> str:
        """For backward compatibility — some code still expects .name"""
        return self.key


# ---- Preset catalog shown in the dropdown ----
# Internal key -> (Friendly label shown in UI, Expression)
PRESET_CALCS = {
    "current_height_mm": ("Current Height (mm)", "h0_mm - (disp_mm - disp_start_mm)"),
    "current_area_mm2":  ("Current Area (mm²)",  "A0_mm2 / (1 - eps_axial)"),
    "sigma3_kpa":        ("Radial Stress σ3 (kPa)", "cell_pressure_kpa"),
    "sigma1_kpa":        ("Axial Stress σ1 (kPa)",  "(sigma3_kpa*(current_area_mm2) + force_N)/current_area_mm2"),
    "eff_sigma3_kpa":    ("Effective Radial Stress (kPa)", "sigma3_kpa - pore_pressure_kpa"),
    "eff_sigma1_kpa":    ("Effective Axial Stress (kPa)",  "sigma1_kpa - pore_pressure_kpa"),
    "q_kpa":             ("Deviator Stress (kPa)",         "eff_sigma1_kpa - eff_sigma3_kpa"),
    "pprime_kpa":        ("Effective Mean Stress s (kPa)", "(eff_sigma1_kpa + 2*eff_sigma3_kpa)/3"),
}

DEFAULT_SET: List[CalcDef] = []

class CustomCalcsWidget(QGroupBox):
    changed = pyqtSignal(list)        # emits List[CalcDef]
    toggled_live = pyqtSignal(list)   # emits names selected for live readout

    def __init__(self, title="Custom Calculations", parent=None):
        super().__init__(title, parent)
        self._calcs: List[CalcDef] = [CalcDef(**asdict(c)) for c in DEFAULT_SET]

        root = QVBoxLayout(self)
        # --- Row: preset dropdown + Add ---
        row = QHBoxLayout()
        self.preset = QComboBox()
        for key, (label, expr) in PRESET_CALCS.items():
            self.preset.addItem(label, userData=key)
        self.preset.addItem("Custom…", userData="__CUSTOM__")

        self.btn_add = QPushButton("+ Add")
        row.addWidget(self.preset, 1)
        row.addWidget(self.btn_add)
        root.addLayout(row)

        # --- Selected calcs list (check to enable/disable) ---
        self.listw = QListWidget()
        self.listw.setAlternatingRowColors(True)
        root.addWidget(self.listw)

        # --- Live readout toggle + label ---
        self.live_box = QCheckBox("Show selected calcs in Live Readout")
        root.addWidget(self.live_box)
        self.live_label = QLabel("—")
        self.live_label.setWordWrap(True)
        self.live_label.setStyleSheet("color:#444;")
        root.addWidget(self.live_label)

        # --- Buttons row ---
        btns = QHBoxLayout()
        self.btn_edit  = QPushButton("Edit")
        self.btn_del   = QPushButton("Delete")
        self.btn_reset = QPushButton("Reset")
        btns.addWidget(self.btn_edit)
        btns.addWidget(self.btn_del)
        btns.addStretch(1)
        btns.addWidget(self.btn_reset)
        root.addLayout(btns)

        # Wire up
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_del.clicked.connect(self._on_delete)
        self.btn_reset.clicked.connect(self._on_reset)
        self.live_box.stateChanged.connect(self._emit_live)
        self.listw.itemChanged.connect(self._on_list_changed)
        self._refresh()

        self._var_catalog: Dict[str, str] = {}   # name -> description
        self.listw.itemDoubleClicked.connect(lambda _: self._on_edit())


    # ---- UI helpers ----
    def _refresh(self):
        self.listw.blockSignals(True)
        self.listw.clear()
        for c in self._calcs:
            label = c.label or c.key
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, c.key)   # keep internal key
            it.setCheckState(Qt.Checked if c.enabled else Qt.Unchecked)
            it.setToolTip(c.expr)
            self.listw.addItem(it)

        self.listw.blockSignals(False)
        self.changed.emit(self.calcs())
        if self.live_box.isChecked():
            self._emit_live()


    def _on_list_changed(self, _item):
        # keep the normal "calcs changed" signal
        self.changed.emit(self.calcs())
        # and if live mode is on, re-emit the live selection now
        if self.live_box.isChecked():
            self._emit_live()

    # ---- Actions ----
    def _on_add(self):
        key = self.preset.currentData()
        if key == "__CUSTOM__":
            # open editor as before
            ...
            return

        expr = PRESET_CALCS[key][1]
        label = PRESET_CALCS[key][0]
        # enable if exists, else add
        for c in self._calcs:
            if c.key == key:
                c.enabled = True
                self._refresh()
                return
        self._calcs.append(CalcDef(key=key, expr=expr, label=label, enabled=True))
        self._refresh()


    def _on_edit(self):
        idx = self.listw.currentRow()
        if idx < 0: return
        c = self._calcs[idx]
        dlg = CalcEditorDialog(
            title="Edit Calculation",
            name=c.name,
            expr=c.expr,
            variables=self._var_catalog,
            parent=self
        )
        if dlg.exec_() != dlg.Accepted:
            return
        name, expr = dlg.values()
        if not name or not expr:
            return
        c.name, c.expr = name, expr
        self._refresh()

    def _on_delete(self):
        idx = self.listw.currentRow()
        if idx < 0: return
        del self._calcs[idx]
        self._refresh()

    def _on_reset(self):
        self._calcs = [CalcDef(**asdict(c)) for c in DEFAULT_SET]
        self._refresh()

    def _emit_live(self):
        keys = []
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            if it.checkState() == Qt.Checked:
                keys.append(it.data(Qt.UserRole))  # internal key
        self.toggled_live.emit(keys if self.live_box.isChecked() else [])



    # ---- External API ----
    def calcs(self) -> List[CalcDef]:
        for i, c in enumerate(self._calcs):
            it = self.listw.item(i)
            c.enabled = (it.checkState() == Qt.Checked)
            # don’t overwrite key! preserve friendly label
            c.label = it.text()
        return self._calcs


    def set_available_vars(self, var_catalog: Dict[str, str]):
        """var_catalog: name -> description (can include units)."""
        self._var_catalog = dict(var_catalog or {})

