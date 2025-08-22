from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit,
    QPushButton, QCheckBox, QListWidget, QListWidgetItem,
    QStackedWidget, QSplitter, QSizePolicy, QStyledItemDelegate, QGroupBox, QFormLayout,
    QAbstractItemView, QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
import re
from PyQt5.QtGui import QFont
from typing import Dict, Any, Optional, List, Iterable
import uuid
import math

class StageData:
    def __init__(self, name="New Stage", stage_type="Saturation",
                 cell_pressure=0, back_pressure=0, duration=0,
                 axial_velocity=0, load_threshold=0, safety_load_kN=9999,
                 dock=False, hold=False):
        self.name = name
        self.stage_type = stage_type
        self.cell_pressure = cell_pressure
        self.back_pressure = back_pressure
        self.duration = duration
        self.axial_velocity = axial_velocity
        self.load_threshold = load_threshold
        self.safety_load_kN = safety_load_kN
        self.dock = dock
        self.hold = hold
        self.readings = []

        # NEW: stable identifier to track this stage even if reordered/edited
        self.stage_id = str(uuid.uuid4())

    def add_reading(self, reading: dict):
        """Store a single live reading for this stage."""
        self.readings.append(reading)

    def to_dict(self) -> Dict:
        """Convenience for UI/debugging/serialization."""
        return {
            "stage_id": self.stage_id,
            "name": self.name,
            "stage_type": self.stage_type,
            "cell_pressure": self.cell_pressure,
            "back_pressure": self.back_pressure,
            "duration": self.duration,
            "axial_velocity": self.axial_velocity,
            "load_threshold": self.load_threshold,
            "safety_load_kN": self.safety_load_kN,
            "dock": self.dock,
            "hold": self.hold,
        }

    def update_fields(self, updates: Dict, allowed: Iterable[str] = ()):
        """
        Safe update: only apply keys that exist (and optionally only those in 'allowed').
        Returns the dict of actually-applied changes.
        """
        applied = {}
        for k, v in updates.items():
            if allowed and k not in allowed:
                continue
            if hasattr(self, k):
                setattr(self, k, v)
                applied[k] = v
        return applied


