from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QPushButton, QComboBox, QListWidget, QListWidgetItem, QGridLayout,
    QScrollArea, QFrame, QTabWidget, QListView, QFileDialog, QMessageBox, QStackedLayout,
    QApplication, QDialog, QDialogButtonBox, QInputDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QStandardItem
from collections import deque
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
import os
import re
import csv
from datetime import datetime
from graph_workspace_dialog import GraphWorkspaceDialog
from custom_calcs_widget import CustomCalcsWidget, CalcDef
from safe_eval import eval_expr
from typing import List
import math
from math import sqrt, pi
import time
from test_set_up_page import TestSetupPage

class StageEditDialog(QDialog):
    def __init__(self, parent=None, stages=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Stages")
        self.resize(1000, 700)

        layout = QVBoxLayout(self)
        self.editor = TestSetupPage(self)      # reuse full setup page
        if stages is not None:
            # load existing StageData objects into the editor
            self.editor.stage_data_list = stages
            for data in stages:
                self.editor.add_stage()  # populates list + editors

        layout.addWidget(self.editor)

        # OK / Cancel buttons
        btns = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

class _CalcColumnsDialog(QDialog):
    """Multi-select picker for calculated/custom export columns."""
    def __init__(self, choices, parent=None):
        """
        choices: list[(label, key)] from _gdslab_catalog() filtered to Calculated/Custom
        """
        super().__init__(parent)
        self.setWindowTitle("Add calculated columns")
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Choose calculated/custom columns to include in the CSV:"))

        self.list = QListWidget()
        for label, key in choices:
            it = QListWidgetItem(label, self.list)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            it.setData(Qt.UserRole, key)
        lay.addWidget(self.list)

        # Buttons
        row = QHBoxLayout()
        btn_all = QPushButton("Select All");  btn_none = QPushButton("Clear")
        btn_all.clicked.connect(lambda: [self.list.item(i).setCheckState(Qt.Checked) for i in range(self.list.count())])
        btn_none.clicked.connect(lambda: [self.list.item(i).setCheckState(Qt.Unchecked) for i in range(self.list.count())])
        row.addWidget(btn_all); row.addWidget(btn_none); row.addStretch(1)
        lay.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def selected_keys(self) -> list:
        keys = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.Checked:
                keys.append(it.data(Qt.UserRole))
        return keys



class CompletionCard(QWidget):
    run_again = pyqtSignal()
    back_to_setup = pyqtSignal()
    export_data = pyqtSignal()
    exit_requested = pyqtSignal()
    make_graphs = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._title = QLabel("Test Complete")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setFont(QFont("Segoe UI", 20, QFont.Bold))

        self._subtitle = QLabel("All stages finished successfully.")
        self._subtitle.setAlignment(Qt.AlignCenter)

        # Summary lines
        self._stages = QLabel("Stages Completed: –")
        self._duration = QLabel("Total Duration: –")
        self._points = QLabel("Data Points: –")
        self._filepath = QLabel("Saved To: –")
        self._history = deque(maxlen=200000)   # keep lots of samples for export

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)

        # Buttons
        self._btn_run_again = QPushButton("🔄 Run Another Test")
        self._btn_export = QPushButton("📂 Export Data")
        self.btn_make_graphs = QPushButton("📈 Make Graphs")
        self._btn_exit = QPushButton("🚪 Exit Software")

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self._btn_run_again)   # <— ADD THIS
        btns.addWidget(self._btn_export)
        btns.addWidget(self.btn_make_graphs)
        btns.addWidget(self._btn_exit)
        btns.addStretch(1)

        # Wire signals
        self._btn_run_again.clicked.connect(self.run_again.emit)
        self.btn_make_graphs.clicked.connect(self.make_graphs.emit)   # NEW
        self._btn_export.clicked.connect(self.export_data.emit)
        self._btn_exit.clicked.connect(self.exit_requested.emit)

        # Root layout
        root = QVBoxLayout(self)
        root.addSpacing(8)
        root.addWidget(self._title)
        root.addWidget(self._subtitle)
        root.addSpacing(12)
        root.addWidget(self._stages)
        root.addWidget(self._duration)
        root.addWidget(self._points)
        root.addWidget(self._filepath)
        root.addSpacing(12)
        root.addWidget(divider)
        root.addSpacing(8)
        root.addLayout(btns)
        root.addStretch(1)

    def update_summary(self, *, stages: int, duration: str, datapoints: int, filepath: str, subtitle: str = None):
        """Call this once you have your summary stats ready."""
        if subtitle:
            self._subtitle.setText(subtitle)
        self._stages.setText(f"✅ Stages Completed: {stages}")
        self._duration.setText(f"⏱ Total Duration: {duration}")
        self._points.setText(f"📊 Data Points: {datapoints:,}")
        self._filepath.setText(f"💾 Data Saved To: {filepath}")

