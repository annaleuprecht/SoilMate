# calc_editor_dialog.py
from typing import Dict, Tuple
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QListWidget, QListWidgetItem, QPushButton
)
from PyQt5.QtCore import Qt

# Shown if caller didn't provide a catalog
DEFAULT_VARS: Dict[str, str] = {
    "timestamp":         "Unix seconds",
    "test_elapsed_s":    "Elapsed since test start (s)",
    "stage_elapsed_s":   "Elapsed since stage start (s)",
    "cell_pressure_kpa": "Cell pressure (kPa)",
    "back_pressure_kpa": "Back/pore pressure (kPa)",
    "pore_pressure_kpa": "Pore pressure (kPa)",
    "cell_volume_mm3":   "Cell volume change (mm³)",
    "back_volume_mm3":   "Back volume change (mm³)",
    "position_mm":       "Axial position / displacement (mm)",
    "force_N":           "Axial force (N)",
    "force_kN":          "Axial force (kN)",
    "initial_area_mm2":  "Initial area (mm²)",
    "initial_height_mm": "Initial height (mm)",
    "initial_volume_mm3":"Initial volume (mm³)",
    "axial_strain_frac": "Axial strain (fraction, e.g., 0.012)",
    "axial_strain_pct":  "Axial strain (%)",
    "disp_start_mm":     "Displacement at stage start (mm)",
    "vol_start_mm3":     "Volume at stage start (mm³)",
    # Common derived aliases your context exposes:
    "A0_mm2":            "Alias of initial_area_mm2 (mm²)",
    "h0_mm":             "Alias of initial_height_mm (mm)",
    "v0_mm3":            "Alias of initial_volume_mm3 (mm³)",
    "sigma3_kpa":        "Alias of cell_pressure_kpa (kPa)",
}

class CalcEditorDialog(QDialog):
    """
    Edit (name, expression) with a searchable variable list on top,
    and an expression builder box at the bottom.
    """
    def __init__(self, *, title="Edit Calculation", name="", expr="",
                 variables: Dict[str, str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._vars: Dict[str, str] = (variables or DEFAULT_VARS)

        root = QVBoxLayout(self)

        # --- Name ---
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit(name)
        name_row.addWidget(self.name_edit, 1)
        root.addLayout(name_row)

        # --- Variables header (search + Insert button) ---
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Variables"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search variables…")
        hdr.addWidget(self.search, 1)
        self.insert_btn = QPushButton("Insert")
        hdr.addWidget(self.insert_btn)
        root.addLayout(hdr)

        # --- Variable list (full, multi-select) ---
        self.var_list = QListWidget()
        self.var_list.setAlternatingRowColors(True)
        self.var_list.setSelectionMode(QListWidget.ExtendedSelection)
        root.addWidget(self.var_list, 1)

        # Info line for selected variable
        self.var_info = QLabel(" ")
        self.var_info.setStyleSheet("color:#666;")
        root.addWidget(self.var_info)

        # --- Quick operators ---
        ops = QHBoxLayout()
        for sym in ["+", "-", "*", "/", "**", "(", ")", ","]:
            b = QPushButton(sym)
            b.setFixedWidth(28)
            b.clicked.connect(lambda _, s=sym: self._insert_text(s))
            ops.addWidget(b)
        ops.addStretch(1)
        root.addLayout(ops)

        # --- Expression editor (bottom) ---
        root.addWidget(QLabel("Expression"))
        self.expr_edit = QPlainTextEdit(expr or "")
        self.expr_edit.setPlaceholderText(
            "Build your expression here. Double-click a variable above or select and press Insert."
        )
        self.expr_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.expr_edit.setTabChangesFocus(True)
        self.expr_edit.setFixedHeight(110)
        self.expr_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")
        root.addWidget(self.expr_edit)

        # --- Buttons ---
        br = QHBoxLayout()
        br.addStretch(1)
        ok = QPushButton("OK"); ok.setDefault(True)
        cancel = QPushButton("Cancel")
        br.addWidget(ok); br.addWidget(cancel)
        root.addLayout(br)

        # Wire up
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self.search.textChanged.connect(self._refilter)
        self.var_list.itemDoubleClicked.connect(self._insert_selected)
        self.var_list.currentItemChanged.connect(self._update_info)
        self.insert_btn.clicked.connect(self._insert_selected)

        self._populate()
        self.resize(640, 600)

    # ---------- helpers ----------
    def _populate(self):
        self.var_list.clear()
        for name, desc in sorted(self._vars.items()):
            it = QListWidgetItem(name)
            it.setToolTip(desc or name)
            self.var_list.addItem(it)
        # select first for convenience
        if self.var_list.count():
            self.var_list.setCurrentRow(0)
            self._update_info(self.var_list.item(0), None)

    def _refilter(self, text: str):
        q = (text or "").lower().strip()
        any_visible = False
        for i in range(self.var_list.count()):
            it = self.var_list.item(i)
            show = (q in it.text().lower()) or (q in (it.toolTip() or "").lower())
            it.setHidden(not show)
            if show and not any_visible:
                self.var_list.setCurrentItem(it)
                self._update_info(it, None)
                any_visible = True
        if not any_visible:
            self._update_info(None, None)

    def _update_info(self, item, _prev):
        if not item:
            self.var_info.setText(" ")
            return
        self.var_info.setText(item.toolTip() or item.text())

    def _insert_text(self, s: str):
        e = self.expr_edit
        cursor = e.textCursor()
        cursor.insertText(s)
        e.setTextCursor(cursor)
        e.setFocus()

    def _insert_selected(self, _item=None):
        items = self.var_list.selectedItems()
        if not items:
            it = self.var_list.currentItem()
            if not it:
                return
            items = [it]
        # insert names separated by nothing (you can change to spaces)
        for it in items:
            self._insert_text(it.text())

    # ---------- API ----------
    def values(self) -> Tuple[str, str]:
        name = self.name_edit.text().strip()
        expr = " ".join(self.expr_edit.toPlainText().splitlines()).strip()
        return name, expr