class TestStageEditor(QWidget):
    layout_changed = pyqtSignal()
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)  # add this
        self.data = data

        self.cell_input = self.back_input = self.duration_input = None
        self.axial_input = self.load_input = self.safety_input = None
        self.hold_checkbox = None

        # Outer column to force TOP alignment
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.form_box = QGroupBox("Stage Details")
        self.form_box.setObjectName("StageForm")
        self.form = QFormLayout(self.form_box)
        self.form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self.form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.form.setFormAlignment(Qt.AlignTop)               # top-aligned
        self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.form.setHorizontalSpacing(12)                    # tighter
        self.form.setVerticalSpacing(6)                       # tighter
        self.form.setContentsMargins(12, 10, 12, 10)

        outer.addWidget(self.form_box)
        outer.addStretch(1)                                   # keep content at top

        # after creating self.form_box in TestStageEditor.__init__
        self.form_box.setStyleSheet("""
            /* Only inside StageForm */
            QGroupBox#StageForm QLabel { font-size: 15px; }
            QGroupBox#StageForm QLineEdit, 
            QGroupBox#StageForm QComboBox {
                min-height: 30px;    /* smaller than global */
                padding: 4px 8px;
            }
            QGroupBox#StageForm QCheckBox { padding: 2px 0; }
        """)


        # Stage type
        self.combo = QComboBox()
        self.combo.addItems(["Saturation","Consolidation","Shear","B Check","Automated Docking"])
        self.combo.setCurrentText(self.data.stage_type)
        self.combo.currentTextChanged.connect(self._on_stage_type_changed)

        self.form.addRow("Stage Type", self.combo)

        # container for dynamic rows
        self.dynamic_host = QWidget()
        self.dynamic_layout = QFormLayout(self.dynamic_host)
        self.dynamic_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.dynamic_layout.setHorizontalSpacing(12)
        self.dynamic_layout.setVerticalSpacing(6)
        self.form.addRow(self.dynamic_host)

        self.update_ui_for_stage_type()

    def _clear_dynamic(self):
        # remove old widgets
        while self.dynamic_layout.count():
            item = self.dynamic_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # IMPORTANT: drop stale references so save_inputs doesn't touch deleted widgets
        for name in (
            "cell_input", "back_input", "duration_input",
            "axial_input", "load_input", "safety_input",
            "hold_checkbox"
        ):
            setattr(self, name, None)

    def _on_stage_type_changed(self, new_type):
        self.data.stage_type = new_type
        self.update_ui_for_stage_type()

    def save_inputs(self):
        # read only if the widget still exists
        def _to_float(le, fallback=0.0):
            if le is None:
                return fallback
            try:
                return float(le.text())
            except Exception:
                return fallback

        if self.cell_input is not None:
            self.data.cell_pressure = _to_float(self.cell_input)

        if self.back_input is not None:
            self.data.back_pressure = _to_float(self.back_input)

        if self.duration_input is not None:
            self.data.duration = _to_float(self.duration_input)

        if self.axial_input is not None:
            self.data.axial_velocity = _to_float(self.axial_input)

        if self.load_input is not None:
            self.data.load_threshold = _to_float(self.load_input)

        if self.safety_input is not None:
            self.data.safety_load_kN = _to_float(self.safety_input, 9999.0)

        if self.hold_checkbox is not None:
            self.data.hold = self.hold_checkbox.isChecked()

    def update_ui_for_stage_type(self):
        self._clear_dynamic()
        if self.data.stage_type == "Saturation":
            self._add_cell_pressure()
            self._add_back_pressure()
            self._add_duration()
        elif self.data.stage_type == "Consolidation":
            self._add_cell_pressure()
            self._add_back_pressure()
        elif self.data.stage_type == "B Check":
            self._add_cell_pressure()
        elif self.data.stage_type == "Shear":
            self._add_axial_velocity()
            self._add_safety_threshold()
        elif self.data.stage_type == "Automated Docking":
            self._add_axial_velocity()
            self._add_load_threshold()
        self._add_hold_checkbox()
        self.layout_changed.emit()

    def _add_cell_pressure(self):
        self.cell_input = QLineEdit(str(self.data.cell_pressure))
        self.dynamic_layout.addRow("Cell Pressure (kPa)", self.cell_input)

    def _add_back_pressure(self):
        self.back_input = QLineEdit(str(self.data.back_pressure))
        self.dynamic_layout.addRow("Back Pressure (kPa)", self.back_input)

    def _add_duration(self):
        self.duration_input = QLineEdit(str(self.data.duration))
        self.dynamic_layout.addRow("Duration (min)", self.duration_input)

    def _add_axial_velocity(self):
        self.axial_input = QLineEdit(str(getattr(self.data, "axial_velocity", 0)))
        self.dynamic_layout.addRow("Axial Velocity (mm/min)", self.axial_input)

    def _add_load_threshold(self):
        self.load_input = QLineEdit(str(getattr(self.data, "load_threshold", 0)).replace(",", "."))
        self.dynamic_layout.addRow("Load Threshold (kN)", self.load_input)

    def _add_safety_threshold(self):
        self.safety_input = QLineEdit(str(getattr(self.data, "safety_load_kN", 9999)).replace(",", "."))
        self.dynamic_layout.addRow("Safety Load Threshold (kN)", self.safety_input)

    def _add_hold_checkbox(self):
        self.hold_checkbox = QCheckBox("Hold pressure after stage")
        # span label column with an empty label to keep alignment
        self.dynamic_layout.addRow(QLabel(""), self.hold_checkbox)

