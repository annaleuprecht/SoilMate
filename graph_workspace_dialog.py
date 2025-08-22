# graph_workspace_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QListWidget,
    QListWidgetItem, QPushButton, QFileDialog, QSpinBox, QDoubleSpinBox, QSizePolicy
)
from PyQt5.QtCore import Qt
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
import numpy as np
from datetime import datetime

class GraphWorkspaceDialog(QDialog):
    """
    Post-test graphing workspace.
    - Lets user pick X and one-or-more Y variables from historical data
    - Plots in a pyqtgraph view
    - Save current canvas to PNG
    """
    def __init__(self, history_rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Graph Workspace")
        self.resize(980, 640)
        self.history = list(history_rows or [])

        # -------- Collect headers (union of keys) --------
        all_keys = set()
        for row in self.history:
            if isinstance(row, dict):
                all_keys.update(row.keys())
        self.headers = sorted(all_keys)

        # -------- UI --------
        root = QVBoxLayout(self)

        # ── Row 1: controls (X, smooth, downsample, buttons)
        ctrls = QHBoxLayout()
        root.addLayout(ctrls)

        # ---- choose numeric headers only for plotting
        self.numeric_headers = [k for k in self.headers if self._finite_count_for_key(k) >= 2]

        ctrls.addWidget(QLabel("X:"))
        self.cmb_x = QComboBox()
        # prefer time-like keys, but only those that are numeric
        self.cmb_x.addItems(self._preferred_x_first(self.numeric_headers) or self.numeric_headers)
        ctrls.addWidget(self.cmb_x)

        # Back-compat
        self.x_combo = self.cmb_x
        self.y_combo = QComboBox(); self.y_combo.setVisible(False)

        ctrls.addWidget(QLabel("Y: (multi-select)"))

        # (keep your Smooth / Downsample / Plot / Clear / Save / Close buttons as before)
        ctrls.addWidget(QLabel("Smooth (pts):"))
        self.sb_smooth = QSpinBox(); self.sb_smooth.setRange(1, 9999); self.sb_smooth.setValue(1)
        ctrls.addWidget(self.sb_smooth)

        ctrls.addWidget(QLabel("Downsample:"))
        self.ds_factor = QDoubleSpinBox(); self.ds_factor.setRange(1.0, 1000.0); self.ds_factor.setDecimals(1); self.ds_factor.setValue(1.0)
        ctrls.addWidget(self.ds_factor)

        self.btn_plot = QPushButton("Plot")
        self.btn_clear = QPushButton("Clear")
        self.btn_save = QPushButton("Save PNG")
        self.btn_close = QPushButton("Close")
        for b in (self.btn_plot, self.btn_clear, self.btn_save, self.btn_close):
            ctrls.addWidget(b)

        self.btn_plot.clicked.connect(self._plot_selected)
        self.btn_clear.clicked.connect(self._clear_plot)
        self.btn_save.clicked.connect(self._save_png)
        self.btn_close.clicked.connect(self.accept)   # closes the dialog

        # ── Row 2: Y list (checkboxes) — give it HEIGHT
        yrow = QHBoxLayout()
        root.addLayout(yrow)

        self.lst_y = QListWidget()
        self.lst_y.setSelectionMode(QListWidget.NoSelection)
        self.lst_y.setMinimumWidth(260)
        self.lst_y.setMinimumHeight(150)           # <-- ensures it’s visible
        self.lst_y.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # inside GraphWorkspaceDialog.__init__(...)
        # (re)create the X-axis combo as an instance attribute


        # Populate Y with numeric keys only (single loop)
        self.lst_y.clear()
        for k in self._preferred_y_first(self.numeric_headers):
            it = QListWidgetItem(k)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            it.setCheckState(Qt.Unchecked)
            self.lst_y.addItem(it)
        # click anywhere on the row to toggle
        self.lst_y.itemClicked.connect(lambda it: (it.setCheckState(
            Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked), self._plot_selected()))
        # auto-plot when boxes change via keyboard
        self.lst_y.itemChanged.connect(lambda _: self._plot_selected())

        # optional helpers
        btn_all = QPushButton("Select All Y"); btn_none = QPushButton("Select None")
        btn_all.clicked.connect(lambda: _set_all_y(Qt.Checked))
        btn_none.clicked.connect(lambda: _set_all_y(Qt.Unchecked))
        def _set_all_y(state):
            self.lst_y.blockSignals(True)
            for i in range(self.lst_y.count()):
                self.lst_y.item(i).setCheckState(state)
            self.lst_y.blockSignals(False)
            self._plot_selected()

        yrow.addWidget(self.lst_y, 1)
        yrow.addWidget(btn_all)
        yrow.addWidget(btn_none)

        # ── Plot area
        pg.setConfigOptions(antialias=True)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        self.plot.addLegend()
        root.addWidget(self.plot, 1)

        self._pens = [pg.mkPen(pg.intColor(i, hues=16), width=2) for i in range(16)]

    # ---------- helpers ----------
    @staticmethod
    def _nan_array(n):
        a = np.empty(n, dtype=float)
        a[:] = np.nan
        return a

    def _checked_y_keys(self):
        keys = []
        for i in range(self.lst_y.count()):
            it = self.lst_y.item(i)
            if it.checkState() == Qt.Checked:
                keys.append(it.text())
        return keys

    def _coerce_float(self, v):
        try:
            return float(v)
        except Exception:
            if isinstance(v, str):
                try:
                    # allow ISO8601 timestamp strings as X
                    return datetime.fromisoformat(v).timestamp()
                except Exception:
                    pass
            return np.nan

    def _finite_count_for_key(self, key):
        c = 0
        for r in self.history:
            if isinstance(r, dict):
                v = r.get(key)
                try:
                    if np.isfinite(float(v)):
                        c += 1
                except Exception:
                    # try robust coercion
                    if np.isfinite(self._coerce_float(v)):
                        c += 1
        return c

    def _series(self, key):
        vals = []
        for r in self.history:
            v = r.get(key) if isinstance(r, dict) else None
            vals.append(self._coerce_float(v))
        return np.array(vals, dtype=float)


    def _downsample(self, x, y, factor):
        if factor <= 1.0:
            return x, y
        step = int(max(1, round(factor)))
        return x[::step], y[::step]

    def _smooth(self, y, window_pts):
        if window_pts <= 1 or y.size < 3:
            return y
        k = int(max(2, min(window_pts, y.size)))
        # simple “fill missing then moving average”
        yy = y.copy()
        idx = np.arange(yy.size)
        good = np.isfinite(yy)
        if good.any():
            # interpolate gaps; if all NaN, just return as-is
            yy[~good] = np.interp(idx[~good], idx[good], yy[good])
        kernel = np.ones(k, dtype=float) / k
        return np.convolve(yy, kernel, mode='same')

    def set_variable_catalog(self, items, desc=None):
        self._var_items = items
        self._var_desc = desc or {}
        def fill(combo):
            combo.clear()
            model = combo.model()
            last_group = None
            from PyQt5.QtGui import QStandardItem
            for label, key, group in items:
                if group != last_group:
                    hdr = QStandardItem(group)
                    f = hdr.font(); f.setBold(True); hdr.setFont(f)
                    hdr.setFlags(Qt.NoItemFlags)
                    model.appendRow(hdr)
                    last_group = group
                combo.addItem(label, userData=key)
        fill(self.x_combo)
        fill(self.y_combo)

    def _plot_selected(self):
        self._clear_plot()
        x_key = self.cmb_x.currentText().strip()
        y_keys = self._checked_y_keys()
        if not y_keys:
            return

        # If current X isn’t numeric, pick the first good one
        if self._finite_count_for_key(x_key) < 2:
            for k in self._preferred_x_first(self.numeric_headers):
                if self._finite_count_for_key(k) >= 2:
                    self.cmb_x.setCurrentText(k)
                    x_key = k
                    break

        x = self._series(x_key)
        # drop rows where X is non-finite up front
        finite_x = np.isfinite(x)
        if finite_x.sum() < 2:
            return
        x = x[finite_x]
        self.plot.setLabel('bottom', x_key)

        for yk in y_keys:
            if self._finite_count_for_key(yk) < 2:
                continue
            y = self._series(yk)[finite_x]
            mask = np.isfinite(y)
            if mask.sum() == 0:
                continue

            yy = self._smooth(y[mask], self.sb_smooth.value())
            xx = x[mask]
            xx, yy = self._downsample(xx, yy, self.ds_factor.value())
            pen = self._pens[(hash(yk) % len(self._pens))]
            self.plot.plot(xx, yy, name=yk, pen=pen)


    def _clear_plot(self):
        self.plot.clear()
        self.plot.addLegend()

    def _save_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Graph as PNG",
            "plot.png",
            "PNG Images (*.png)"
        )
        if not path:
            return
        exp = ImageExporter(self.plot.plotItem)
        exp.export(path)

    @staticmethod
    def _preferred_x_first(keys):
        # Common X preferences to top
        pref = ["test_elapsed_s", "stage_elapsed_s", "time_s", "timestamp"]
        rest = [k for k in keys if k not in pref]
        return [k for k in pref if k in keys] + sorted(rest)

    @staticmethod
    def _preferred_y_first(keys):
        # Common Y preferences to top
        pref = [
            "cell_pressure_kpa", "back_pressure_kpa",
            "cell_volume_mm3", "back_volume_mm3",
            "position_mm",
            "axial_load_kN", "pore_pressure_kpa", "axial_displacement_mm"
        ]
        rest = [k for k in keys if k not in pref]
        return [k for k in pref if k in keys] + sorted(rest)
