import os
import sys
import time
import ftd2xx
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QListWidget, QListWidgetItem,
    QComboBox, QTextEdit, QGroupBox, QFormLayout, QLineEdit, QMessageBox, QInputDialog,
    QToolBar, QAction, QDialog, QDialogButtonBox, QDoubleSpinBox, QCheckBox
)
from PyQt5.QtCore import Qt, QSize, QMetaObject, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont, QIcon, QPixmap, QGuiApplication
from device_controllers.loadframe import LoadFrameController
from device_controllers.lf50_movement import LF50Mover
from device_controllers.sttdpc_controller import STTDPCController
from station_config_page import StationConfigPage
from manual_control_page import ManualControlPage
from calibration_wizard import CalibrationManager
from data_view_page import DataViewPage
from device_controllers.serial_pad_reader import SerialPadReader
from triaxial_test_manager import TriaxialTestManager
from test_set_up_page import TestSetupPage
from test_view_page import TestViewPage
from device_settings_page import DeviceSettingsPage
from calibration_popup import CalibrationInputDialog
from ftd2xx_controllers.stddpc_ftd2xx_controller import STDDPC_FTDI_HandleController
import traceback, sys
from test_set_up_page import StageData
from sip import isdeleted
from test_details_dialog import TestDetailsDialog



from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