class TestViewPage(QWidget):
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    next_stage_requested = pyqtSignal()
    end_test_requested = pyqtSignal()
    run_another_test_requested = pyqtSignal()
    back_to_setup_requested = pyqtSignal()
    start_test_clicked = pyqtSignal()

    MAX_POINTS = 2000        # ~few minutes at 5 Hz
    DOWNSAMPLE_OVER = 1500   # start striding after this

    def __init__(self, stages=None, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window   # <-- add this
        self.setFont(QFont("Segoe UI", 12))
        self._stages = []
        self._graph_cards = []
        self.start_time = None
        self.shared_data = {}
        self._history = deque(maxlen=5000)
        self.current_stage_index = 0
        self.is_complete = False
        self._post_stop_cancelled = False
        self._in_post_stop_flow = False
        self._suppress_post_stop_until = 0.0   # monotonic timestamp
        self._cancelled_resume = False
        self._block_completion_until = 0.0  # monotonic timestamp
        self._skip_graph_prompt = False   # 🔑 add this flag


        self._dirty = False
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(300)     # 0.3 s repaint cadence
        self._render_timer.setTimerType(Qt.CoarseTimer)
        self._render_timer.timeout.connect(self._render)
        self._render_timer.start()

        # ===== Title =====
        title_row = QHBoxLayout()
        title = QLabel("Test View")
        title.setObjectName("TitleLabel")
        self.current_left = QLabel("Current Stage:")
        self.current_right = QLabel("Current Stage: —")
        title_row.addWidget(self.current_left)
        title_row.addStretch(1)

        self.btn_start_test = QPushButton("▶ Start Test")
        self.btn_start_test.setObjectName("PrimaryButton")
        self.btn_start_test.clicked.connect(self.start_test_clicked.emit)
        title_row.addWidget(self.btn_start_test)

        title_row.addWidget(self.current_right)

        # ===== Left card: Stages =====
        left_card = QGroupBox("Stages")
        left_card.setObjectName("Card")
        left_col = QVBoxLayout(left_card)
        left_col.setContentsMargins(12, 10, 12, 12)
        self.stage_list = QListWidget()
        self.stage_list.setAlternatingRowColors(True)
        left_col.addWidget(self.stage_list)

        self._calc_panel = CustomCalcsWidget()
        left_col.addWidget(self._calc_panel)   # <-- add panel under the existing stage_list


        # Hold current calc set & live names
        self._calc_defs: List[CalcDef] = self._calc_panel.calcs()
        self._live_calc_names: set[str] = {c.key for c in self._calc_defs if c.live}

        self._calc_panel.changed.connect(self._on_calcs_changed)
        self._calc_panel.toggled_live.connect(self._on_live_toggled)

        # Variables captured at stage start (you likely already have these — set them there)
        self._baselines = {
            "disp_start_mm": 0.0,
            "vol_start_mm3": 0.0,
            "u_start_kpa":   0.0,   # NEW: pore/back pressure at stage start
            "cell_start_kpa":0.0,   # NEW: cell pressure at stage start
        }

        # Make graph dropdowns see calc names too
        self._builtin_keys = [
            "timestamp", "cell_pressure_kpa", "back_pressure_kpa",
            "cell_volume_mm3", "back_volume_mm3", "position_mm",
            "pore_pressure_kpa", "force_N", "eps_axial", "h0_mm",
            "v0_mm3", "A0_mm2", "sigma3_kpa"  # etc if you already expose some
        ]


        # ===== Right card: Charts =====
        right_card = QGroupBox("Live Charts")
        right_card.setObjectName("Card")
        right_col = QVBoxLayout(right_card)
        right_col.setContentsMargins(12, 10, 12, 12)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("View Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Grid View", "Tab View"])   # <— tab mode
        controls.addWidget(self.mode_combo)
        controls.addStretch(1)
        self.add_graph_btn = QPushButton("+ Add Graph")
        self.del_graph_btn = QPushButton("Delete Graph")
        self.reset_btn = QPushButton("Reset Layout")
        self.save_btn = QPushButton("Save Graphs")
        self.save_btn.clicked.connect(self.export_graphs)
        controls.addWidget(self.save_btn)

        controls.addWidget(self.add_graph_btn)
        controls.addWidget(self.del_graph_btn)
        controls.addWidget(self.reset_btn)
        right_col.addLayout(controls)

        controls = QHBoxLayout()
        self.btn_pause = QPushButton("Pause Stage")
        self.btn_continue = QPushButton("Continue Stage")
        self.btn_stop = QPushButton("Stop Stage")

        self.btn_continue.setEnabled(False)  # only after pausing
        controls.addWidget(self.btn_pause)
        controls.addWidget(self.btn_continue)
        controls.addWidget(self.btn_stop)

        # wire signals
        self.btn_pause.clicked.connect(self.pause_requested.emit)
        self.btn_continue.clicked.connect(self.resume_requested.emit)
        self.btn_stop.clicked.connect(self.stop_requested.emit)

        # add to the same header row you already have (right-aligned)
        title_row.addStretch(1)
        title_row.addLayout(controls)


        # --- Grid container (default)
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        grid_wrap = QWidget()
        self.grid_scroll.setWidget(grid_wrap)
        self.grid = QGridLayout(grid_wrap)
        self.grid.setSpacing(10)
        self.grid.setContentsMargins(0, 0, 0, 0)
        right_col.addWidget(self.grid_scroll, 1)

        # --- Tab container (hidden until selected)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab_requested)
        self.tabs.hide()
        right_col.addWidget(self.tabs, 1)

        # ===== Split layout =====
        split = QHBoxLayout()
        split.addWidget(left_card, 1)
        split.addWidget(right_card, 2)

        # ===== Page =====
        self._normal_container = QWidget(self)
        page = QVBoxLayout(self._normal_container)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(10)
        page.addWidget(title)
        page.addLayout(title_row)
        page.addLayout(split, 1)

        # ===== Completion card (hidden initially) =====
        self._complete_card = CompletionCard(self)
        self._complete_card.back_to_setup.connect(self.back_to_setup_requested)
        self._complete_card.run_again.connect(self.run_another_test_requested)
        self._complete_card.export_data.connect(self.export_data_flow)
        self._complete_card.exit_requested.connect(lambda: QApplication.instance().quit())
        self._complete_card.make_graphs.connect(self._open_graph_workspace)

        # ===== Stacked layout to swap views =====
        self._stack = QStackedLayout()
        self._stack.addWidget(self._normal_container)  # index 0
        self._stack.addWidget(self._complete_card)     # index 1

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._stack)

        # ===== Style =====
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
            QPushButton#PrimaryButton {
                background: #0078d7; color: white; border: none; border-radius: 6px;
                padding: 8px 16px; font-weight: 700;
            }
            QPushButton#PrimaryButton:hover { background: #006cbe; }
            QPushButton#DangerButton {
                background: #e55353; color: white; border: none; border-radius: 6px;
                padding: 8px 16px; font-weight: 700;
            }
            QPushButton#DangerButton:hover { background: #d64545; }

            /* make the little close button visible */
            QPushButton#CloseButton {
                min-width: 22px; min-height: 22px; padding: 0;
                border: 1px solid #cfcfcf; border-radius: 4px;
                background: #f5f5f5;
            }
            QPushButton#CloseButton:hover { background: #ececec; }
            QPushButton#CloseButton:pressed { background: #e0e0e0; }
        """)

        # ===== Wire up =====
        self.add_graph_btn.clicked.connect(self.add_graph)
        self.reset_btn.clicked.connect(self.reset_layout)
        self.del_graph_btn.clicked.connect(self.delete_last_graph)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        if stages:
            self.load_stages(stages)


    def _ask_export_calcs(self) -> list:
        """Show a picker of Calculated/Custom vars and return selected keys."""
        items, _ = self._gdslab_catalog()
        choices = [(label, key) for (label, key, group) in items if group in ("Calculated", "Custom")]
        if not choices:
            return []
        dlg = _CalcColumnsDialog(choices, self)
        return dlg.selected_keys() if dlg.exec_() == QDialog.Accepted else []

    def _compute_derived_for_export(self, row: dict, wanted_keys: list) -> dict:
        """
        Recompute a subset of derived/custom values for a single row so the CSV
        always has the requested columns, even if they weren’t present live.
        """
        r = dict(row)  # don’t mutate input
        self._ensure_geometry_from_tm()

        # Normalize/seed basics
        A0 = float(r.get("initial_area_mm2") or getattr(self, "_A0_mm2", 0.0) or 0.0)
        h0 = float(r.get("initial_height_mm") or getattr(self, "_h0_mm",  0.0) or 0.0)
        r.setdefault("position_mm", r.get("disp_mm", 0.0))
        sigma3 = float(r.get("cell_pressure_kpa") or r.get("sigma3_kpa") or 0.0)
        u      = float(r.get("pore_pressure_kpa") or r.get("back_pressure_kpa") or 0.0)

        # Axial strain (if missing)
        eps = r.get("axial_strain_frac")
        if eps is None:
            pct = r.get("axial_strain_pct")
            if pct is not None:
                try: eps = float(pct) / 100.0
                except Exception: eps = None
        if eps is None and h0 > 0:
            d  = float(r.get("position_mm") or 0.0)
            d0 = float(self._baselines.get("disp_start_mm", 0.0))
            eps = (d - d0) / h0
        if eps is not None:
            r["axial_strain_frac"] = eps
            r["axial_strain_pct"]  = float(eps) * 100.0

        # Geometry from axial strain (no radial sensors needed)
        if A0 > 0 and eps is not None:
            denom = 1.0 - float(eps)
            r["current_area_mm2"] = (A0 / denom) if abs(denom) > 1e-12 else float("nan")
            d0 = math.sqrt(4*A0/math.pi)
            if r.get("current_area_mm2") and math.isfinite(r["current_area_mm2"]):
                dn = math.sqrt(4*r["current_area_mm2"]/math.pi)
                r["current_diameter_mm"] = dn
                r["radial_strain_pct"] = (dn - d0) / d0 * 100.0
        if h0 > 0:
            d  = float(r.get("position_mm") or 0.0)
            d0 = float(self._baselines.get("disp_start_mm", 0.0))
            r["current_height_mm"] = h0 - (d - d0)

        # Force (kN preferred)
        ax_kN = None
        for k in ("axial_force_kN","force_kN","load_kN","axial_load_kN"):
            v = r.get(k); 
            if v is not None:
                try:
                    ax_kN = float(v); break
                except Exception: pass
        if ax_kN is None:
            for k in ("force_N","axial_force_N","load_N"):
                v = r.get(k)
                if v is not None:
                    try: ax_kN = float(v)/1000.0; break
                    except Exception: pass
        if ax_kN is None: ax_kN = 0.0
        r["axial_force_kN"] = ax_kN
        r["force_N"] = ax_kN * 1000.0

        # Stresses
        area_for_stress = (r.get("current_area_mm2") or r.get("area_mm2") or A0)
        sigma1_from_force = (r["force_N"] / float(area_for_stress) * 1000.0) if area_for_stress else 0.0
        sigma1_total = float(sigma3) + sigma1_from_force
        r["axial_stress_kpa"] = sigma1_from_force
        r["sigma1_kpa"]       = sigma1_total
        r["eff_sigma3_kpa"]   = float(sigma3) - float(u)
        r["eff_sigma1_kpa"]   = float(sigma1_total) - float(u)
        r["q_kpa"]            = r["eff_sigma1_kpa"] - r["eff_sigma3_kpa"]
        r["pprime_kpa"]       = (r["eff_sigma1_kpa"] + 2*r["eff_sigma3_kpa"]) / 3.0
        r["max_shear_stress_kpa"] = r["q_kpa"] / 2.0

        # B-value from stage start deltas
        du    = float(u)      - float(self._baselines.get("u_start_kpa",   u))
        dcell = float(sigma3) - float(self._baselines.get("cell_start_kpa",sigma3))
        r["b_value"] = (du / dcell) if abs(dcell) > 1e-6 else float("nan")

        # Custom calcs (use same safe evaluator)
        ctx = self._calc_context_from(r)
        for c in self._calc_defs:
            if c.enabled and c.name in wanted_keys:
                try:
                    r[c.name] = eval_expr(c.expr, ctx)
                except Exception:
                    r[c.name] = float('nan')

        return {k: r.get(k) for k in wanted_keys}

    def show_completion_summary(self, summary_data: dict):
        """
        summary_data = {
            "stages": int,
            "duration": "3h 27m",
            "datapoints": int,
            "filepath": "C:/path/file.csv",
            "subtitle": "All stages finished successfully."  # optional
        }
        """
        if getattr(self, "_in_post_stop_flow", False):
        # We're in the Stop → dialog flow; don't flip views.
            return

        if getattr(self, "_cancelled_resume", False):
        # one-shot consume, then allow future completions
            self._cancelled_resume = False
            return
        if time.monotonic() < getattr(self, "_block_completion_until", 0.0):
            return
        if getattr(self, "_post_stop_cancelled", False):
            self._post_stop_cancelled = False
            try: self._stack.setCurrentWidget(self._normal_container)
            except Exception: pass
            self._set_stage_controls_enabled(True)
            try: self._render_timer.start()
            except Exception: pass
            return

        self.is_complete = True
        self._freeze_live_updates()
        self._complete_card.update_summary(
            stages=summary_data.get("stages", 0),
            duration=summary_data.get("duration", "—"),
            datapoints=summary_data.get("datapoints", 0),
            filepath=summary_data.get("filepath", "—"),
            subtitle=summary_data.get("subtitle")
        )
        self._complete_card.show()
        self._stack.setCurrentWidget(self._complete_card)

    def on_stage_started(self, snapshot: dict):
        self._suppress_post_stop_until = 0.0
        self._cancelled_resume = False
        self._block_completion_until = 0.0
        self._baselines["disp_start_mm"]  = float(snapshot.get("position_mm", snapshot.get("disp_mm", 0.0)) or 0.0)
        self._baselines["vol_start_mm3"]  = float(snapshot.get("cell_volume_mm3", snapshot.get("vol_mm3", 0.0)) or 0.0)
        self._baselines["u_start_kpa"]    = float(snapshot.get("pore_pressure_kpa", snapshot.get("back_pressure_kpa", 0.0)) or 0.0)
        self._baselines["cell_start_kpa"] = float(snapshot.get("cell_pressure_kpa", snapshot.get("sigma3_kpa", 0.0)) or 0.0)
        # if you also track stage_start_ts elsewhere, keep doing that as-is
        # reference stage timestamp (fallback to 'now' if snapshot lacks one)
        self.stage_start_ts = float(snapshot.get("timestamp", time.time()))

    def _on_calcs_changed(self, defs):
        self._calc_defs = defs
        self._refresh_axis_dropdowns()
        # Also refresh live names if live mode is on
        try:
            if self._calc_panel.live_box.isChecked():
                # recompute from panel
                self._on_live_toggled([c.name for c in self._calc_panel.calcs() if c.enabled])
        except Exception:
            pass


    def _on_live_toggled(self, _names):
        self._live_calc_names = {c.key for c in self._calc_panel.calcs() if c.enabled}


    def _refresh_axis_dropdowns(self):
        # vars available to the editor/search list
        var_catalog = {
            "timestamp": "Unix seconds",
            "test_elapsed_s": "Elapsed since test start (s)",
            "stage_elapsed_s": "Elapsed since stage start (s)",
            "cell_pressure_kpa": "Cell Pressure (kPa)",
            "back_pressure_kpa": "Back/Pore Pressure (kPa)",
            "pore_pressure_kpa": "Pore Pressure (kPa)",
            "cell_volume_mm3": "Cell Volume Change (mm³)",
            "back_volume_mm3": "Back Volume Change (mm³)",
            "position_mm": "Chamber Displacement (mm)",
            "force_N": "Axial Force (N)",
            "axial_force_kN": "Axial Force (kN)",
            "initial_area_mm2": "Initial Area A₀ (mm²)",
            "initial_height_mm": "Initial Height h₀ (mm)",
            "initial_volume_mm3": "Initial Volume V₀ (mm³)",
            "axial_strain_frac": "Axial Strain (fraction)",
            "axial_strain_pct": "Axial Strain (%)",
            "disp_start_mm": "Displacement at stage start (mm)",
            "vol_start_mm3": "Volume at stage start (mm³)",
            "sigma3_kpa": "Radial Stress σ₃ (kPa)",
        }
        for c in self._calc_defs:
            if c.enabled:
                var_catalog.setdefault(c.name, "Custom calculation")

        try:
            self._calc_panel.set_available_vars(var_catalog)
        except Exception:
            pass

        # friendly, grouped menu for graph combos
        items, _ = self._gdslab_catalog()
        for card in self._graph_cards:
            if hasattr(card, "set_available_series_grouped"):
                card.set_available_series_grouped(items)



    def _route_to_graph_cards(self, reading: dict):
        """Send an enriched reading to all graphs, respecting per-stage views, and log it."""
        if not reading:
            return

        # Stage sync (use value from reading if present)
        si = reading.get("stage_index", self.current_stage_index)
        if si != self.current_stage_index:
            self.set_current_stage(si)

        # Feed each graph card
        for card in getattr(self, "_graph_cards", []):
            xk = getattr(card, "get_x_key", lambda: None)()
            # Per-stage graphs only show the active stage
            if xk in ("stage_elapsed_s", "time_s") and si != self.current_stage_index:
                continue
            try:
                card.update_data(reading)
            except Exception as e:
                print("[Plot] update error:", e)

        # Keep a copy in history (for export / workspace)
        try:
            self._history.append({k: reading.get(k) for k in reading.keys()})
        except Exception:
            pass

    def _gdslab_catalog(self):
        items = [
            # ---- Read (direct measurements) ----
            ("Time Since Start of Test (s)", "test_elapsed_s", "Read"),
            ("Time Since Start of Stage (s)", "stage_elapsed_s", "Read"),
            ("Square root time since start of stage (s^0.5)", "sqrt_stage_time_s", "Read"),
            ("Cell Pressure (kPa)", "cell_pressure_kpa", "Read"),
            ("Back Pressure (kPa)", "back_pressure_kpa", "Read"),
            ("Pore Pressure (kPa)", "pore_pressure_kpa", "Read"),
            ("Cell Volume Change (mm³)", "cell_volume_mm3", "Read"),
            ("Back Volume Change (mm³)", "back_volume_mm3", "Read"),
            ("Chamber Displacement (mm)", "position_mm", "Read"),
            ("Axial Force (kN)", "axial_force_kN", "Read"),

            # ---- Calculated (examples) ----
            ("Axial Stress (kPa)", "axial_stress_kpa", "Calculated"),
            ("Total Axial Stress σ1 (kPa)", "sigma1_kpa", "Calculated"),
            ("Radial Stress σ3 (kPa)", "sigma3_kpa", "Calculated"),
            ("Effective Axial Stress σ1' (kPa)", "eff_sigma1_kpa", "Calculated"),
            ("Effective Radial Stress σ3' (kPa)", "eff_sigma3_kpa", "Calculated"),
            ("Deviator Stress q (kPa)", "q_kpa", "Calculated"),
            ("Mean Effective Stress p' (kPa)", "pprime_kpa", "Calculated"),
            ("Axial Strain (%)", "axial_strain_pct", "Calculated"),
            ("Current Area (mm²)", "current_area_mm2", "Calculated"),
            ("Current Height (mm)", "current_height_mm", "Calculated"),
            ("Current Diameter (mm)", "current_diameter_mm", "Calculated"),
            ("Radial Strain (%)", "radial_strain_pct", "Calculated"),
        ]
        # add custom calcs to a "Custom" group
        items += [(c.name.replace("_", " ").title() + " (custom)", c.name, "Custom")
                  for c in self._calc_defs if c.enabled]

        desc = {k: l for (l, k, _g) in items}  # simple mapping for tooltips/editors
        return items, desc


    def update_plot(self, reading: dict):
        ctx = self._calc_context_from(reading)

        # --- Geometry from test details
        # --- Geometry (static, from test details)
        self._ensure_geometry_from_tm()
        geom = getattr(self, "_geometry", {})

        h0 = float(reading.setdefault("initial_height_mm", geom.get("h0_mm", 0.0)))
        d0 = float(reading.setdefault("initial_diameter_mm", geom.get("d0_mm", 0.0)))
        A0 = float(reading.setdefault("initial_area_mm2", geom.get("A0_mm2", 0.0)))
        V0 = float(reading.setdefault("initial_volume_mm3", geom.get("V0_mm3", 0.0)))
        # --- Pressures (direct readings)
        sigma3 = self._f(reading, "sigma3_kpa", aliases=("cell_pressure_kpa",), default=0.0)
        u      = self._f(reading, "pore_pressure_kpa", aliases=("back_pressure_kpa","u_kpa","u"), default=0.0)
        reading["sigma3_kpa"]        = sigma3
        reading["pore_pressure_kpa"] = u

        # --- Axial strain from displacement
        disp  = float(reading.get("axial_displacement_mm") or 0.0)
        disp0 = float(self._baselines.get("disp_start_mm", 0.0))
        eps = None
        if h0 > 0:
            eps = (disp - disp0) / h0
            reading["axial_strain_frac"] = eps
            reading["axial_strain_pct"]  = eps * 100.0
            reading["current_height_mm"] = h0 - (disp - disp0)

        # --- Current area (constant-volume assumption)
        if A0 > 0 and eps is not None:
            denom = 1.0 - eps
            reading["current_area_mm2"] = (A0 / denom) if abs(denom) > 1e-12 else float("nan")

        # --- Axial load
        F_kN = self._first_num(reading, ("axial_force_kN","force_kN","load_kN","axial_load_kN"))
        if F_kN is None:
            F_kN = 0.0
        F_N  = F_kN * 1000.0
        reading["axial_force_kN"] = F_kN
        reading["force_N"]        = F_N

        # --- Total axial stress (σ1)
        A = reading.get("current_area_mm2") or A0
        sigma1 = (sigma3 * A + F_N) / A if A and A > 0 else 0.0
        reading["sigma1_kpa"] = sigma1

        # --- Effective stresses
        eff_sigma3 = sigma3 - u
        eff_sigma1 = sigma1 - u
        reading["eff_sigma3_kpa"] = eff_sigma3
        reading["eff_sigma1_kpa"] = eff_sigma1

        # --- Derived stress quantities
        reading["q_kpa"]               = eff_sigma1 - eff_sigma3
        reading["pprime_kpa"]          = (eff_sigma1 + 2 * eff_sigma3) / 3.0
        reading["max_shear_stress_kpa"] = reading["q_kpa"] / 2.0

        # --- B value (stage-based)
        du    = u      - self._f(self._baselines, "u_start_kpa",    default=u)
        dcell = sigma3 - self._f(self._baselines, "cell_start_kpa", default=sigma3)
        reading["b_value"] = (du / dcell) if abs(dcell) > 1e-6 else float("nan")

        # --- Volume change (stage-based, back volume ref)
        back_v  = float(reading.get("back_volume_mm3") or 0.0)
        back_v0 = self._f(self._baselines, "back_volume_start_mm3", default=back_v)
        reading["volume_change_mm3"] = back_v - back_v0

        # --- Custom calculations (unchanged)
        for c in self._calc_defs:
            if not c.enabled:
                continue
            try:
                val = eval_expr(c.expr, ctx)
                print(f"[DEBUG] {c.key} = {val}  from expr={c.expr}")
                reading[c.key] = val
            except Exception as e:
                print(f"[DEBUG] {c.key} failed: {e}")
                reading[c.key] = float('nan')



        # --- Timekeeping (unchanged)
        ts = reading.get("timestamp")
        if ts is not None:
            t0 = getattr(self, "test_start_ts", None)
            s0 = getattr(self, "stage_start_ts", None)
            if t0 is not None: reading["test_elapsed_s"]  = max(0.0, float(ts) - float(t0))
            if s0 is not None:
                reading["stage_elapsed_s"] = max(0.0, float(ts) - float(s0))
                reading["sqrt_stage_time_s"] = math.sqrt(reading["stage_elapsed_s"])

        # --- Route to outputs
        self._update_live_readout(reading)
        self._route_to_graph_cards(reading)



    @staticmethod
    def _f(d: dict, key: str, default=0.0, aliases=()):
        candidates = (key,) + tuple(aliases or ())
        for k in candidates:
            if k in d:
                v = d.get(k)
                if v is None:
                    continue
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return float(default)

    # --- geometry helpers -------------------------------------------------
    def _ensure_geometry_from_tm(self):
        """Guarantee that h0, d0, A0, V0 are always present together."""
        h0 = getattr(self, "_h0_mm", None)
        d0 = getattr(self, "_d0_mm", None)
        if h0 and d0:
            A0 = math.pi * (d0**2) / 4.0
            V0 = A0 * h0
            self._geometry = {
                "h0_mm": h0,
                "d0_mm": d0,
                "A0_mm2": A0,
                "V0_mm3": V0,
            }

    def _first_num(self, d, keys):
        for k in keys:
            v = d.get(k)
            if v is None:
                continue
            try:
                f = float(v)
                if math.isfinite(f):
                    return f
            except Exception:
                pass
        return None


    def _calc_context_from(self, r: dict) -> dict:
        # always ensure geometry is computed
        self._ensure_geometry_from_tm()
        geom = getattr(self, "_geometry", {})

        ts     = self._f(r, "timestamp", aliases=("time", "t"))
        cell_p = self._f(r, "cell_pressure_kpa", aliases=("cell_kpa",))
        back_p = self._f(r, "back_pressure_kpa", aliases=("pore_pressure_kpa","u_kpa","u"))
        pore_p = self._f(r, "pore_pressure_kpa", default=back_p, aliases=("u_kpa","u"))
        disp   = self._f(r, "position_mm", aliases=("axial_position_mm","lf_position_mm"))
        vol    = self._f(r, "cell_volume_mm3", aliases=("volume_mm3","vol_cell_mm3"))

        # --- Geometry: prefer reading, else fall back to _geometry
        area0 = self._f(r, "initial_area_mm2", aliases=("A0_mm2",))
        if area0 == 0.0:
            area0 = geom.get("A0_mm2", 0.0)

        h0 = self._f(r, "initial_height_mm", aliases=("h0_mm",))
        if h0 == 0.0:
            h0 = geom.get("h0_mm", 0.0)

        v0 = self._f(r, "initial_volume_mm3", aliases=("v0_mm3",))
        if v0 == 0.0:
            v0 = geom.get("V0_mm3", 0.0)
        force = self._f(r, "force_N", aliases=("axial_force_N","load_N"))
        if force == 0.0:
            force = 1000.0 * self._f(r, "force_kN", aliases=("axial_force_kN",), default=0.0)

        eps   = self._f(r, "axial_strain_frac", aliases=("eps_axial","axial_strain"))
        if eps == 0.0:
            eps_pct = self._f(r, "axial_strain_pct", aliases=("strain_pct",), default=0.0)
            if eps_pct != 0.0:
                eps = eps_pct / 100.0

        ctx = {
            "timestamp": ts,
            "cell_pressure_kpa": cell_p,
            "back_pressure_kpa": back_p,
            "pore_pressure_kpa": pore_p,
            "disp_mm": disp,
            "vol_mm3": vol,
            "A0_mm2": area0,
            "h0_mm":  h0,
            "v0_mm3": v0,
            "force_N": force,
            "eps_axial": eps,
            "disp_start_mm": float(self._baselines.get("disp_start_mm", 0.0) or 0.0),
            "vol_start_mm3": float(self._baselines.get("vol_start_mm3", 0.0) or 0.0),
        }
        ctx["sigma3_kpa"] = ctx["cell_pressure_kpa"]

        print("[DEBUG] _calc_context_from ->", ctx)
        return ctx


    def _update_live_readout(self, r: dict):
        lines = []
        for key in self._live_calc_names:
            val = r.get(key, float('nan'))
            if isinstance(val, (int, float)):
                # look up the label from defs
                label = next((c.label for c in self._calc_defs if c.key == key), key)
                lines.append(f"{label}: {val:.3f}")
        txt = "\n".join(lines) if lines else "—"
        self._calc_panel.live_label.setText(txt)


    def _friendly_name(self, key: str) -> str:
        mapping = {
            "current_height_mm": "Current Height (mm)",
            "current_area_mm2":  "Current Area (mm²)",
            "sigma3_kpa":        "Radial Stress σ3 (kPa)",
            "sigma1_kpa":        "Axial Stress σ1 (kPa)",
            "eff_sigma3_kpa":    "Effective Radial Stress (kPa)",
            "eff_sigma1_kpa":    "Effective Axial Stress (kPa)",
            "q_kpa":             "Deviator Stress (kPa)",
            "pprime_kpa":        "Effective Mean Stress s (kPa)",
        }
        return mapping.get(key, key.replace("_", " ").title())


    def _open_graph_workspace(self):
        history = list(getattr(self, "_history", []) or
                       getattr(getattr(self, "main_window", None), "test_manager", None).data_log
                       if getattr(getattr(self, "main_window", None), "test_manager", None) else [])
        if not history:
            QMessageBox.information(self, "No Data", "There is no data available to plot.")
            return
        try:
            dlg = GraphWorkspaceDialog(history, parent=self)
            if hasattr(dlg, "set_variable_catalog"):
                items, desc = self._gdslab_catalog()
                dlg.set_variable_catalog(items, desc)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Graph Workspace Error", str(e))
    
    def export_data_flow(self):
        """
        1) Ask where to save CSV (user names the file & picks folder).
        2) Write self._history as CSV with a union of keys.
        3) Offer to open a post-test Graph Workspace so they can make/snapshot graphs.
        """
        if not getattr(self, "_history", None):
            QMessageBox.information(self, "No Data", "There is no data to export yet.")
            return

        # Suggest a helpful default file name
        suggested = f"triaxial_test_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

        tm = getattr(getattr(self, "main_window", None), "test_manager", None)
        sample_id = getattr(tm, "sample_id", "") or "triaxial_test"
        date_str  = getattr(tm, "test_date_str", "") or datetime.now().strftime("%Y-%m-%d")
        suggested = f"{sample_id}_{date_str}_{datetime.now().strftime('%H-%M-%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save test data as CSV", suggested, "CSV Files (*.csv)")
        if not path: return

        # ---- CSV writing with metadata at top ----
        rows = list(self._history)
        if not rows:
            QMessageBox.information(self, "No Data", "There is no data to export yet.")
            return

        # Metadata to write first (one per line)
        meta = {
            "sample_id": sample_id,
            "sample_height_cm": getattr(tm, "sample_height_cm", ""),
            "sample_diameter_cm": getattr(tm, "sample_diameter_cm", ""),
            "docked": "Yes" if getattr(tm, "is_docked", False) else "No",
            "sampling_period_s": getattr(tm, "sampling_period_s", ""),
            "start_datetime_local": datetime.fromtimestamp(getattr(tm, "test_start_ts", datetime.now().timestamp())).strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Build headers from union of keys, but drop metadata-like keys if present
        # --- Ask which extra calculated/custom columns to include
        wanted = self._ask_export_calcs()  # list of keys
        if wanted:
            for r in rows:
                r.update(self._compute_derived_for_export(r, wanted))

        # Build headers from union of keys (after adding any wanted calcs)
        all_keys = set()
        for d in rows:
            all_keys.update(d.keys())

        drop = {"sample_id","sample_height_cm","sample_diameter_cm","is_docked","sampling_period_s"}
        preferred = ["timestamp","date","test_elapsed_s","stage_elapsed_s","time_s",
                     "cell_pressure_kpa","back_pressure_kpa","cell_volume_mm3","back_volume_mm3",
                     "position_mm","stage_index","stage_name"]

        # Keep user-chosen calcs near the end, in the order they picked
        rest = [k for k in all_keys if k not in set(preferred) | drop]
        # ensure chosen keys appear (even if alphabetically they wouldn't)
        ordered_rest = [k for k in wanted if k in rest] + sorted([k for k in rest if k not in set(wanted)])

        headers = [k for k in preferred if k in all_keys] + ordered_rest


        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["# Metadata"])
                for k, v in meta.items():
                    w.writerow([k, v])
                w.writerow([])  # blank line before table

                dw = csv.DictWriter(f, fieldnames=headers)
                dw.writeheader()
                for r in rows:
                    dw.writerow({k: r.get(k) for k in headers})
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not write CSV:\n{e}")
            return

        QMessageBox.information(self, "Export Complete", f"Saved data to:\n{path}")

        choice = QMessageBox.question(
            self,
            "Make Graphs?",
            "Do you want to create and save graphs from the historical data now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if choice == QMessageBox.Yes:
            try:
                # Keep the Test Complete card visible; just open a modal workspace
                dlg = GraphWorkspaceDialog(list(self._history), parent=self)
                dlg.exec_()  # modal; returns when closed
            except Exception as e:
                QMessageBox.critical(self, "Graph Workspace Error", str(e))

    def _set_stage_controls_enabled(self, enabled: bool):
        try:
            self.btn_pause.setEnabled(enabled)
            self.btn_continue.setEnabled(False if enabled else False)  # only true after Pause
            self.btn_stop.setEnabled(enabled)
            # (optional) also guard graph controls
            self.save_btn.setEnabled(enabled)
            self.add_graph_btn.setEnabled(enabled)
            self.del_graph_btn.setEnabled(enabled)
            self.reset_btn.setEnabled(enabled)
        except Exception:
            pass

    def reset_for_new_test(self, keep_last_config: bool = False):
        self.is_complete = False
        self._clear_graphs_and_timers()
        try: self._stack.setCurrentWidget(self._normal_container)
        except Exception: pass
        self._set_stage_controls_enabled(True)
        self.set_paused_state(False)
        try: self._render_timer.start()
        except Exception: pass

        
    def _freeze_live_updates(self):
        try: self._render_timer.stop()
        except Exception: pass
        self._set_stage_controls_enabled(False)

    def _clear_graphs_and_timers(self):
        try: self.reset_layout()
        except Exception: pass
        self.current_stage_index = 0
        self.current_right.setText("Current Stage: —")
        self.start_time = None
        self._history.clear()

    def on_test_started(self):
        # called by MainWindow when a new test begins
        self.is_complete = False
        try: self._stack.setCurrentWidget(self._normal_container)
        except Exception: pass
        self._set_stage_controls_enabled(True)
        self.set_paused_state(False)
        # guarantee a reference start time (will be refined by first reading)
        self.test_start_ts = time.time()
        try: self._render_timer.start()
        except Exception: pass


    def on_test_stopped(self):
        # optional: if you ever need to force-disable (e.g., on error)
        self._set_stage_controls_enabled(False)


    # ---------------- Public API ----------------
    def load_stages(self, stages):
        self._stages = list(stages or [])
        self.stage_list.clear()
        for i, s in enumerate(self._stages, start=1):
            name = getattr(s, "name", f"Stage {i}")
            self.stage_list.addItem(QListWidgetItem(name))
        if self._stages:
            self.stage_list.setCurrentRow(0)
            self.set_current_stage_index(0)

    def _render(self):
        if not self._dirty:
            return
        for g in self._graph_cards:
            if hasattr(g, "update_data"):
                g.update_data(self.shared_data)
        self._dirty = False
        
    def set_paused_state(self, paused: bool):
        self.btn_pause.setEnabled(not paused)
        self.btn_continue.setEnabled(paused)

    def set_current_stage(self, stage):
        """
        Accepts an int index or a string like 'Stage 2' (or a stage name).
        Syncs the left list selection and clears only per-stage graphs so
        they start plotting immediately in the new stage.
        """
        idx = None
        if isinstance(stage, int):
            idx = stage
        elif isinstance(stage, str):
            # Try 'Stage N' first
            m = re.search(r'(\d+)', stage)
            if m:
                idx = int(m.group(1)) - 1
            else:
                # Fallback: exact text match in the list
                for i in range(self.stage_list.count()):
                    if self.stage_list.item(i).text().strip() == stage.strip():
                        idx = i
                        break

        if idx is None:
            return

        self.current_stage_index = idx
        self.current_right.setText(f"Current Stage: Stage {idx + 1}")

        # Sync the left list selection quietly (avoid feedback loops)
        self.stage_list.blockSignals(True)
        try:
            self.stage_list.setCurrentRow(idx)
        finally:
            self.stage_list.blockSignals(False)

        # Clear ONLY per-stage graphs (x = stage_elapsed_s or time_s)
        for card in getattr(self, "_graph_cards", []):
            xk = getattr(card, "get_x_key", lambda: None)()
            if xk in ("stage_elapsed_s", "time_s"):
                try:
                    card.clear_data()
                except Exception:
                    pass

    def set_current_stage_index(self, idx: int):
        if 0 <= idx < self.stage_list.count():
            self.stage_list.setCurrentRow(idx)
            self.set_current_stage(self.stage_list.item(idx).text())
            
    def _save_all_graphs_flow(self) -> bool:
        # Prefer the page-level exporter (lets the user choose a folder)
        if hasattr(self, "export_graphs") and callable(self.export_graphs):
            self.export_graphs()
            return True

        # Fallback: pick a folder once and save each card
        folder = QFileDialog.getExistingDirectory(self, "Choose folder to save graphs")
        if not folder:
            return False

        saved_any = False
        for i, card in enumerate(getattr(self, "_graph_cards", []), start=1):
            try:
                # If the card has its own saver, use it…
                if hasattr(card, "save_png") and callable(card.save_png):
                    card.save_png(os.path.join(folder, f"stage_graph_{i:02d}.png"))
                    saved_any = True
                # …otherwise export via pyqtgraph directly
                elif hasattr(card, "plot") and card.plot is not None:
                    ImageExporter(card.plot.plotItem).export(
                        os.path.join(folder, f"stage_graph_{i:02d}.png")
                    )
                    saved_any = True
            except Exception:
                pass

        if saved_any:
            return True

        # Nothing to save with — ask whether to proceed without saving
        choice = QMessageBox.question(
            self,
            "No Save Method Found",
            "No save routine was found for the current graphs.\n"
            "Continue without saving?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return choice == QMessageBox.Yes

    # --- add anywhere inside TestViewPage ---------------------------------
    def _has_next_stage(self) -> bool:
        tm = getattr(self.main_window, "test_manager", None)
        if not tm:
            return False
        # Prefer manager API if available; fall back to indices
        if hasattr(tm, "has_next_stage"):
            try:
                return bool(tm.has_next_stage())
            except Exception:
                pass
        try:
            idx = int(getattr(tm, "current_stage_index", 0))
            n = len(getattr(tm, "stages", []))
            return idx < n - 1
        except Exception:
            return False


    # --- replace your current handle_stage_complete with this --------------
    def handle_stage_complete(self):
        print("[DEBUG] handle_stage_complete called")

        mgr = getattr(self.main_window, "test_manager", None)
        if mgr is None:
            print("[DEBUG] No test_manager on main_window")
            returnS

        # Always show the "What to do next?" dialog
        self.prompt_next_action()

            
    def prompt_save_graphs(self) -> str:
        """Show the save/skip graphs dialog. Returns 'save' or 'skip'."""
        # If there are no graphs to save, just skip
        if not getattr(self, "_graph_cards", None):
            return "skip"

        msg = QMessageBox(self)
        msg.setWindowTitle("Save Graphs")
        msg.setText("Do you want to save the current stage’s graphs before continuing?")
        btn_save = msg.addButton("Save Now", QMessageBox.AcceptRole)
        btn_skip = msg.addButton("Skip", QMessageBox.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec_()

        if msg.clickedButton() is btn_save:
            try:
                # Prefer page-level export flow if available
                if hasattr(self, "_save_all_graphs_flow"):
                    self._save_all_graphs_flow()
                else:
                    self.export_graphs()
            except Exception:
                pass
            return "save"
        else:
            return "skip"

    def prompt_next_action(self):
        """After a Stop: Edit Stages / Next Stage / End Test (Next disabled if last)."""
        has_next = self._has_next_stage()

        dlg = QMessageBox(self)
        dlg.setWindowTitle("What do you want to do next?")
        dlg.setText("Choose what to do next:")
        btn_edit = dlg.addButton("Edit Stages", QMessageBox.ActionRole)
        btn_next = dlg.addButton("Go to Next Stage", QMessageBox.AcceptRole)
        btn_end  = dlg.addButton("End Test", QMessageBox.DestructiveRole)
        btn_next.setEnabled(has_next)

        dlg.exec_()
        clicked = dlg.clickedButton()

        if clicked is btn_end:
            tm = getattr(self.main_window, "test_manager", None)
            if tm is not None:
                tm.stop_requested = False  # make sure no trailing completion shows dialogs
            self._block_completion_until = time.monotonic() + 2.0
            self.end_test_requested.emit()
            print("End test requested")

            self._stack.setCurrentWidget(self._complete_card)
            return

        if clicked is btn_next:
            self.next_stage_requested.emit()
            return

        if clicked is btn_edit:
            if hasattr(self.main_window, "on_edit_stage_requested"):
                self.main_window.on_edit_stage_requested()
                # refresh list & keep selection in range
                try:
                    stages = getattr(self.main_window.test_manager, "stages", [])
                    self.load_stages(stages)
                    if stages:
                        self.set_current_stage_index(min(self.current_stage_index, len(stages) - 1))
                except Exception:
                    pass
            # Let user decide again after editing


    def export_graphs(self):
        if not self._graph_cards:
            QMessageBox.information(self, "No graphs", "There are no graphs to save.")
            return

        # Single-graph: let the user choose the exact filename
        if len(self._graph_cards) == 1:
            card = self._graph_cards[0]
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Graph As",
                os.path.join(os.path.expanduser("~"), "graph.png"),
                "PNG Images (*.png)"
            )
            if not path:
                return
            try:
                if hasattr(card, "plot") and card.plot is not None:
                    exporter = ImageExporter(card.plot.plotItem)
                    exporter.export(path)
                QMessageBox.information(self, "Export Complete", f"Saved graph to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not save graph:\n{e}")
            return

        # Multi-graph: pick a folder then ask for a base name
        dir_path = QFileDialog.getExistingDirectory(self, "Select Folder to Save Graphs")
        if not dir_path:
            return

        base, ok = QInputDialog.getText(
            self, "Name Your Plots", "Base file name (no extension):", text="graph"
        )
        if not ok:
            return
        base = base.strip() or "graph"

        saved_count = 0
        for i, card in enumerate(self._graph_cards, start=1):
            try:
                if hasattr(card, "plot") and card.plot is not None:
                    file_path = os.path.join(dir_path, f"{base}_{i}.png")
                    exporter = ImageExporter(card.plot.plotItem)
                    exporter.export(file_path)
                    saved_count += 1
            except Exception as e:
                print(f"[✗] Failed to save graph {i}: {e}")

        QMessageBox.information(
            self,
            "Export Complete",
            f"Saved {saved_count} graph(s) to:\n{dir_path}"
        )


    def _trim_series(self, xs, ys):
        # keep only the last MAX_POINTS
        n = len(xs)
        if n <= self.MAX_POINTS:
            return xs, ys
        return xs[-self.MAX_POINTS:], ys[-self.MAX_POINTS:]

    def _maybe_stride(self, xs, ys):
        n = len(xs)
        if n <= self.DOWNSAMPLE_OVER:
            return xs, ys
        step = max(2, n // self.DOWNSAMPLE_OVER)
        return xs[::step], ys[::step]

    def prompt_export_graphs(self):
        reply = QMessageBox.question(
            self,
            "Export Graphs?",
            "Do you want to export graphs for this stage before they are cleared?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            folder = QFileDialog.getExistingDirectory(
                self, "Select Folder to Save Graphs"
            )
            if folder:
                for i, card in enumerate(self._graph_cards):
                    file_path = os.path.join(folder, f"stage_graph_{i+1}.png")
                    card.plot.scene().renderToFile(file_path)  # pyqtgraph save

    # ---------------- Graphs ----------------
    def add_graph(self):
        card = _GraphCard(title=f"Graph {len(self._graph_cards)+1}")
        card.remove_requested.connect(self._remove_graph)
        self._graph_cards.append(card)

        # put it on screen
        if self.mode_combo.currentText() == "Tab View":
            self.tabs.addTab(card, card.get_title())
        else:
            self._reflow_grid()

        # >>> use the grouped catalog (friendly names)
        items, _ = self._gdslab_catalog()
        if hasattr(card, "set_available_series_grouped"):
            card.set_available_series_grouped(items)
        else:
            # fallback if ever needed
            calc_names = [c.name for c in getattr(self, "_calc_defs", []) if c.enabled]
            keys = getattr(self, "_builtin_keys", []) + calc_names
            card.set_available_series(keys)

        # backfill history
        if self._history:
            for d in self._history:
                card.update_data(d)
        return card




    def _remove_graph(self, card):
        if card in self._graph_cards:
            self._graph_cards.remove(card)
        # remove from grid if present
        self._remove_from_layout(self.grid, card)
        # remove from tabs if present
        idx = self.tabs.indexOf(card)
        if idx != -1:
            self.tabs.removeTab(idx)
        card.setParent(None); card.deleteLater()
        self._reflow_grid()

    def delete_last_graph(self):
        if not self._graph_cards:
            return
        self._remove_graph(self._graph_cards[-1])

    def reset_layout(self):
        while self._graph_cards:
            self._remove_graph(self._graph_cards[-1])
        
    def reset_for_new_stage(self):
        # Clear only graphs that track from stage start; keep test-start history
        self._graph_cancelled_resume = False
        per_stage_keys = {"stage_elapsed_s", "time_s", "time_since_stage_start_s"}
        for card in self._graph_cards:
            xk = getattr(card, "get_x_key", lambda: None)()
            if xk in per_stage_keys:
                card.clear_data()

    # ---------------- View mode switching ----------------
    def _on_mode_changed(self, mode: str):
        if mode == "Tab View":
            # move all to tabs
            self.grid_scroll.hide()
            self.tabs.show()
            for card in self._graph_cards:
                self._remove_from_layout(self.grid, card)
                if self.tabs.indexOf(card) == -1:
                    self.tabs.addTab(card, card.get_title())
        else:
            # move all to grid
            self.tabs.hide()
            self.grid_scroll.show()
            while self.tabs.count():
                w = self.tabs.widget(0)
                self.tabs.removeTab(0)
                self.grid.addWidget(w)  # temp, proper positions set below
            self._reflow_grid()

    def _close_tab_requested(self, index: int):
        w = self.tabs.widget(index)
        if w:
            self._remove_graph(w)

    def clear_stage_start_graphs(self):
        for card in self._graph_cards:
            if getattr(card, "_x_key", "") == "time_since_stage_start_s":
                card.clear_data()

    def clear_stage_graphs(self):
        """Clear only graphs that are tracking from stage start."""
        for card in self._graph_cards:
            if getattr(card, "x_axis_mode", "stage_start") == "stage_start":
                card.clear_data()

    # ---------------- Internals ----------------
    def _reflow_grid(self):
        # clear grid, add back in 2 columns
        for i in reversed(range(self.grid.count())):
            self.grid.itemAt(i).widget().setParent(None)  # detach; will be re-added
        for idx, w in enumerate(self._graph_cards):
            if self.tabs.indexOf(w) != -1:
                continue  # currently in tabs
            r, c = divmod(idx, 2)
            self.grid.addWidget(w, r, c)

    @staticmethod
    def _remove_from_layout(layout, widget):
        # remove widget from a QGridLayout if it’s there
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item.widget() is widget:
                layout.removeWidget(widget)
                return


# --- Graph card ---------------------------------------------------------------
class _GraphCard(QGroupBox):
    remove_requested = pyqtSignal(object)   # emits self

    def __init__(self, title="Graph", x_axis_mode="stage_start"):
        super().__init__(title)
        self.setObjectName("Card")
        self.x_axis_mode = x_axis_mode
        self._keys_set = False

        # X + multi-Y state
        self._x_key = "timestamp"
        self._series = []            # list of {"combo": QComboBox, "key": str, "curve": PlotDataItem}
        self._data_x = deque(maxlen=1000)
        self._data_y = {}            # key -> deque
        self._last_grouped_items = None  # cached grouped items for filling combos
        self._history = deque(maxlen=1000)

        col = QVBoxLayout(self)
        col.setContentsMargins(12, 10, 12, 12)

        # top row: remove button
        top = QHBoxLayout()
        top.addStretch(1)
        rm = QPushButton("✕")
        rm.setObjectName("CloseButton")
        rm.setFixedSize(24, 24)
        rm.setToolTip("Remove graph")
        rm.clicked.connect(lambda: self.remove_requested.emit(self))
        top.addWidget(rm)
        col.addLayout(top)

        # controls row
        controls = QHBoxLayout()
        controls.addWidget(QLabel("X:"))

        self.x_combo = QComboBox()
        self.x_combo.setEditable(False)
        self.x_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.x_combo.setMinimumWidth(140)
        self.x_combo.currentTextChanged.connect(self._on_x_changed)
        controls.addWidget(self.x_combo, 1)

        controls.addSpacing(12)
        controls.addWidget(QLabel("Y:"))

        # container that will hold multiple (combo + close) pairs
        # inside _GraphCard.__init__()  (controls row)
        self.y_bar = QHBoxLayout()
        self.y_bar.setSpacing(6)

        self.btn_add_y = QPushButton("+")
        self.btn_add_y.setFixedWidth(36)
        self.btn_add_y.setToolTip("Add another Y series")
        self.btn_add_y.clicked.connect(lambda: self._add_y_series())
        self.y_bar.addWidget(self.btn_add_y)  # put button at the start (always visible)

        controls.addLayout(self.y_bar, 3)


        controls.addStretch(1)
        col.addLayout(controls)

        # plot
        if pg is not None:
            self.plot = pg.PlotWidget()
            self.plot.setBackground("w")
            self.plot.showGrid(x=True, y=True, alpha=0.3)
            # legend for multi series
            try:
                self.legend = self.plot.addLegend(offset=(10, 10))
            except Exception:
                self.legend = None
            col.addWidget(self.plot, 1)
        else:
            self.plot = None
            self.body = QLabel("PyQtGraph not installed. Showing keys only.\n"
                               "Install 'pyqtgraph' for real-time charts.")
            self.body.setAlignment(Qt.AlignCenter)
            self.body.setStyleSheet("color:#666;")
            col.addWidget(self.body, 1)

        # start with one Y
        self._add_y_series(preferred_key="cell_pressure_kpa")

    # ---------- UI builders -------------------------------------------------
    def _add_y_series(self, preferred_key=None):
        """Add (combo + ×) for one Y series and create a curve."""
        row = QHBoxLayout()
        row.setSpacing(4)

        cb = QComboBox()
        cb.setEditable(False)
        cb.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        cb.setMinimumWidth(180)
        # fill later when we receive keys/items
        cb.currentIndexChanged.connect(lambda _=None, c=cb: self._on_y_changed(c))

        btn_x = QPushButton("×")
        btn_x.setObjectName("CloseButton")
        btn_x.setFixedSize(22, 22)
        btn_x.setToolTip("Remove this series")
        btn_x.clicked.connect(lambda: self._remove_y_series(cb, row))

        row.addWidget(cb)
        row.addWidget(btn_x)
        self.y_bar.addLayout(row)

        # add to state
        entry = {"combo": cb, "key": None, "curve": None}
        self._series.append(entry)

        # if we already have options, populate now
        if self._last_grouped_items:
            self._fill_combo_grouped(cb, self._last_grouped_items)
            self._select_first_valid(cb, preferred_keys=(preferred_key,) if preferred_key else ())
            self._ensure_curve_for_combo(cb)

    def _remove_y_series(self, combo, row_layout):
        """Remove one Y series and its curve."""
        # remove curve
        key = combo.property("y_key")
        if key and key in self._data_y:
            try:
                del self._data_y[key]
            except Exception:
                pass
        for i, s in enumerate(self._series):
            if s["combo"] is combo:
                if s["curve"] is not None and self.plot:
                    try:
                        self.plot.removeItem(s["curve"])
                    except Exception:
                        pass
                del self._series[i]
                break

        # physically remove widgets
        while row_layout.count():
            w = row_layout.itemAt(0).widget()
            row_layout.removeItem(row_layout.itemAt(0))
            if w:
                w.setParent(None)
                w.deleteLater()

        # redraw remaining from history
        self._rebuild_from_history()

    def _fill_combo_grouped(self, combo, items):
        """Fill a single combo with grouped (label, key, group) rows."""
        combo.blockSignals(True)
        combo.clear()
        model = combo.model()  # QStandardItemModel
        last_group = None
        for label, key, group in items:
            if group != last_group:
                hdr = QStandardItem(group)
                f = hdr.font(); f.setBold(True); hdr.setFont(f)
                hdr.setFlags(Qt.NoItemFlags)  # header (disabled)
                model.appendRow(hdr)
                last_group = group
            combo.addItem(label, userData=key)
        combo.blockSignals(False)

    def _select_first_valid(self, combo: QComboBox, preferred_keys=()):
        """Pick a non-header row, preferring specific keys if present."""
        # try preferred keys
        for key in preferred_keys or ():
            idx = combo.findData(key)
            if idx != -1:
                combo.setCurrentIndex(idx)
                return
        # else first real row
        for i in range(combo.count()):
            if combo.itemData(i) is not None:
                combo.setCurrentIndex(i)
                return

    def _ensure_curve_for_combo(self, combo):
        """Create/replace the curve bound to this combo's selected key."""
        key = combo.currentData() or combo.currentText()
        old_key = combo.property("y_key")
        if key == old_key:
            return

        # remove old curve
        for s in self._series:
            if s["combo"] is combo and s["key"] == old_key and s["curve"] is not None and self.plot:
                try:
                    self.plot.removeItem(s["curve"])
                except Exception:
                    pass
                s["curve"] = None

        # make new curve
        if self.plot:
            color = pg.intColor(len([x for x in self._series if x["curve"] is not None]), hues=12)
            label = combo.currentText() or key
            curve = self.plot.plot([], [], pen=pg.mkPen(color, width=2), name=label)
        else:
            curve = None

        # store
        for s in self._series:
            if s["combo"] is combo:
                s["key"] = key
                s["curve"] = curve
                break

        combo.setProperty("y_key", key)
        # prepare deque for this key
        if key not in self._data_y:
            self._data_y[key] = deque(maxlen=1000)

    # ---------- external API from page -------------------------------------
    def set_available_series(self, keys: list[str]):
        """Flat list version (fallback). Populates X and all Y combos."""
        # X
        cur_x = self.x_combo.currentText()
        self.x_combo.blockSignals(True)
        self.x_combo.clear()
        self.x_combo.addItems(keys)
        if cur_x in keys:
            self.x_combo.setCurrentText(cur_x)
        elif "timestamp" in keys:
            self.x_combo.setCurrentText("timestamp")
        self.x_combo.blockSignals(False)
        self._x_key = self.x_combo.currentText() or self._x_key

        # Ys
        for s in self._series:
            cb = s["combo"]
            cur = cb.currentData() or cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            for k in keys:
                cb.addItem(k, userData=k)
            if cur in keys:
                cb.setCurrentText(cur)
            cb.blockSignals(False)
            self._ensure_curve_for_combo(cb)

    def set_available_series_grouped(self, items):
        """
        items: list of (label, key, group)
        Insert bold, disabled rows when group changes.
        """
        self._last_grouped_items = list(items)

        # X combo: grouped fill
        # (We simply show the user-facing labels but still use key as userData.)
        self.x_combo.blockSignals(True)
        self.x_combo.clear()
        model = self.x_combo.model()
        last_group = None
        for label, key, group in items:
            if group != last_group:
                hdr = QStandardItem(group)
                f = hdr.font(); f.setBold(True); hdr.setFont(f)
                hdr.setFlags(Qt.NoItemFlags)
                model.appendRow(hdr)
                last_group = group
            self.x_combo.addItem(label, userData=key)
        self.x_combo.blockSignals(False)
        # choose a sensible default for X
        self._select_first_valid(self.x_combo, preferred_keys=("timestamp", "test_elapsed_s", "stage_elapsed_s"))
        self._x_key = self.x_combo.currentData() or self._x_key
        if self.plot:
            self.plot.setLabel('bottom', self.x_combo.currentText())

        # Fill all Y combos the same way
        if not self._series:
            self._add_y_series()
        for s in self._series:
            self._fill_combo_grouped(s["combo"], items)
            # try to preserve selection; else pick a good default
            if s["combo"].findData(s.get("key")) == -1:
                self._select_first_valid(s["combo"], preferred_keys=("cell_pressure_kpa",))
            self._ensure_curve_for_combo(s["combo"])

    def get_x_key(self):
        return self._x_key

    def clear_data(self):
        """Clear only the data; keep axes, selectors, and curves."""
        try:
            self._data_x.clear()
            for dq in self._data_y.values():
                dq.clear()
        except Exception:
            pass
        if self.plot:
            for s in self._series:
                if s["curve"] is not None:
                    try:
                        s["curve"].setData([], [])
                    except Exception:
                        pass

    # ---------- internal helpers ------------------------------------------
    def _on_x_changed(self, _):
        self._x_key = self.x_combo.currentData() or self.x_combo.currentText() or self._x_key
        if self.plot:
            self.plot.setLabel('bottom', self.x_combo.currentText() or str(self._x_key))
        self._rebuild_from_history()

    def _on_y_changed(self, combo):
        self._ensure_curve_for_combo(combo)
        self._rebuild_from_history()

    def _populate_keys_once(self, keys):
        if self._keys_set:
            return
        if self._last_grouped_items:
            self.set_available_series_grouped(self._last_grouped_items)
        else:
            self.set_available_series(keys)
        self._keys_set = True


    def _rebuild_from_history(self):
        # clear deques
        self._data_x.clear()
        for k in list(self._data_y.keys()):
            self._data_y[k].clear()

        def _get_num(d, key):
            try:
                v = float(d.get(key))
                return v if math.isfinite(v) else None
            except Exception:
                return None

        # refill from history
        for d in self._history:
            x = _get_num(d, self._x_key)
            if x is None:
                continue
            self._data_x.append(x)
            for s in self._series:
                key = s["key"]
                if not key:
                    continue
                y = _get_num(d, key)
                if y is not None:
                    self._data_y.setdefault(key, deque(maxlen=1000)).append(y)

        if self.plot:
            for s in self._series:
                key = s["key"]
                curve = s["curve"]
                if curve is None or not key:
                    continue
                xs = list(self._data_x)
                ys = list(self._data_y.get(key, []))
                # stride/trim similar to your single-series code
                MAX_POINTS = 2000
                if len(xs) > MAX_POINTS:
                    xs = xs[-MAX_POINTS:]; ys = ys[-MAX_POINTS:]
                DOWNSAMPLE_OVER = 1500
                if len(xs) > DOWNSAMPLE_OVER:
                    step = max(2, len(xs)//DOWNSAMPLE_OVER)
                    xs = xs[::step]; ys = ys[::step]
                curve.setData(xs, ys)

    # ---------- live update -----------------------------------------------
    def update_data(self, data: dict):
        # first reading: use keys present to seed combos
        if isinstance(data, dict) and data and not self._keys_set:
            self._populate_keys_once(list(data.keys()))

        # keep snapshot to rebuild if axes change
        try:
            self._history.append({k: data.get(k) for k in data.keys()})
        except Exception:
            return

        # extract X
        try:
            x = float(data.get(self._x_key, float("nan")))
            if x != x:  # NaN
                alias = {"stage_elapsed_s": "time_s", "test_elapsed_s": "time_s"}.get(self._x_key)
                if alias in data:
                    x = float(data.get(alias))
        except Exception:
            return
        if not math.isfinite(x):
            return
        self._data_x.append(x)

        if self.plot is None:
            keys = ", ".join(list(data.keys())[:6])
            self.body.setText(f"Live keys: {keys if keys else '—'}")
            return

        # update each Y series
        for s in self._series:
            key = s["key"]
            curve = s["curve"]
            if not key or curve is None:
                continue
            try:
                y = float(data.get(key, float("nan")))
            except Exception:
                continue
            if not math.isfinite(y):
                continue
            self._data_y.setdefault(key, deque(maxlen=1000)).append(y)

            # build strided data for this series
            xs = list(self._data_x)
            ys = list(self._data_y[key])
            MAX_POINTS = 2000
            if len(xs) > MAX_POINTS:
                xs = xs[-MAX_POINTS:]; ys = ys[-MAX_POINTS:]
            DOWNSAMPLE_OVER = 1500
            if len(xs) > DOWNSAMPLE_OVER:
                step = max(2, len(xs)//DOWNSAMPLE_OVER)
                xs = xs[::step]; ys = ys[::step]
            curve.setData(xs, ys)
