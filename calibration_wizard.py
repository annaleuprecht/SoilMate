import os
import csv
import json

class CalibrationManager:
    def __init__(self,
                 serialpad_dir="calibration/serial_pad",
                 pressure_json_path="calibration/stddpc/pressure_calibrations.json",
                 log=print):
        self.log = log
        self.serialpad_dir = serialpad_dir
        self.pressure_json_path = pressure_json_path

        self.calibrations = self.load_from_cal_files(self.serialpad_dir)
        self.pressure_calibrations = self.load_pressure_calibrations()

    def get_calibration(self, channel):
        return self.calibrations.get(str(channel), {
            "sensitivity": 1.0,
            "soft_zero_offset": 0.0,
            "full_scale_mv": 30.0,
            "adc_range": 32767,
            "units": "units",
            "label": f"Channel {channel}"
        })

    def load_from_cal_files(self, cal_dir):
        cal_files = sorted([f for f in os.listdir(cal_dir) if f.endswith(".cal")])
        channel_cals = {}
        for filename in cal_files:
            filepath = os.path.join(cal_dir, filename)
            cal = self.parse_cal_file(filepath)
            try:
                ch_number = int(filename.split('_')[0].replace("ch", ""))
            except:
                continue  # Skip file if naming doesn't match expected pattern

            label_part = os.path.splitext(filename)[0].split('_', 1)[-1].replace('_', ' ').title()
            cal["label"] = label_part
            channel_cals[str(ch_number)] = cal
            #print(f"[Debug] Loaded channel {ch_number} from '{filename}': {cal}")
        return channel_cals

    def parse_cal_file(self, file_path):
        calibration = {}
        with open(file_path, 'r', newline='') as f:
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

        calibration["adc_range"] = 32767
        if "units" not in calibration:
            calibration["units"] = "units"
        return calibration

    def load_pressure_calibrations(self):
        if not os.path.exists(self.pressure_json_path):
            os.makedirs(os.path.dirname(self.pressure_json_path), exist_ok=True)
            with open(self.pressure_json_path, 'w') as f:
                json.dump({}, f)
        with open(self.pressure_json_path, 'r') as f:
            return json.load(f)

    def get_pressure_calibration(self, serial):
        if serial not in self.pressure_calibrations:
            raise ValueError(f"No calibration values found for STDDPC {serial}")
        return self.pressure_calibrations[serial]

    def set_pressure_calibration(self, serial, values):
        self.pressure_calibrations[serial] = values
        self.save_pressure_calibrations()

    def save_pressure_calibrations(self):
        with open(self.pressure_json_path, 'w') as f:
            json.dump(self.pressure_calibrations, f, indent=4)

    def get_all_device_serials(self):
        serials = list(self.pressure_calibrations.keys())

        if self.serialpad_dir:
            try:
                for fname in os.listdir(self.serialpad_dir):
                    if fname.endswith(".cal"):
                        serial = os.path.splitext(fname)[0]
                        if serial not in serials:
                            serials.append(serial)
            except Exception as e:
                self.log(f"[!] Failed to scan serialpad cal dir: {e}")

        return sorted(serials)

    def add_pressure_calibration(self, serial, values):
        self.pressure_calibrations[serial] = values
        self.save_pressure_calibrations()

    def get_pressure_device_serials(self):
        return [k for k in self.get_all_device_serials() if k.startswith("GDS") or k.startswith("150")]

    def get_all_transducer_channels(self):
        return [k for k in self.get_all_device_serials() if k.startswith("ch")]

    def get_transducer_calibration(self, key):
        return self.get_calibration(key)

    def set_transducer_calibration(self, key, values):
        self.set_calibration(key, values)