class HomePage(QWidget):
    def __init__(self, stack, test_setup_page, station_config_page, data_view_page, parent=None):
        super().__init__(parent)

        # --- root layout on self ---
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignCenter)

        # --- title / subtitle ---
        title = QLabel("Welcome to SoilMate v2025")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont("Segoe UI", QFont.Bold)
        title_font.setPointSize(80)   # now REALLY big
        title.setFont(title_font)

        subtitle = QLabel("Choose an action to get started:")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle_font = QFont("Segoe UI")
        subtitle_font.setPointSize(28)  # medium sized
        subtitle.setFont(subtitle_font)

        root.addWidget(title)
        root.addWidget(subtitle)

        # --- buttons ---
        btn_font = QFont("Segoe UI")
        btn_font.setPixelSize(24)   # bigger than before

        btn_new_test = QPushButton("➕ New Test")
        btn_station  = QPushButton("⚙ Station Setup")
        btn_data     = QPushButton("📊 View Live Data")

        for btn in (btn_new_test, btn_station, btn_data):
            btn.setFont(btn_font)
            btn.setFixedHeight(80)       # taller buttons
            btn.setMinimumWidth(320)     # wider buttons
            root.addWidget(btn, alignment=Qt.AlignHCenter)


        # --- navigation wiring ---
        btn_new_test.clicked.connect(lambda: stack.setCurrentWidget(test_setup_page))
        btn_station.clicked.connect(lambda: stack.setCurrentWidget(station_config_page))
        btn_data.clicked.connect(lambda: stack.setCurrentWidget(data_view_page))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoilMate v2025")
        self.setGeometry(100, 100, 1000, 600)

        self.lf_controller = None
        self.back_pressure_controller = None
        self.cell_pressure_controller = None
        self.serial_pad = None
        self.manual_page = None
        self.test_manager = None
        self._last_plot_ts = 0.0
        self._polling_enabled = False
        self._prefs = {}
        if hasattr(self, "_load_prefs"):
            self._load_prefs()


        self.PRESSURE_SAMPLE_MS = 300  # 0.3 s
        self.pressure_timer = QTimer(self)
        self.pressure_timer.setInterval(self.PRESSURE_SAMPLE_MS)
        self.pressure_timer.setTimerType(Qt.CoarseTimer)  # lighter than PreciseTimer
        self.pressure_timer.timeout.connect(self._pressure_tick)


        self.setStyleSheet("""
            QWidget {
                font-family: 'Segoe UI', sans-serif;
                font-size: 16px;
                background-color: #f9f9f9;
            }
            QListWidget {
                background-color: #f0f0f0;
                border: none;
            }
            QListWidget::item {
                padding: 12px;
                font-size: 16px;
            }
            QListWidget::item:selected {
                background-color: #d0d0d0;
                border-left: 4px solid #2a82da;
            }
            QPushButton {
                background-color: white;
                border: 1px solid #ccc;
                padding: 8px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e6f0ff;
            }
            QLabel {
                color: #333;
            }
        """)

        central_widget = QWidget()
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)  # only called once

        self.sidebar = QListWidget()
        self.sidebar.setIconSize(QSize(24, 24))

        home_icon = QIcon("icons/house.png")
        wrench_icon = QIcon("icons/wrench.png")
        clipboard_icon = QIcon("icons/clipboard-list.png")
        chart_icon = QIcon("icons/chart-spline.png")
        terminal_icon = QIcon("icons/terminal.png")
        move_icon = QIcon("icons/move.png")
        data_view_icon = QIcon("icons/message-square-text.png")
        data_settings_icon = QIcon("icons/settings.png")

        self.sidebar.addItem(QListWidgetItem(home_icon, "Dashboard"))
        self.sidebar.addItem(QListWidgetItem(wrench_icon, "Station Configuration"))
        self.sidebar.addItem(QListWidgetItem(clipboard_icon, "Test Set Up"))
        self.sidebar.addItem(QListWidgetItem(chart_icon, "Test View"))
        self.sidebar.addItem(QListWidgetItem(move_icon, "Manual Control"))
        self.sidebar.addItem(QListWidgetItem(data_view_icon, "Data View"))
        self.sidebar.addItem(QListWidgetItem(data_settings_icon, "Device Settings"))

        self.sidebar.setFixedWidth(210)
        main_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        self.calibration_manager = CalibrationManager(
            serialpad_dir="calibration/serial_pad",
            pressure_json_path="calibration/stddpc/pressure_calibrations.json",
            log=self.log
        )

        # Instantiate shims that wrap the FTDI backends
        self.lf_controller = LoadFrameController(log=self.log)
        self.cell_pressure_controller = STTDPCController(
            log=self.log, calibration_manager=self.calibration_manager
        )
        self.back_pressure_controller = STTDPCController(
            log=self.log, calibration_manager=self.calibration_manager
        )

        # NEW: compatibility aliases for older code paths
        self.load_frame = self.lf_controller
        self.cell_controller = self.cell_pressure_controller
        self.back_controller = self.back_pressure_controller
        

        self.config_page = StationConfigPage(log=self.log)
        self.setup_page = TestSetupPage(device_checker=self._check_devices)
        self.setup_page.start_test_requested.connect(self._on_go_to_test_view)


        self.device_settings_page = DeviceSettingsPage()
        self.data_view_page = DataViewPage(self.calibration_manager, log=self.config_page.log)
        self.view_page = TestViewPage([], main_window=self)
        self.view_page.start_test_clicked.connect(self.start_test)
        self.manual_page = ManualControlPage()

        self.home_page = HomePage(self.stack,
                                  self.setup_page,
                                  self.config_page,       # <- correct attribute
                                  self.data_view_page)    # <- now exists

        
        self.device_settings_page.populate_devices(
            self._list_devices(), select=self._current_device_name()
        )
        lf = (self._prefs.get("lf_limits")
              or {"min_pos_mm": -50.0, "max_pos_mm": 50.0, "max_vel_mm_min": 50.0})
        self.device_settings_page.set_loadframe_limits(
            lf["min_pos_mm"], lf["max_pos_mm"], lf["max_vel_mm_min"]
        )
        spad = self._prefs.get("serialpad") or {"assignments": {}, "sensors": {}}
        self.device_settings_page.set_serialpad_config(spad.get("assignments", {}), spad.get("sensors", {}))

        self.device_settings_page.apply_spad_config_requested.connect(self._apply_serialpad_config)

        self.device_settings_page.reload_spad_requested.connect(self._hydrate_serialpad_from_live)

        self.config_page.connect_requested.connect(self._on_connect_requested)  # NEW

        # populate STDDPC serials (from calibration file; adds connected ones below on connect)
        try:
            serials = self.calibration_manager.get_pressure_device_serials()
        except Exception:
            serials = []
        self.device_settings_page.set_stddpc_serials(serials)

        # wire the STDDPC calibration actions
        self.device_settings_page.reload_stddpc_cal_requested.connect(self._on_reload_stddpc_cal)
        self.device_settings_page.apply_stddpc_cal_requested.connect(self._on_apply_stddpc_cal)


        self.manual_page = ManualControlPage()

        # Route Manual page actions to your real controllers
        self.manual_page.send_axial_position_requested.connect(self._set_axial_position)
        self.manual_page.send_axial_velocity_requested.connect(self._set_axial_velocity)
        self.manual_page.stop_axial_requested.connect(self._stop_axial)

        self.manual_page.send_cell_pressure_requested.connect(self._set_cell_pressure)
        self.manual_page.stop_cell_pressure_requested.connect(self._stop_cell_pressure)

        self.manual_page.send_back_pressure_requested.connect(self._set_back_pressure)
        self.manual_page.stop_back_pressure_requested.connect(self._stop_back_pressure)

        # Initial enable/disable based on current connection state
        self.manual_page.set_axial_enabled(self._is_connected(self.lf_controller))
        self.manual_page.set_cell_enabled(self._is_connected(self.cell_pressure_controller))
        self.manual_page.set_back_enabled(self._is_connected(self.back_pressure_controller))

        # Wire actions
        self.device_settings_page.refresh_devices_requested.connect(
            lambda: self.device_settings_page.populate_devices(
                self._list_devices(), select=self._current_device_name()
            )
        )
        self.device_settings_page.save_device_requested.connect(self._on_save_default_device)

        self.device_settings_page.apply_lf_limits_requested.connect(
            lambda a,b,c: self._apply_lf_limits(a, b, c)
        )

        self.device_settings_page.apply_limits_requested.connect(
            lambda lo, hi: self._apply_pressure_limits(lo, hi)
        )
        # after you create self.view_page
        self.view_page.run_another_test_requested.connect(self._on_run_another_test)
        self.view_page.back_to_setup_requested.connect(self._on_back_to_setup)


        # start Data View updates immediately; harmless if nothing connected yet
        self.data_timer = QTimer(self)
        self.data_timer.setInterval(300)  # 3–5 Hz is fine on GUI thread
        self.data_timer.setTimerType(Qt.CoarseTimer)
        self.data_timer.timeout.connect(self._update_dataview_from_devices)


        self.view_page.pause_requested.connect(self.on_pause_stage)
        self.view_page.resume_requested.connect(self.on_resume_stage)
        self.view_page.stop_requested.connect(self.on_stop_stage)


        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.config_page)
        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.view_page)  # now permanent and indexed correctly
        self.stack.addWidget(self.manual_page)
        self.stack.addWidget(self.data_view_page)
        self.stack.addWidget(self.device_settings_page)

        # map stack index -> page (and vice versa if you like)
        self._page_order = [
            self.home_page,
            self.config_page,
            self.setup_page,
            self.view_page,
            self.manual_page,
            self.data_view_page,
            self.device_settings_page,
        ]

        # When the stack changes (e.g., via Dashboard buttons), update the sidebar row
        self.stack.currentChanged.connect(self._on_stack_changed)

        # Keep this one you already have:
        self.sidebar.currentRowChanged.connect(self.display_page)


        self.sidebar.currentRowChanged.connect(self.display_page)
        self.sttdpc_controller = None

        self.serialpad_timer = QTimer(self)
        self.serialpad_timer.setInterval(200)  # 5 Hz is plenty to start
        self.serialpad_timer.timeout.connect(self._poll_serialpad)
        
        QTimer.singleShot(0, self._fit_to_screen)
        self.display_page(self.sidebar.currentRow() if self.sidebar.currentRow() >= 0 else 0)

    def _on_save_default_device(self, name: str):
        if self._select_device(name):
            self._info("Default Device Saved", f"Connected device set to:\n\n  {name}")

    def display_page(self, index):
        self.stack.setCurrentIndex(index)
        w = self.stack.widget(index)
        if w is self.device_settings_page:
            self._hydrate_serialpad_from_live()
            # stay in view mode
            if hasattr(self.device_settings_page, "set_spad_edit_enabled"):
                self.device_settings_page.set_spad_edit_enabled(False)
        needs_poll = (w is self.manual_page) or (w is self.data_view_page) or (w is self.view_page)
        self._set_polling_enabled(needs_poll)

    def _on_reload_stddpc_cal(self, serial: str):
        """Fill the 3 fields from calibration JSON (or zeros if not found)."""
        vals = {"pressure_quanta": 0.0, "pressure_offset": 0.0, "volume_quanta": 0.0}
        try:
            got = self.calibration_manager.get_pressure_calibration(serial)  # loads JSON
            if isinstance(got, dict):
                vals.update(got)
        except Exception:
            pass
        self.device_settings_page.set_stddpc_values(vals["pressure_quanta"], vals["pressure_offset"], vals["volume_quanta"])

    def _on_go_to_test_view(self, config: dict):
        """
        Prompt for test details when the user presses Go to Test View.
        Store them, then switch to the Test View page.
        """
        try:
            # Ask for details up-front
            dlg = TestDetailsDialog(self, default_sample_id="", default_period_s=0.5)
            if dlg.exec_() != dlg.Accepted:
                self.log("[✗] Test cancelled by user.")
                return
            self._pending_test_details = dlg.values()

            # Keep the setup config too (geometry, stages, etc.)
            self.test_context = config
            print("[DEBUG] Test details accepted ->", self._pending_test_details)

            # Only switch pages here — don’t call start_test yet
            self.stack.setCurrentWidget(self.view_page)
            self.sidebar.setCurrentRow(3)

        except Exception as e:
            self.log(f"[✗ GUI] Failed to accept test config: {e}")
            return



    def _on_stack_changed(self, idx: int):
        # visually select the matching row without re-triggering display_page
        if 0 <= idx < self.sidebar.count():
            self.sidebar.blockSignals(True)
            self.sidebar.setCurrentRow(idx)
            self.sidebar.blockSignals(False)

        # ensure the same side-effects as clicking the sidebar (polling, hydration)
        try:
            self.display_page(idx)
        except Exception:
            pass


    def _push_cal_to_driver(self, serial: str, p_q: float, p_off: float, v_q: float):
        """Best-effort: immediately inform connected drivers that match this serial."""
        for ctrl in (self.cell_pressure_controller, self.back_pressure_controller):
            drv = getattr(ctrl, "driver", None)
            if not drv:
                continue
            # try to get its serial
            try:
                dserial = getattr(drv, "serial", None) or getattr(drv, "serial_number", None)
                if callable(dserial): dserial = dserial()
            except Exception:
                dserial = None
            if (dserial or "") != serial:
                continue

            # try common update hooks; otherwise they’ll pick it up next reconnect
            for name in ("set_pressure_calibration", "set_calibration_params", "set_quanta_offset"):
                fn = getattr(drv, name, None)
                if callable(fn):
                    try:
                        fn(p_q, p_off, v_q)  # tolerant: unused args will be ignored by specific impls
                        self.log(f"[i] Pushed calibration to driver via {name}()")
                        break
                    except Exception as e:
                        self.log(f"[!] Driver {name} failed: {e}")

    def _on_apply_stddpc_cal(self, serial: str, p_q: float, p_off: float, v_q: float):
        """Persist to JSON and push to live driver if connected; show a summary popup."""
        # previous values (for the diff in the popup)
        prev = {"pressure_quanta": 0.0, "pressure_offset": 0.0, "volume_quanta": 0.0}
        try:
            got = self.calibration_manager.get_pressure_calibration(serial)
            if isinstance(got, dict):
                prev.update(got)
        except Exception:
            pass

        # save to JSON (same mechanism you already use)
        self.calibration_manager.set_pressure_calibration(serial, {
            "pressure_quanta": float(p_q),
            "pressure_offset": float(p_off),
            "volume_quanta": float(v_q),
        })

        # push to live devices (if connected)
        self._push_cal_to_driver(serial, p_q, p_off, v_q)

        # feedback
        self._info("STDDPC Calibration Saved", (
            f"Device: {serial}\n\n"
            f"pressure_quanta: {prev['pressure_quanta']:.7f} → {p_q:.7f}\n"
            f"pressure_offset: {prev['pressure_offset']:.3f} → {p_off:.3f}\n"
            f"volume_quanta:   {prev['volume_quanta']:.5f} → {v_q:.5f}"
        ))


    def _hydrate_serialpad_from_live(self):
        assignments = {}
        sensors = {}
        sp = getattr(self, "serial_pad", None)
        if sp:
            try:
                if hasattr(sp, "get_assignments"): assignments = sp.get_assignments() or {}
                if hasattr(sp, "get_sensors"):     sensors     = sp.get_sensors()     or {}
            except Exception:
                pass
        if not assignments:
            spad_prefs = (self._prefs.get("serialpad") or {})
            assignments = spad_prefs.get("assignments", {}) or {}
            sensors     = spad_prefs.get("sensors", {})     or sensors
        if not assignments:
            # sensible default mapping
            roles = ["Axial Load","Pore Pressure","Axial Displacement",
                     "Local Axial 1","Local Axial 2","Local Radial","Unused 1","Unused 2"]
            assignments = {i: {"role": roles[i], "sensor": ""} for i in range(8)}

        # fill the card
        self.device_settings_page.set_serialpad_config(assignments, sensors)
    def on_pause_stage(self):
        if self.test_manager:
            self.test_manager.pause()
            if self.view_page:
                self.view_page.set_paused_state(True)
            self.log("[⏸] Stage paused.")
            # Pause GUI-side pressure polling too
            if hasattr(self, "pressure_timer") and self.pressure_timer.isActive():
                self.pressure_timer.stop()
                self.log("[i] Paused pressure polling.")

    def _set_polling_enabled(self, on: bool):
        self._polling_enabled = bool(on)
        for t in (getattr(self, "data_timer", None), getattr(self, "pressure_timer", None)):
            if not t:
                continue
            if on and not t.isActive():
                t.start()
            elif (not on) and t.isActive():
                t.stop()
                
    def _apply_serialpad_config(self, cfg: dict):
        old = self._prefs.get("serialpad") or {"assignments": {}, "sensors": {}}
        new = {"assignments": dict(cfg.get("assignments") or {}),
               "sensors": dict(cfg.get("sensors") or {})}

        # persist
        self._prefs["serialpad"] = new
        try: self._save_prefs()
        except Exception: pass

        # push to live reader
        sp = getattr(self, "serial_pad", None)
        if sp:
            try:
                if hasattr(sp, "set_assignments"):
                    sp.set_assignments(new["assignments"], new["sensors"])
                else:
                    # backwards-compat shims
                    if hasattr(sp, "set_channel_assignments"):
                        sp.set_channel_assignments(new["assignments"])
                    if hasattr(sp, "set_sensors"):
                        sp.set_sensors(new["sensors"])
            except Exception as e:
                self.log(f"[!] Failed to apply SerialPad config: {e}")

        # build “what changed” summary
        changes = []
        # channel mapping changes
        for ch in range(8):
            o = old["assignments"].get(ch, {})
            n = new["assignments"].get(ch, {})
            if (o.get("role"), o.get("sensor")) != (n.get("role"), n.get("sensor")):
                changes.append(f"Ch {ch}: {o.get('role','–')} / {o.get('sensor','–')} → {n.get('role','–')} / {n.get('sensor','–')}")
        # new sensors
        for name, meta in new["sensors"].items():
            if name not in old["sensors"]:
                changes.append(f"Sensor added: {name} [{meta.get('kind','')}] {meta.get('scale',1)}× + {meta.get('offset',0)} {meta.get('units','')}")

        self._info("SerialPad Settings Applied",
                   "SerialPad configuration updated.\n\n" + ("\n".join(changes) if changes else "No differences."))

    def _apply_lf_limits(self, min_pos_mm: float, max_pos_mm: float, max_vel_mm_min: float):
        old = (self._prefs.get("lf_limits")
               or {"min_pos_mm": -50.0, "max_pos_mm": 50.0, "max_vel_mm_min": 50.0})

        self._prefs["lf_limits"] = {
            "min_pos_mm": float(min_pos_mm),
            "max_pos_mm": float(max_pos_mm),
            "max_vel_mm_min": float(max_vel_mm_min),
        }
        try: self._save_prefs()
        except Exception: pass

        lf = getattr(self, "lf_controller", None)
        # Push to wrapper & driver (keep your current forwarding code)
        try:
            if lf and hasattr(lf, "set_motion_limits"):
                lf.set_motion_limits(min_pos_mm, max_pos_mm, max_vel_mm_min)
            drv = getattr(lf, "driver", None)
            if drv and hasattr(drv, "set_motion_limits"):
                drv.set_motion_limits(min_pos_mm, max_pos_mm, max_vel_mm_min)
        except Exception as e:
            self.log(f"[!] Failed to apply LF limits: {e}")

        # Read back effective (driver wins)
        eff = None
        for obj in (lf, getattr(lf, "driver", None)):
            if obj and hasattr(obj, "get_motion_limits"):
                try:
                    eff = obj.get_motion_limits()
                    break
                except Exception:
                    pass

        if eff:
            a, b, c = eff
            msg = (
                "Load frame limits updated.\n\n"
                f"Min position:  {old['min_pos_mm']:.2f} → {a:.2f} mm\n"
                f"Max position:  {old['max_pos_mm']:.2f} → {b:.2f} mm\n"
                f"Max velocity:  {old['max_vel_mm_min']:.2f} → {c:.2f} mm/min"
            )
        else:
            # Fallback if we can’t read back
            msg = (
                "Load frame limits updated.\n\n"
                f"Min position:  {old['min_pos_mm']:.2f} → {min_pos_mm:.2f} mm\n"
                f"Max position:  {old['max_pos_mm']:.2f} → {max_pos_mm:.2f} mm\n"
                f"Max velocity:  {old['max_vel_mm_min']:.2f} → {max_vel_mm_min:.2f} mm/min"
            )

        self._info("Load Frame Limits Applied", msg)
        return True



    def on_resume_stage(self):
        if not self.test_manager:
            return
        tm = self.test_manager

        # If the stage thread no longer exists or isn’t running, restart this stage.
        th = getattr(tm, "thread", None)
        try:
            thread_running = bool(th and (not isdeleted(th)) and th.isRunning())
        except Exception:
            thread_running = False

        if thread_running:
            tm.resume()  # normal pause/resume path
        else:
            # the previous Stop fully ended the stage → start this stage again
            tm.run_stage(tm.current_stage_index)

        if self.view_page:
            self.view_page.set_paused_state(False)
        self.log("[▶] Stage continued.")
        if hasattr(self, "pressure_timer") and not self.pressure_timer.isActive():
            self.pressure_timer.start()
            self.log("[i] Resumed pressure polling.")

    def on_stop_stage(self):
        if not self.test_manager:
            return

        resp = QMessageBox.question(
            self,
            "Stop Stage?",
            "Are you sure you want to stop the current stage?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            self.log("[■] Stop cancelled by user.")
            return

        self.log("[■] Stop confirmed; stopping devices…")
        self.view_page._stop_triggered = True
        self.test_manager.stop_requested = True    # <-- add this


        try:
            self.test_manager.stop_current_stage()
        except Exception as e:
            self.log(f"[✗ GUI] Failed to stop stage: {e}")


    def _fit_to_screen(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        min_w, min_h = 1000, 650
        w = min(max(min_w, self.width()),  screen.width())
        h = min(max(min_h, self.height()), screen.height())
        self.resize(w, h)
        x = max(screen.left(),  min(self.x(), screen.right()  - w))
        y = max(screen.top(),   min(self.y(), screen.bottom() - h))
        self.move(x, y)

    def _pick_ftdi_serial(self, title: str):
        try:
            devs = ftd2xx.listDevices() or []
            serials = [(d.decode() if isinstance(d, bytes) else str(d)) for d in devs]
        except Exception as e:
            self.log(f"[✗] Could not list FTDI devices: {e}")
            return None
        if not serials:
            self.log("[✗] No FTDI (D2XX) devices found.")
            return None
        serial, ok = QInputDialog.getItem(self, title, "Select FTDI serial:", serials, 0, False)
        return serial if ok else None

    def _on_connect_requested(self, device: dict):
        dtype = (device.get("type") or "").strip()
        serial = (device.get("serial") or "").strip()
        row = device.get("_row", None)

        if dtype == "Load Frame":
            if not serial:
                self.log("[✗] Please choose a serial for the Load Frame row before connecting.")
                if row is not None:
                    self.config_page.set_status(row, False)
                return
            if self.lf_controller.connect(serial):
                self.log(f"[✓] Load frame connected: {serial}")
                self.manual_page.set_axial_enabled(True)
                self._write_serial_to_row(row, serial)
                if row is not None:
                    self.config_page.set_status(row, True)
            else:
                self.log("[✗] Load frame connection failed.")
                if row is not None:
                    self.config_page.set_status(row, False)

        elif dtype == "Cell Pressure Controller":
            if not serial:
                self.log("[✗] Please choose a serial for the Cell Pressure row before connecting.")
                if row is not None:
                    self.config_page.set_status(row, False)
                return

            backend = STDDPC_FTDI_HandleController(
                log=self.log,
                calibration_manager=self.calibration_manager
            )
            if backend.connect(serial):
                self.cell_pressure_controller.attach_driver(backend)
                self.cell_pressure_controller.connected = True
                self.log(f"[✓] Cell pressure controller connected: {serial}")
                self.manual_page.set_cell_enabled(True)
                self._write_serial_to_row(row, serial)
##                if not self.pressure_timer.isActive():
##                    self.pressure_timer.start()
##                if not self.data_timer.isActive():
##                    self.data_timer.start()
##                self._start_pressure_polling()
                self._prime_pressure_cards()
                if row is not None:
                    self.config_page.set_status(row, True)

                try:
                    serials = self.calibration_manager.get_pressure_device_serials()
                    if serial not in serials: serials.append(serial)
                    self.device_settings_page.set_stddpc_serials(sorted(set(serials)), select=serial)
                    self._on_reload_stddpc_cal(serial)
                except Exception:
                    pass
            else:
                self.log("[✗] Cell pressure controller connection failed.")
                if row is not None:
                    self.config_page.set_status(row, False)

        elif dtype == "Back Pressure Controller":
            if not serial:
                self.log("[✗] Please choose a serial for the Back Pressure row before connecting.")
                if row is not None:
                    self.config_page.set_status(row, False)
                return

            backend = STDDPC_FTDI_HandleController(
                log=self.log,
                calibration_manager=self.calibration_manager
            )
            if backend.connect(serial):
                self.back_pressure_controller.attach_driver(backend)
                self.back_pressure_controller.connected = True
                self.log(f"[✓] Back pressure controller connected: {serial}")
                self.manual_page.set_back_enabled(True)
                self._write_serial_to_row(row, serial)
##                if not self.pressure_timer.isActive():
##                    self.pressure_timer.start()
##                if not self.data_timer.isActive():
##                    self.data_timer.start()
##                self._start_pressure_polling()
                self._prime_pressure_cards()
                if row is not None:
                    self.config_page.set_status(row, True)

                try:
                    serials = self.calibration_manager.get_pressure_device_serials()
                    if serial not in serials: serials.append(serial)
                    self.device_settings_page.set_stddpc_serials(sorted(set(serials)), select=serial)
                    self._on_reload_stddpc_cal(serial)
                except Exception:
                    pass
            else:
                self.log("[✗] Back pressure controller connection failed.")
                if row is not None:
                    self.config_page.set_status(row, False)

        elif dtype == "Serial Pad":
            if not serial:
                self.log("[✗] Enter a COM port (e.g., COM5) for the Serial Pad row before connecting.")
                if row is not None:
                    self.config_page.set_status(row, False)
                return
            try:
                self.serial_pad = SerialPadReader(
                    port=serial,
                    calibration=self.calibration_manager,
                    log=self.log
                )
                self.serialpad_timer.start()
                self.log(f"[✓] SerialPad connected on {serial}")
                self._write_serial_to_row(row, serial)
                cfg = self._prefs.get("serialpad")
                if cfg:
                    try:
                        self._apply_serialpad_config(cfg)
                    except Exception:
                        pass

                if row is not None:
                    self.config_page.set_status(row, True)

                    try: self._hydrate_serialpad_from_live()
                    except Exception: pass
            except Exception as e:
                self.log(f"[✗] SerialPad connect failed: {e}")
                if row is not None:
                    self.config_page.set_status(row, False)
                
    def _update_dataview_from_devices(self):
        if not getattr(self, "_polling_enabled", False):
            return
        if self.stack.currentWidget() is self.config_page:
            return

        payload = {}
        def add(dev, p_key, v_key):
            try:
                d = getattr(dev, "driver", dev)
                gp = getattr(d, "get_cached_pressure", None)
                gv = getattr(d, "get_cached_volume", None)
                p = gp and gp(0.9)
                v = gv and gv(0.9)
                if p is not None: payload[p_key] = float(p)
                if v is not None: payload[v_key] = float(v)
            except Exception:
                pass

        add(self.cell_pressure_controller, "Cell Pressure", "Cell Volume")
        add(self.back_pressure_controller, "Back Pressure", "Back Volume")
        if payload:
            self.data_view_page.set_values(payload)



    def _start_pressure_polling(self):
        # start the timer only once; safe to call repeatedly
        if hasattr(self, "pressure_timer") and not self.pressure_timer.isActive():
            self.pressure_timer.start()
            self.log("[i] Pressure polling started.")

    def _prime_pressure_cards(self):
        payload = {}

        try:
            c = self.cell_pressure_controller
            c_backend = getattr(c, "driver", None) if c else None
            if c_backend and hasattr(c_backend, "read_pressure_kpa"):
                v = c_backend.read_pressure_kpa()
                if v is not None:
                    payload["Cell Pressure"] = float(v)
            if c_backend and hasattr(c_backend, "read_volume_mm3"):
                vv = c_backend.read_volume_mm3()
                if vv is not None:
                    payload["Cell Volume"] = float(vv)
        except Exception:
            pass

        try:
            b = self.back_pressure_controller
            b_backend = getattr(b, "driver", None) if b else None
            if b_backend and hasattr(b_backend, "read_pressure_kpa"):
                v = b_backend.read_pressure_kpa()
                if v is not None:
                    payload["Back Pressure"] = float(v)
            if b_backend and hasattr(b_backend, "read_volume_mm3"):
                vv = b_backend.read_volume_mm3()
                if vv is not None:
                    payload["Back Volume"] = float(vv)
        except Exception:
            pass

        if payload:
            self.data_view_page.set_values(payload)


    # GUI_run.py (inside MainWindow)
    def _write_serial_to_row(self, row: int, serial: str):
        """Update the Serial cell in-place and the backing model, without rebuilding the table."""
        try:
            tbl = self.config_page.table
            if row is None or row < 0 or row >= tbl.rowCount():
                return
            w = tbl.cellWidget(row, 3)  # Serial column widget
            if hasattr(w, "findText"):  # QComboBox
                idx = w.findText(serial)
                if idx < 0:
                    w.addItem(serial)
                    idx = w.findText(serial)
                w.setCurrentIndex(idx)
            elif hasattr(w, "setText"):  # QLineEdit
                w.setText(serial)
            else:
                from PyQt5.QtWidgets import QTableWidgetItem
                tbl.setItem(row, 3, QTableWidgetItem(serial))

            # Update the page's model directly (no load_config)
            if 0 <= row < len(self.config_page._devices):
                self.config_page._devices[row]["serial"] = serial
        except Exception as e:
            self.log(f"[!] Failed to set serial: {e}")

    def connect_loadframe_ftdi(self):
        serial = self._pick_ftdi_serial("Connect Load Frame")
        if not serial: return
        if self.lf_controller.connect(serial):
            self.log(f"[✓] Load frame connected: {serial}")
            self.manual_page.set_axial_enabled(True)
        else:
            self.log("[✗] Load frame connection failed.")

    def connect_pressure_ftdi(self, which="cell"):
        serial = self._pick_ftdi_serial(f"Connect {which.title()} Pressure")
        if not serial: return
        ctrl = self.cell_pressure_controller if which == "cell" else self.back_pressure_controller
        if ctrl.connect(serial):
            self.log(f"[✓] {which.title()} pressure controller connected: {serial}")
            (self.manual_page.set_cell_enabled if which == "cell" else self.manual_page.set_back_enabled)(True)
        else:
            self.log(f"[✗] {which.title()} pressure controller connection failed.")


    def connect_serial_pad(self):
        # TODO: replace this with a real port list if you have one
        port, ok = QInputDialog.getText(self, "Connect SerialPad", "COM port (e.g., COM5):")
        if not ok or not port: return
        try:
            self.serial_pad = SerialPadReader(
                port=serial,
                calibration=self.calibration_manager,   # so read_channels() can calibrate each channel
                log=self.log
            )
            self.serialpad_timer.start()
            self.log(f"[✓] SerialPad connected on {port}")
        except Exception as e:
            self.log(f"[✗] SerialPad connect failed: {e}")

    def _is_connected(self, dev) -> bool:
        if not dev:
            return False
        for attr in ("is_ready", "is_connected", "isConnected", "connected"):
            val = getattr(dev, attr, None)
            try:
                return bool(val() if callable(val) else val)
            except Exception:
                pass
        return False  # fallback: treat existing object as connected


    def _is_ready_obj(self, dev) -> bool:
        try:
            if not dev:
                return False
            if hasattr(dev, "is_ready"):
                return bool(dev.is_ready())
            if hasattr(dev, "connected"):
                v = dev.connected
                return bool(v() if callable(v) else v)
        except Exception:
            pass
        return False

    # --- Axial (load frame) ---
    def _set_axial_position(self, mm: float):
        dev = self.lf_controller
        if not dev: return
        for name in ("send_displacement", "set_axial_position", "set_target_position", "move_to"):
            if hasattr(dev, name):
                getattr(dev, name)(mm)
                return
        self.log("[✗] Load frame does not implement a position method.")

    def _set_axial_velocity(self, mm_min: float):
        dev = self.lf_controller
        if not dev: return
        for name in ("send_velocity", "set_axial_velocity", "set_target_velocity", "jog"):
            if hasattr(dev, name):
                getattr(dev, name)(mm_min)
                return
        self.log("[✗] Load frame does not implement a velocity/jog method.")

    def _stop_axial(self):
        dev = self.lf_controller
        if not dev: return
        for name in ("stop_motion", "stop_axial", "stop", "halt"):
            if hasattr(dev, name):
                getattr(dev, name)()
                return
        self.log("[✗] Load frame does not implement a stop method.")

    # --- Cell pressure ---
    def _set_cell_pressure(self, kpa: float):
        dev = self.cell_pressure_controller
        if not dev:
            return
        backend = getattr(dev, "driver", None)
        if backend and hasattr(backend, "send_pressure"):
            backend.send_pressure(kpa)
            return
        for name in ("send_pressure", "set_pressure", "set_target_pressure", "set_cell_pressure"):
            if hasattr(dev, name):
                getattr(dev, name)(kpa)
                return
        self.log("[✗] Cell pressure controller does not implement a set/send method.")

    # --- Back pressure ---
    def _set_back_pressure(self, kpa: float):
        dev = self.back_pressure_controller
        if not dev:
            return
        backend = getattr(dev, "driver", None)
        if backend and hasattr(backend, "send_pressure"):
            backend.send_pressure(kpa)
            return
        for name in ("send_pressure", "set_pressure", "set_target_pressure", "set_back_pressure"):
            if hasattr(dev, name):
                getattr(dev, name)(kpa)
                return
        self.log("[✗] Back pressure controller does not implement a set/send method.")


    def _stop_cell_pressure(self):
        dev = self.cell_pressure_controller
        if not dev: return
        for name in ("stop", "stop_pressure", "abort"):
            if hasattr(dev, name):
                getattr(dev, name)()
                return
        self.log("[✗] Cell pressure controller does not implement a stop method.")

    def _stop_back_pressure(self):
        dev = self.back_pressure_controller
        if not dev: return
        for name in ("stop", "stop_pressure", "abort"):
            if hasattr(dev, name):
                getattr(dev, name)()
                return
        self.log("[✗] Back pressure controller does not implement a stop method.")


    # --- MainWindow helpers (put inside the class) -------------------------------
    def _list_devices(self):
        """Return FTDI serials (D2XX) for dropdown."""
        try:
            devs = ftd2xx.listDevices() or []
            return [(d.decode() if isinstance(d, bytes) else str(d)) for d in devs]
        except Exception:
            return []

    def _current_device_name(self):
        """Prefer saved default; otherwise a connected controller's serial if available."""
        # 1) saved default (persisted below)
        try:
            return self._prefs.get("default_ftdi_serial", "")
        except Exception:
            pass

        # 2) fall back to any connected backend’s serial/id
        for ctrl in (self.cell_pressure_controller, self.back_pressure_controller, self.lf_controller):
            drv = getattr(ctrl, "driver", None)
            for key in ("serial", "serial_number", "device_serial"):
                if drv is not None and hasattr(drv, key):
                    try:
                        val = getattr(drv, key)
                        return val() if callable(val) else str(val)
                    except Exception:
                        pass
        return ""
    
    def _apply_pressure_limits(self, lo: float, hi: float):
        old = (self._prefs.get("pressure_limits") or {"min": -50.0, "max": 3050.0})
        self._prefs["pressure_limits"] = {"min": float(lo), "max": float(hi)}
        try: self._save_prefs()
        except Exception: pass

        # Push to both controllers (keep your existing code here)
        for ctrl in (self.cell_pressure_controller, self.back_pressure_controller):
            try:
                if ctrl and hasattr(ctrl, "set_command_limits"):
                    ctrl.set_command_limits(lo, hi)
            except Exception as e:
                self.log(f"[!] Failed to apply limits to a controller: {e}")

        # Popup summary
        msg = (
            "Pressure command limits updated.\n\n"
            f"Minimum:  {old['min']:.1f} → {lo:.1f} kPa\n"
            f"Maximum:  {old['max']:.1f} → {hi:.1f} kPa"
        )
        self._info("Pressure Limits Applied", msg)
        return True



    def _select_device(self, name: str):
        """Save as default FTDI serial; optionally auto-connect later."""
        if not name:
            return False
        # simple prefs dict
        self._prefs = getattr(self, "_prefs", {})
        self._prefs["default_ftdi_serial"] = name
        try:
            self._save_prefs()
        except Exception:
            pass
        self.log(f"[✓] Saved default FTDI serial: {name}")
        return True


    def _check_devices(self):
        """
        Minimal connection check: only ensure each required device object exists.
        Skips StationConfig 'connected' flags and .is_ready checks.
        """
        problems = []

        required = {
            "Load Frame":               ("Load Frame",               self.load_frame),
            "Cell Pressure Controller": ("Cell Pressure Controller", self.cell_pressure_controller),
            "Back Pressure Controller": ("Back Pressure Controller", self.back_pressure_controller),
            "Serial Pad":               self.serial_pad,
        }

        for label, obj in required.items():
            if obj is None:
                problems.append(f"{label} not initialized")

        if problems:
            return (False, " • " + "\n • ".join(problems))
        return (True, "")

    
    def _safe(self, fn, ctx: str):
        try:
            return fn()
        except Exception as e:
            self.log(f"[dbg] {ctx} error: {e}")
            return None



    def _poll_serialpad(self):
        def _do():
            if not self.serial_pad:
                return
            vals = self.serial_pad.read_channels()
            if not vals or len(vals) < 8:
                return

            # role → channel index (default identity if no config)
            assign = {}
            try:
                if hasattr(self.serial_pad, "get_assignments"):
                    assign = self.serial_pad.get_assignments() or {}
            except Exception:
                assign = {}
            # invert to role -> ch
            role_to_ch = { (v or {}).get("role"): ch for ch, v in assign.items() if isinstance(v, dict) }

            # canonical dashboard order (keeps your existing cards stable)
            roles = ["Axial Load","Pore Pressure","Axial Displacement",
                     "Local Axial 1","Local Axial 2","Local Radial","Unused 1","Unused 2"]

            payload = {}
            for role in roles:
                ch = role_to_ch.get(role, roles.index(role))  # fallback: identity mapping
                value = vals[ch] if 0 <= ch < len(vals) else None
                payload[role] = ("—" if value is None else value)

            self.data_view_page.set_values(payload)
        self._safe(_do, "serialpad poll")


    def handle_live_reading(self, reading):
        enriched = self._augment_with_pressures(reading)
        self.view_page.shared_data = enriched
        self.view_page._dirty = True   # <- no immediate update_plot()

    def _augment_with_pressures(self, reading: dict) -> dict:
        out = dict(reading or {})

        def _cached(dev, age=0.9):
            try:
                d = getattr(dev, "driver", dev)
                f = getattr(d, "get_cached_pressure", None)
                return float(f(age)) if callable(f) else None
            except Exception:
                return None

        cell = _cached(self.cell_pressure_controller)
        back = _cached(self.back_pressure_controller)

        if cell is not None:
            out["cell_pressure_kpa"] = cell
        if back is not None:
            out["back_pressure_kpa"] = back
        return out

    def goto_setup(self, clear: bool = False):
        # 1) show the setup page
        shown = False
        for attr in ("main_stack", "stack", "pages", "stacked_widget"):
            w = getattr(self, attr, None)
            if w and hasattr(self, "setup_page"):
                try:
                    w.setCurrentWidget(self.setup_page)
                    shown = True
                    break
                except Exception:
                    pass
        if not shown and hasattr(self, "setup_page"):
            # fallback if you're using setCentralWidget-style pages
            self.setCentralWidget(self.setup_page)

        # 2) update the left nav highlight if you have one
        try:
            # common patterns; keep whichever matches your app
            self.sidebar.setCurrentRow(self.NAV_INDEXES["Test Set Up"])
        except Exception:
            try:
                self.nav_list.setCurrentRow(self.NAV_INDEXES["Test Set Up"])
            except Exception:
                pass

        # 3) optionally clear/reset the form
        if clear and hasattr(self.setup_page, "reset_form"):
            try:
                self.setup_page.reset_form()
            except Exception:
                pass

    def _on_back_to_setup(self):
        # leave devices connected; just flip UI back
        try:
            self.view_page.reset_for_new_test(keep_last_config=True)
        except Exception:
            pass
        self.goto_setup(clear=False)

    def _on_run_another_test(self):
        # same as back_to_setup, but usually you want a fresh form
        try:
            self.view_page.reset_for_new_test(keep_last_config=False)
        except Exception:
            pass
        self.goto_setup(clear=True)

    def _prefill_stage_pressures(self):
        """Prefill current cell/back pressures into stages using cache/live reads or prompt."""
        if getattr(self, "test_manager", None):
            # already have a running/paused test; don't prompt
            return True

        # --- Try to auto-read current pressures once up-front
        def _current_kpa(ctrl):
            """Return latest kPa from controller or None. Unwrap shim, prefer cache."""
            if not ctrl:
                return None
            dev = getattr(ctrl, "driver", ctrl)
            # 1) cached (fast, non-blocking)
            try:
                if hasattr(dev, "get_cached_pressure"):
                    v = dev.get_cached_pressure(0.6)  # treat cache ≤0.6 s old as fresh
                    if v is not None:
                        return float(v)
            except Exception:
                pass
            # 2) short live read
            try:
                fn = getattr(dev, "read_pressure_kpa", None)
                if callable(fn):
                    v = fn(timeout_s=0.25)
                    if v is not None:
                        return float(v)
            except Exception:
                pass
            return None

        cell_now = _current_kpa(self.cell_pressure_controller)
        back_now = _current_kpa(self.back_pressure_controller)

        # --- Prefill stages; only prompt if still missing
        for stage_data in getattr(self.setup_page, "stage_data_list", []):
            if stage_data.stage_type in ("Saturation", "Consolidation", "Shear"):
                if getattr(stage_data, "current_cell_pressure", None) is None:
                    if cell_now is not None:
                        stage_data.current_cell_pressure = cell_now
                    else:
                        val, ok = QInputDialog.getDouble(
                            None, "Current Cell Pressure",
                            "Enter current cell pressure (kPa):",
                            0, 0, 2000, 1
                        )
                        if not ok:
                            self.log("[✗] Test cancelled by user.")
                            return False
                        stage_data.current_cell_pressure = val

                if getattr(stage_data, "current_back_pressure", None) is None:
                    if back_now is not None:
                        stage_data.current_back_pressure = back_now
                    else:
                        val, ok = QInputDialog.getDouble(
                            None, "Current Back Pressure",
                            "Enter current back pressure (kPa):",
                            0, 0, 2000, 1
                        )
                        if not ok:
                            self.log("[✗] Test cancelled by user.")
                            return False
                        stage_data.current_back_pressure = val
        return True


    def start_test(self, _=None):
        #print("[DEBUG] MainWindow.start_test() called")

        if getattr(self, "_resuming_existing_stage", False):
            return  # skip prefill when resuming

        # --- guards & stage prefill
        if not self._prefill_stage_pressures():
            return

        self.view_page.start_time = time.time()
        self.view_page.load_stages(self.setup_page.stage_data_list)

        if not (self.lf_controller and self.cell_pressure_controller and self.back_pressure_controller and self.serial_pad):
            self.log("[✗] All devices must be connected before starting a test.")
            return

        # --- Get details from earlier dialog (Go to Test View). If missing, prompt now.
        # --- Get details from earlier dialog (Go to Test View)
        details = getattr(self, "_pending_test_details", None)
        if not details:
            self.log("[✗] Missing test details (expected from setup page).")
            return


        # always unpack here
        sample_id, sampling_period_s, height_mm, diameter_mm, docked = details

        test_config = {
            "stages": self.setup_page.stage_data_list,
            "sample_id": sample_id,
            "sampling_period_s": sampling_period_s,
            "sample_height_mm": height_mm,
            "sample_diameter_mm": diameter_mm,
            "is_docked": docked,
        }

        # ensure attrs exist for TestViewPage calcs
        self.view_page._h0_mm = height_mm
        self.view_page._d0_mm = diameter_mm



        # --- instantiate manager
        self.test_manager = TriaxialTestManager(
            lf_controller=self.lf_controller,
            cell_pressure_controller=self.cell_pressure_controller,
            back_pressure_controller=self.back_pressure_controller,
            serial_pad=self.serial_pad,
            test_config=test_config,
            log=self.log
        )
        self.test_manager.view_page = self.view_page
        self.test_manager.stop_requested = False   # <-- add this

        # manager → mainwindow
        self.test_manager.stage_changed.connect(lambda name: self.log(f"[Stage] {name}"))
        self.test_manager.reading_updated.connect(self.view_page.update_plot)
        self.test_manager.test_finished.connect(lambda: self.log("[✓] Test finished!"))
        self.test_manager.test_finished.connect(lambda: self.pressure_timer.stop())
        self.test_manager.test_finished.connect(self._on_test_finished)  # keep

        # manager → view (new-safe)
        # After rebuilding or modifying test_manager:
        if hasattr(self.test_manager, "stage_completed"):
            try:
                # avoid duplicate connects
                self.test_manager.stage_completed.disconnect()
            except Exception:
                pass
            self.test_manager.stage_completed.connect(lambda _: self.view_page.handle_stage_complete())

        if hasattr(self.view_page, "set_current_stage"):
            self.test_manager.stage_changed.connect(self.view_page.set_current_stage)

        # post-stage decision (view → manager) (new-safe)
        if hasattr(self.view_page, "next_stage_requested"):
            self.view_page.next_stage_requested.connect(self.test_manager.next_stage)
        if hasattr(self.view_page, "end_test_requested"):
            self.view_page.end_test_requested.connect(self.test_manager.finish)

        # view hook
        if hasattr(self.view_page, "on_test_started"):
            self.view_page.on_test_started()

        # show the Test View page
        self.stack.setCurrentWidget(self.view_page)
        self.sidebar.setCurrentRow(3)

        # kick off polling & plotting
        if not self.pressure_timer.isActive():
            self.pressure_timer.start()
        self.view_page.add_graph()  # start with one graph; users can add/remove
        self.test_manager.start()


    def _on_test_finished(self):
        # Build a lightweight summary
        try:
            stages = len(getattr(self.test_manager, "stages", []) or [])
        except Exception:
            stages = 0

        # Duration
        now = time.time()
        start_ts = getattr(self.view_page, "start_time", None)
        dur_s = (now - start_ts) if start_ts else 0
        dur_s = max(0, int(dur_s))
        h, rem = divmod(dur_s, 3600)
        m, _ = divmod(rem, 60)
        duration = f"{h}h {m}m" if h else f"{m}m"

        # Datapoints & filepath (best-effort if you don’t have a logger yet)
        datapoints = 0
        try:
            datapoints = int(self.logger.total_rows_written())
        except Exception:
            pass
        filepath = "Not saved yet"
        try:
            p = getattr(self.logger, "last_path", None)
            if p:
                filepath = str(p)
        except Exception:
            pass

        summary = {
            "stages": stages,
            "duration": duration,
            "datapoints": datapoints,
            "filepath": filepath,
            "subtitle": "All stages finished successfully."
        }
        # Show the completion card
        if hasattr(self.view_page, "show_completion_summary"):
            self.view_page.show_completion_summary(summary)


    def on_edit_stage_requested(self):
        tm = self.test_manager
        if not tm or not tm.stages:
            return

        # --- Dialog container ---
        dlg = QDialog(self)
        dlg.setWindowTitle("Manage Stages")
        layout = QVBoxLayout(dlg)

        # --- Stage selector + Add/Remove ---
        row = QHBoxLayout()
        self.stage_selector = QComboBox()
        for s in tm.stages:
            self.stage_selector.addItem(f"{s.name} ({s.stage_type})", s.stage_id)
        row.addWidget(QLabel("Select Stage"))
        row.addWidget(self.stage_selector)

        btn_add = QPushButton("Add After")
        btn_remove = QPushButton("Remove")
        row.addWidget(btn_add)
        row.addWidget(btn_remove)
        layout.addLayout(row)

        self.stage_selector.currentIndexChanged.connect(
            lambda _: self._populate_stage_fields(self.stage_selector.currentData())
        )
        btn_add.clicked.connect(self._add_stage_from_editor)       # NEW
        btn_remove.clicked.connect(self._remove_stage_from_editor) # NEW


        # --- Type dropdown ---
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "Saturation",
            "Consolidation",
            "Shear",
            "B Check",
            "Automated Docking",
        ])
        self.type_combo.currentTextChanged.connect(self._update_fields)
        layout.addWidget(QLabel("Type"))
        layout.addWidget(self.type_combo)

        # --- Dynamic form area ---
        self.form_layout = QFormLayout()
        self.dynamic_fields = QWidget()
        self.dynamic_layout = QFormLayout(self.dynamic_fields)
        self.form_layout.addRow(self.dynamic_fields)
        layout.addLayout(self.form_layout)

        # --- Buttons ---
        btns = QHBoxLayout()
        save_btn = QPushButton("Save")
        next_btn = QPushButton("Go to Next Stage")   # NEW
        cancel_btn = QPushButton("Cancel")
        btns.addWidget(save_btn)
        btns.addWidget(next_btn)                     # NEW
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        save_btn.clicked.connect(lambda: self._save_stage())         # UPDATED (no dlg)
        next_btn.clicked.connect(lambda: self._go_next_from_editor(dlg))  # NEW
        cancel_btn.clicked.connect(dlg.reject)

                # At the end of on_edit_stage_requested, after you’ve updated/added stages:
        if hasattr(self.test_manager, "stage_completed"):
            try:
                self.test_manager.stage_completed.disconnect()
            except Exception:
                pass
            self.test_manager.stage_completed.connect(
                lambda _: self.view_page.handle_stage_complete()
            )

        # Initially load first stage
        if tm.stages:
            self._populate_stage_fields(tm.stages[0].stage_id)

        dlg.exec_()

    def _add_stage_from_editor(self):
        tm = self.test_manager
        if not tm:
            return

        from test_set_up_page import StageData  # ensure correct import

        # Use current type, but generate a fresh unique name
        stage_type = self.type_combo.currentText() if hasattr(self, "type_combo") else "Saturation"
        new_name = self._unique_stage_name("Stage")

        # Pull numbers only if those widgets exist; otherwise default to 0
        def _num(key, default=0.0):
            w = getattr(self, "_active_fields", {}).get(key)
            try:
                return float(w.value()) if w else default
            except Exception:
                return default

        new_stage = StageData(
            name=new_name,
            stage_type=stage_type,
            cell_pressure=_num("cell_pressure", 0.0),
            back_pressure=_num("back_pressure", 0.0),
            duration=_num("duration", 0.0),
            axial_velocity=_num("axial_velocity", 0.0),
            load_threshold=_num("load_threshold", 0.0),
            safety_load_kN=_num("safety_load_kN", 9999.0),
        )

        # Insert right after the currently selected stage
        sel_sid = self.stage_selector.currentData()
        cur_idx = next((i for i, s in enumerate(tm.stages) if s.stage_id == sel_sid), len(tm.stages) - 1)
        insert_at = min(cur_idx + 1, len(tm.stages))
        tm.add_stage(new_stage, index=insert_at)

        # Update dropdown and focus the new stage
        self.stage_selector.insertItem(insert_at, f"{new_stage.name} ({new_stage.stage_type})", new_stage.stage_id)
        self.stage_selector.setCurrentIndex(insert_at)
        self._populate_stage_fields(new_stage.stage_id)

        QMessageBox.information(self, "Added", "New stage inserted.")



    def _remove_stage_from_editor(self):
        """Remove the currently selected stage (with safety checks)."""
        tm = self.test_manager
        if not tm or not tm.stages:
            return

        sel_idx = self.stage_selector.currentIndex()
        sel_sid = self.stage_selector.currentData()
        if sel_sid is None:
            return

        # Prevent removing the running stage if a thread is still active
        running_idx = getattr(tm, "current_stage_index", -1)
        is_current = sel_sid == getattr(tm.stages[running_idx], "stage_id", None) if 0 <= running_idx < len(tm.stages) else False
        thread_running = bool(getattr(tm, "thread", None) and hasattr(tm.thread, "isRunning") and tm.thread.isRunning())

        if is_current and thread_running:
            QMessageBox.warning(self, "Blocked", "Stop the current stage before removing it.")
            return

        # Confirm
        resp = QMessageBox.question(self, "Remove Stage", "Are you sure you want to remove this stage?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes:
            return

        # Remove in manager
        if not tm.remove_stage(sel_sid):
            QMessageBox.warning(self, "Error", "Could not remove stage.")
            return

        # Update selector UI
        self.stage_selector.removeItem(sel_idx)

        if self.stage_selector.count() == 0:
            QMessageBox.information(self, "Removed", "Stage removed. No stages remain.")
            return

        # Move selection to a sensible neighbor and reload fields
        new_sel = max(0, sel_idx - 1)
        self.stage_selector.setCurrentIndex(new_sel)
        self._populate_stage_fields(self.stage_selector.currentData())
        QMessageBox.information(self, "Removed", "Stage removed.")

    def _info(self, title: str, text: str):
        # Centralized informational popup
        try:
            QMessageBox.information(self, title, text)
        except Exception:
            # Safe fallback: still log if UI cannot show a modal
            self.log(f"[i] {title}: {text}")

    def _unique_stage_name(self, base="Stage"):
        tm = self.test_manager
        existing = {s.name for s in (tm.stages if tm else [])}
        i = 1
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"

    def _refresh_stage_selector_item(self, stage):
        # Update the visible label in the dropdown to match the StageData
        if not hasattr(self, "stage_selector"):
            return
        idx = self.stage_selector.findData(stage.stage_id)
        if idx >= 0:
            self.stage_selector.setItemText(idx, f"{stage.name} ({stage.stage_type})")


    def _populate_stage_fields(self, stage_id):
        tm = self.test_manager
        if not tm:
            return
        stage = next((s for s in tm.stages if s.stage_id == stage_id), None)
        if not stage:
            return

        # Set type, rebuild fields for that type
        self.type_combo.setCurrentText(stage.stage_type)
        self._update_fields(stage.stage_type)

        # Helper to set a field if it exists and is alive
        def set_if(key, val):
            w = self._active_fields.get(key)
            if not w or isdeleted(w):
                return
            if isinstance(w, QDoubleSpinBox):
                w.setValue(float(val))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(val))
            elif isinstance(w, QLineEdit):
                w.setText(str(val))

        # Populate based on your StageData shape
        set_if("name", stage.name)
        set_if("cell_pressure", stage.cell_pressure)
        set_if("back_pressure", stage.back_pressure)
        set_if("duration", stage.duration)
        set_if("axial_velocity", stage.axial_velocity)
        set_if("load_threshold", stage.load_threshold)
        set_if("safety_load_kN", stage.safety_load_kN)


    def _update_fields(self, stage_type: str):
        # Clear previous UI
        while self.dynamic_layout.count():
            item = self.dynamic_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Track only currently alive widgets
        self._active_fields = {}

        def add_row(label, widget, key):
            self.dynamic_layout.addRow(label, widget)
            self._active_fields[key] = widget

        # Name (always)
        name = QLineEdit()
        add_row("Name", name, "name")

        # Stage-specific widgets
        if stage_type == "Saturation":
            cp = QDoubleSpinBox(); cp.setRange(0, 2000); cp.setSuffix(" kPa")
            bp = QDoubleSpinBox(); bp.setRange(0, 2000); bp.setSuffix(" kPa")
            dur = QDoubleSpinBox(); dur.setRange(0, 1e6); dur.setSuffix(" min")
            add_row("Cell Pressure", cp, "cell_pressure")
            add_row("Back Pressure", bp, "back_pressure")
            add_row("Duration", dur, "duration")

        elif stage_type == "Consolidation":
            cp = QDoubleSpinBox(); cp.setRange(0, 2000); cp.setSuffix(" kPa")
            bp = QDoubleSpinBox(); bp.setRange(0, 2000); bp.setSuffix(" kPa")
            add_row("Cell Pressure", cp, "cell_pressure")
            add_row("Back Pressure", bp, "back_pressure")

        elif stage_type == "Shear":
            vel = QDoubleSpinBox(); vel.setRange(0, 100); vel.setSuffix(" mm/min")
            sfty = QDoubleSpinBox(); sfty.setRange(0, 1000); sfty.setSuffix(" kN")
            add_row("Axial Velocity", vel, "axial_velocity")
            add_row("Safety Threshold", sfty, "safety_load_kN")

        elif stage_type == "B Check":
            cp = QDoubleSpinBox(); cp.setRange(0, 2000); cp.setSuffix(" kPa")
            dur = QDoubleSpinBox(); dur.setRange(0, 1e6); dur.setSuffix(" min")
            add_row("Cell Pressure", cp, "cell_pressure")
            add_row("Duration", dur, "duration")

        elif stage_type == "Automated Docking":
            vel = QDoubleSpinBox(); vel.setRange(0, 100); vel.setSuffix(" mm/min")
            th  = QDoubleSpinBox(); th.setRange(0, 1000); th.setSuffix(" kN")
            add_row("Axial Velocity", vel, "axial_velocity")
            add_row("Load Threshold", th, "load_threshold")

    def _save_stage(self):
        tm = self.test_manager
        if not tm:
            return

        stage_id = self.stage_selector.currentData()
        stage = next((s for s in tm.stages if s.stage_id == stage_id), None)
        if not stage:
            return

        def get_num(key, default=0.0):
            w = getattr(self, "_active_fields", {}).get(key)
            if not w or isdeleted(w) or not isinstance(w, QDoubleSpinBox):
                return default
            return float(w.value())

        def get_text(key, default=""):
            w = getattr(self, "_active_fields", {}).get(key)
            if not w or isdeleted(w) or not isinstance(w, QLineEdit):
                return default
            return w.text().strip()

        def get_bool(key, default=False):
            w = getattr(self, "_active_fields", {}).get(key)
            if not w or isdeleted(w) or not isinstance(w, QCheckBox):
                return default
            return bool(w.isChecked())

        # Write back
        new_name = get_text("name", stage.name) or stage.name
        stage.stage_type = self.type_combo.currentText()

        if "cell_pressure"  in self._active_fields: stage.cell_pressure   = get_num("cell_pressure",  stage.cell_pressure)
        if "back_pressure"  in self._active_fields: stage.back_pressure   = get_num("back_pressure",  stage.back_pressure)
        if "duration"       in self._active_fields: stage.duration        = get_num("duration",       stage.duration)
        if "axial_velocity" in self._active_fields: stage.axial_velocity  = get_num("axial_velocity", stage.axial_velocity)
        if "load_threshold" in self._active_fields: stage.load_threshold  = get_num("load_threshold", stage.load_threshold)
        if "safety_load_kN" in self._active_fields: stage.safety_load_kN  = get_num("safety_load_kN", stage.safety_load_kN)
        # if "dock"         in self._active_fields: stage.dock           = get_bool("dock", stage.dock)
        # if "hold"         in self._active_fields: stage.hold           = get_bool("hold", stage.hold)

        # Update name last (after potential validation)
        stage.name = new_name

        # 🔁 Refresh the combo label so you can see the change immediately
        self._refresh_stage_selector_item(stage)

        QMessageBox.information(self, "Saved", "Stage configured.")

    def _go_next_from_editor(self, dlg):
        # Save first, then close and advance
        self._save_stage()
        try:
            dlg.accept()
        except Exception:
            pass
        tm = self.test_manager
        if tm and hasattr(tm, "next_stage"):
            tm.next_stage()


    def advance_to_next_stage(self):
        if self.test_manager:
            self.test_manager.next_stage()

    def stop_current_stage(self):
        if self.test_manager:
            self.test_manager.stop_stage()

    def _pressure_tick(self):
        if not getattr(self, "_polling_enabled", False):
            return

        def _cached_pair(dev, p_key, v_key):
            try:
                d = getattr(dev, "driver", dev)
                gp = getattr(d, "get_cached_pressure", None)
                gv = getattr(d, "get_cached_volume", None)
                p = float(gp(0.9)) if callable(gp) else None
                v = float(gv(0.9)) if callable(gv) else None
                return {k: v for k, v in [(p_key, p), (v_key, v)] if v is not None}
            except Exception:
                return {}

        update_dataview = {}
        update_dataview.update(_cached_pair(self.cell_pressure_controller, "Cell Pressure", "Cell Volume"))
        update_dataview.update(_cached_pair(self.back_pressure_controller, "Back Pressure", "Back Volume"))
        if update_dataview:
            self.data_view_page.set_values(update_dataview)

    def on_next_stage(self):
        # Save graphs first
        self.view_page.save_graphs()

        # Move to next stage
        self.test_manager.next_stage()

        # Reinitialize plot cards so they immediately accept data
        self.view_page.reset_for_new_stage()


    def log(self, message):
        # keep stdout for dev logs
        try:
            print(message)
        except Exception:
            pass

        # Only show a modal for explicit GUI errors you raise on purpose
        if isinstance(message, str) and message.startswith("[✗ GUI]"):
            QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Error", message))


if __name__ == "__main__":
    import traceback
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QApplication
    import ctypes, os, sys

    def resource_path(filename: str) -> str:
        return (os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(__file__)), filename))

    try:
        # Force a stable AppUserModelID so Windows uses your exe’s identity & icon
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SoilMate.2025")  # any stable string
        except Exception:
            pass  # non-Windows or older systems

        app = QApplication(sys.argv)

        icon_path = resource_path("SoilMateLogo.ico")
        print("Icon path:", icon_path, "exists?", os.path.exists(icon_path))
        ico = QIcon(icon_path)
        app.setWindowIcon(ico)

        window = MainWindow()
        window.setWindowIcon(ico)   # some shells require setting the window icon too
        window.show()
        sys.exit(app.exec())
    except Exception:
        print("Exception on startup:")
        traceback.print_exc()