class LockRightSplitter(QSplitter):
    """Horizontal splitter that keeps the RIGHT pane at a fixed width."""
    def __init__(self, lock_width=520, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._lock_width = int(lock_width)
        self.setChildrenCollapsible(False)

    def set_lock_width(self, w:int):
        self._lock_width = int(w)
        self._apply()

    def _apply(self):
        if self.count() != 2:
            return
        total = self.size().width()
        if total <= 0:
            return
        handle = self.handleWidth()
        right = min(self._lock_width, max(0, total - handle))  # clamp to available
        left  = max(0, total - right - handle)
        self.setSizes([left, right])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def apply_locked_sizes_later(self):
        QTimer.singleShot(0, self._apply)

class LockRightCapLeftSplitter(QSplitter):
    """
    Keeps the RIGHT pane at a fixed width and caps LEFT to a max.
    If there's extra width, it goes to a 3rd 'spacer' widget.
    Order must be: [left, right, spacer].
    """
    def __init__(self, lock_right=520, left_max=720, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._lock_right = int(lock_right)
        self._left_max   = int(left_max)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(6)

    def set_lock_right(self, w:int):
        self._lock_right = int(w); self._apply()

    def set_left_max(self, w:int):
        self._left_max = int(w); self._apply()

    def _apply(self):
        if self.count() < 2:
            return
        handles   = (self.count() - 1) * self.handleWidth()
        total_w   = max(0, self.size().width() - handles)
        if total_w <= 0:
            return

        right = min(self._lock_right, total_w)         # fixed right
        left  = min(self._left_max, total_w - right)   # capped left
        spacer = max(0, total_w - right - left)        # remainder

        if self.count() == 2:
            self.setSizes([left + spacer, right])      # no spacer widget, shove into left
        else:
            # order must be [left, right, spacer]
            self.setSizes([left, right, spacer])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def apply_locked_sizes_later(self):
        QTimer.singleShot(0, self._apply)

class FiftyFiftySplitter(QSplitter):
    """Horizontal splitter that keeps a 50/50 split, honoring minimums."""
    def __init__(self, min_left=420, min_right=420, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._min_left  = int(min_left)
        self._min_right = int(min_right)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(6)

    def _apply(self):
        if self.count() < 2:
            return
        handles = (self.count() - 1) * self.handleWidth()
        total   = max(0, self.size().width() - handles)
        if total <= 0:
            return

        # target = half, but respect minimums
        half = total // 2
        lmin = max(self.widget(0).minimumWidth(), self._min_left)
        rmin = max(self.widget(1).minimumWidth(), self._min_right)

        left  = max(half, lmin)
        right = total - left
        if right < rmin:
            right = rmin
            left  = total - right

        self.setSizes([max(0, left), max(0, total - left)])

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._apply)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()


        
class FullWidthEditDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        ed = QLineEdit(parent)
        ed.setFrame(False)
        # Override the global min-height so it matches the row
        ed.setStyleSheet("min-height: 0px; padding: 0px 6px;")
        return ed

    def updateEditorGeometry(self, editor, option, index):
        # Fit exactly inside the row, tiny insets
        r = option.rect.adjusted(4, 2, -4, -2)
        editor.setGeometry(r)
        editor.setFixedHeight(r.height())  # <- pin to row height

    # keep row height + editor aligned using the same padding
    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        # match the 6px vertical padding (3 top + 3 bottom) below
        return hint

class TestSetupPage(QWidget):
    start_test_requested = pyqtSignal(dict)  # emits the stage list

    def __init__(self, parent=None, device_checker=None):
        super().__init__(parent)
        self.device_checker = device_checker   # <— store optional callback

        self.setFont(QFont("Segoe UI", 12))  # Try 12–13 for large UI, adjust to taste


        self.stage_data_list = []

        # ---------- Top bar ----------
        top_bar = QHBoxLayout()
        title = QLabel("Test Set Up")
        title.setObjectName("TitleLabel")           # <-- lets the CSS target it
        self.start_btn = QPushButton("▶ Go to Test View")
        self.start_btn.setFixedHeight(42)
        top_bar.addWidget(title)
        top_bar.addStretch(1)
        top_bar.addWidget(self.start_btn, alignment=Qt.AlignRight)
        self.start_btn.setObjectName("PrimaryButton")

        
        # ---------- Left: stage list + actions ----------
        self.stage_selector = QListWidget()
        self.stage_selector.setUniformItemSizes(True)
        self.stage_selector.setAlternatingRowColors(True)
        self.stage_selector.setMinimumWidth(260)
        self.stage_selector.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.stage_selector.setItemDelegate(FullWidthEditDelegate(self.stage_selector))
        self.stage_selector.setSpacing(2)  # a bit more room so the editor doesn’t clip

        self.stage_selector.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.stage_selector.setFrameShape(QFrame.StyledPanel)
        self.stage_selector.setFrameShadow(QFrame.Plain)
        self.stage_selector.setViewportMargins(0, 0, 0, 0)  # no hidden margins
        
        self.add_btn = QPushButton("+ Add Stage")
        self.add_btn.setMinimumHeight(34)

        left_footer = QHBoxLayout()
        self.rename_btn = QPushButton("✎ Rename")
        self.up_btn = QPushButton("⬆ Move Up")
        self.down_btn = QPushButton("⬇ Move Down")
        self.delete_btn = QPushButton("🗑 Delete Stage")
        left_footer.addWidget(self.rename_btn)
        left_footer.addWidget(self.up_btn)
        left_footer.addWidget(self.down_btn)
        left_footer.addWidget(self.delete_btn)

        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Test Stages"))
        left_col.addWidget(self.stage_selector)
        left_col.addWidget(self.add_btn)         # Add above footer for proximity
        left_col.addLayout(left_footer)
        left_wrap = QWidget()
        left_wrap.setLayout(left_col)

        # ---------- Right: stack of per-stage editors ----------
        self.editor_stack = QStackedWidget()
        right_wrap = QWidget()
        right_col = QVBoxLayout(right_wrap)
        right_col.setContentsMargins(0,0,0,0)
        right_col.addWidget(self.editor_stack)

        # ---------- 50/50 splitter ----------
        self.splitter = FiftyFiftySplitter(min_left=420, min_right=420, parent=self)
        self.splitter.addWidget(left_wrap)
        self.splitter.addWidget(right_wrap)     # no spacer, no caps
        # showEvent will apply once the widget is visible

        
        # ---------- Page layout ----------
        page = QVBoxLayout(self)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(8)
        page.addLayout(top_bar)
        page.addWidget(self.splitter)

        # Global style tightening
        self.setStyleSheet("""
            QWidget { font-size: 18px; }

            QLabel#TitleLabel { font-size: 24px; font-weight: 600; }

            QListWidget { background: #fff; border: 1px solid #ddd; }
            QListWidget::item { padding: 10px 12px; }
            QListView { show-decoration-selected: 1; }

            /* No global min-heights — just padding */
            QPushButton { padding: 10px 14px; font-weight: 500; }
            QLineEdit, QComboBox { padding: 8px 10px; }
            QCheckBox { padding: 6px 2px; }

            /* Only the primary button is tall */
            QPushButton#StartButton {
                min-height: 40px;
                background-color: #0078d7;
                color: white; border: none; border-radius: 6px;
                padding: 8px 16px; font-weight: bold;
            }
            QPushButton#StartButton:hover { background-color: #006cbe; }
            QPushButton#StartButton:pressed { background-color: #005a9e; }

            /* Form inputs have a modest min-height, scoped to the group box */
            QGroupBox#StageForm QLineEdit,
            QGroupBox#StageForm QComboBox { min-height: 30px; }
        """)

        # ---------- Signals ----------
        self.add_btn.clicked.connect(self.add_stage)
        self.rename_btn.clicked.connect(self.rename_stage)
        self.up_btn.clicked.connect(self.move_stage_up)
        self.down_btn.clicked.connect(self.move_stage_down)
        self.delete_btn.clicked.connect(self.delete_stage)
        self.stage_selector.currentRowChanged.connect(self.editor_stack.setCurrentIndex)
        self.stage_selector.setEditTriggers(QListWidget.DoubleClicked | QListWidget.EditKeyPressed)
        self.stage_selector.itemChanged.connect(self._on_item_changed)
        self.start_btn.clicked.connect(self._emit_start_test)

        # Create initial stage so page isn't blank
        self.add_stage()

    # ---- Actions ----
    def rename_stage(self):
        row = self.stage_selector.currentRow()
        if row != -1:
            self.stage_selector.editItem(self.stage_selector.item(row))

    def get_test_config(self):
        # TODO: fetch these from wherever you store them (probably passed in when dialog closes)
        h0_mm = getattr(self, "h0_mm", 0.0)
        d0_mm = getattr(self, "d0_mm", 0.0)

        A0_mm2 = math.pi * (d0_mm/2.0)**2 if d0_mm > 0 else 0.0
        v0_mm3 = A0_mm2 * h0_mm if A0_mm2 > 0 else 0.0

        return {
            "stages": self.stage_data_list,
            "h0_mm": h0_mm,
            "d0_mm": d0_mm,
            "A0_mm2": A0_mm2,
            "v0_mm3": v0_mm3,
        }

    def _emit_start_test(self):
        # 0) Confirm
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Start Test?")
        box.setText("Are you sure you want to start the test?")
        box.setInformativeText("Make sure the specimen is installed and all devices are connected.")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)   # default to No for safety
        if box.exec_() != QMessageBox.Yes:
            return

        # 1) Check devices (if a checker was provided)
        ok, details = True, ""
        if callable(getattr(self, "device_checker", None)):
            try:
                result = self.device_checker()
                if isinstance(result, tuple):
                    ok, details = bool(result[0]), str(result[1]) if len(result) > 1 else ""
                else:
                    ok = bool(result)
            except Exception as e:
                ok, details = False, f"Device check failed: {e}"

        if not ok:
            QMessageBox.critical(
                self, "Devices not ready",
                details or "Required devices are not connected. Please connect devices and try again."
            )
            return

        # 2) Save all editor inputs safely
        for i in range(self.editor_stack.count()):
            editor = self.editor_stack.widget(i)
            if hasattr(editor, "save_inputs"):
                editor.save_inputs()

        # 🔧 Force details dialog to appear every time
        if hasattr(self.parent(), "_pending_test_details"):
            self.parent()._pending_test_details = None

        # 3) Go! — emit full config, not just stage list
        self.start_test_requested.emit(self.get_test_config())


    def add_stage(self):
        data = StageData(name=f"Stage {len(self.stage_data_list)+1}")
        self.stage_data_list.append(data)

        item = QListWidgetItem(data.name)
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.stage_selector.addItem(item)

        editor = TestStageEditor(data, self)
        editor.layout_changed.connect(self.splitter._apply)   # keep the split after form changes
        self.editor_stack.addWidget(editor)
        self.editor_stack.setCurrentWidget(editor)


        # Select the newly added stage in the list
        self.stage_selector.setCurrentRow(self.stage_selector.count() - 1)

    def delete_stage(self):
        current_row = self.stage_selector.currentRow()
        if current_row == -1:
            return

        # Remove from data list and GUI
        self.stage_data_list.pop(current_row)

        w = self.editor_stack.widget(current_row)
        self.editor_stack.removeWidget(w)
        w.deleteLater()

        self.stage_selector.takeItem(current_row)

        # Show another stage if available
        if self.stage_data_list:
            new_row = min(current_row, len(self.stage_data_list) - 1)
            self.stage_selector.setCurrentRow(new_row)

        self.renumber_stage_labels()

    def move_stage_up(self):
        index = self.stage_selector.currentRow()
        if index > 0:
            # swap data
            self.stage_data_list[index], self.stage_data_list[index-1] = \
                self.stage_data_list[index-1], self.stage_data_list[index]

            # swap editors
            top = self.editor_stack.widget(index)
            bottom = self.editor_stack.widget(index - 1)
            self.editor_stack.removeWidget(top)
            self.editor_stack.removeWidget(bottom)
            self.editor_stack.insertWidget(index - 1, top)
            self.editor_stack.insertWidget(index, bottom)

            # move the QListWidgetItem
            item = self.stage_selector.takeItem(index)
            self.stage_selector.insertItem(index - 1, item)
            self.stage_selector.setCurrentRow(index - 1)

    def move_stage_down(self):
        index = self.stage_selector.currentRow()
        if 0 <= index < len(self.stage_data_list) - 1:
            # swap data
            self.stage_data_list[index], self.stage_data_list[index+1] = \
                self.stage_data_list[index+1], self.stage_data_list[index]

            # swap editors
            top = self.editor_stack.widget(index)
            bottom = self.editor_stack.widget(index + 1)
            self.editor_stack.removeWidget(bottom)
            self.editor_stack.removeWidget(top)
            self.editor_stack.insertWidget(index, bottom)
            self.editor_stack.insertWidget(index + 1, top)

            # move the QListWidgetItem
            item = self.stage_selector.takeItem(index)
            self.stage_selector.insertItem(index + 1, item)
            self.stage_selector.setCurrentRow(index + 1)

    def _on_item_changed(self, item):
        idx = self.stage_selector.row(item)
        if 0 <= idx < len(self.stage_data_list):
            self.stage_data_list[idx].name = item.text()

    def renumber_stage_labels(self):
        for i in range(self.stage_selector.count()):
            item = self.stage_selector.item(i)
            if re.fullmatch(r"Stage \d+", item.text()):  # only pure default names
                item.setText(f"Stage {i+1}")

