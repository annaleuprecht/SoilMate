import os
import csv

class CalibrationManager:
    def __init__(self, cal_dir="calibration_values"):
        self.calibrations = self.load_from_cal_files(cal_dir)

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
