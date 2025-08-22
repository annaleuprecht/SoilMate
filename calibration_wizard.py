# --- top of calibration_wizard.py ---
import os, sys
from pathlib import Path
import csv
import json

def app_base() -> Path:
    # Where read-only bundled assets live when frozen
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Running from source: use this file's folder
    return Path(__file__).resolve().parent

def user_data_dir(appname: str = "SoilMate") -> Path:
    # A writable place for configs/calibration JSON
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / appname
    # macOS/Linux fallback
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / appname

def res_path(*parts) -> Path:
    return app_base().joinpath(*parts)

class CalibrationManager:
    def __init__(self,
                 serialpad_dir="calibration/serial_pad",
                 pressure_json_path="calibration/stddpc/pressure_calibrations.json",
                 log=print):
        self.log = log

        # Resolve serial pad calibration directory from bundled resources (read-only)
        if serialpad_dir == "calibration/serial_pad":
            self.serialpad_dir = res_path("calibration", "serial_pad")
        else:
            self.serialpad_dir = Path(serialpad_dir)

        # Store pressure calibrations in a WRITEABLE per-user location when frozen
        # (Bundled dir is read-only in --onefile; still works in dev.)
        default_json = (res_path("calibration", "stddpc", "pressure_calibrations.json"))
        if pressure_json_path == "calibration/stddpc/pressure_calibrations.json":
            cfg_dir = user_data_dir() / "calibration" / "stddpc"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            self.pressure_json_path = cfg_dir / "pressure_calibrations.json"
            # First-run: seed from bundled default if present and user file not created yet
            if self.pressure_json_path.exists() is False and default_json.exists():
                try:
                    self.pressure_json_path.write_text(default_json.read_text(encoding="utf-8"), encoding="utf-8")
                except Exception as e:
                    self.log(f"[!] Could not seed pressure calibrations: {e}")
        else:
            self.pressure_json_path = Path(pressure_json_path)

        self.calibrations = self.load_from_cal_files(self.serialpad_dir)
        self.pressure_calibrations = self.load_pressure_calibrations()

    def load_from_cal_files(self, cal_dir: Path):
        cal_dir = Path(cal_dir)
        if not cal_dir.exists():
            self.log(f"[!] Missing calibration folder: {cal_dir} — continuing with empty calibrations.")
            return {}
        cal_files = sorted(cal_dir.glob("*.cal"))
        channel_cals = {}
        for filepath in cal_files:
            cal = self.parse_cal_file(filepath)
            try:
                # Expect filenames like: ch1_axial_load.cal  or  ch2_whatever.cal
                ch_number = int(filepath.stem.split('_')[0].replace("ch", ""))
            except Exception:
                continue  # Skip file if naming doesn't match expected pattern

            label_part = filepath.stem.split('_', 1)[-1].replace('_', ' ').title()
            cal["label"] = label_part
            channel_cals[str(ch_number)] = cal
        return channel_cals

    def parse_cal_file(self, file_path: Path):
        calibration = {}
        file_path = Path(file_path)
        with file_path.open('r', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 4 or row[0] != "H":
                    continue
                key = row[1].strip().lower()
                value = row[3].strip()

                if key == "engunits":
                    calibration["units"] = value
                    continue

                try:
                    value = float(value)
                except ValueError:
                    continue

                if key == "sensitivity":
                    calibration["sensitivity"] = value
                elif key == "softzero":
                    calibration["soft_zero_offset"] = value
                elif key == "calculatedspan":
                    calibration["full_scale_mv"] = value

        calibration.setdefault("adc_range", 32767)
        calibration.setdefault("units", "units")
        return calibration

    def load_pressure_calibrations(self):
        p = self.pressure_json_path
        try:
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("{}", encoding="utf-8")
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            self.log(f"[!] Failed to read pressure calibrations at {p}: {e}")
            return {}

    def save_pressure_calibrations(self):
        p = self.pressure_json_path
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self.pressure_calibrations, indent=4), encoding="utf-8")
        except Exception as e:
            self.log(f"[!] Failed to write pressure calibrations to {p}: {e}")

    def get_all_device_serials(self):
        serials = list(self.pressure_calibrations.keys())
        if self.serialpad_dir:
            try:
                for filepath in Path(self.serialpad_dir).glob("*.cal"):
                    serial = filepath.stem
                    if serial not in serials:
                        serials.append(serial)
            except Exception as e:
                self.log(f"[!] Failed to scan serialpad cal dir: {e}")
        return sorted(serials)
