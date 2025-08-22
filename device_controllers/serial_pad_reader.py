import serial
import time
import threading

class SerialPadReader:
    def __init__(self, port, calibration=None, log=print):
        self.ser = serial.Serial(
            port=port,
            baudrate=4800,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_TWO,
            timeout=1
        )
        self.calibration = calibration
        self._assignments = {}  # {ch: {"role": str, "sensor": str}}
        self._sensors = {}
        self.log = log
        self._lock = threading.Lock()

    def convert_adc_to_eng_units(self, adc_output, cal):
        return (((adc_output / cal["adc_range"]) * cal["full_scale_mv"]) * cal["sensitivity"]) + cal["soft_zero_offset"]

    def set_assignments(self, assignments: dict, sensors: dict = None):
        try:
            self._assignments = {int(k): (dict(v) if isinstance(v, dict) else {}) for k, v in (assignments or {}).items()}
        except Exception:
            self._assignments = {}
        if sensors is not None:
            self.set_sensors(sensors)

    def set_channel_assignments(self, assignments: dict):  # backwards-compat
        self.set_assignments(assignments, None)

    def set_sensors(self, sensors: dict):
        self._sensors = dict(sensors or {})

    def get_assignments(self) -> dict:
        return dict(self._assignments)

    # optional: apply simple scale/offset calibration per channel, if you’re returning raw volts
    def _apply_sensor_cal(self, ch: int, raw_value: float):
        try:
            sensor_name = (self._assignments.get(ch) or {}).get("sensor")
            sdef = self._sensors.get(sensor_name) or {}
            scale = float(sdef.get("scale", 1.0)); offset = float(sdef.get("offset", 0.0))
            return (raw_value * scale) + offset
        except Exception:
            return raw_value

   # --- add this helper if you want to read sensors back in the UI
    def get_sensors(self) -> dict:
        return dict(self._sensors)

    def read_channels(self):
        with self._lock:
            try:
                self.ser.reset_input_buffer()
                self.ser.write(b'SS\r\n')
                time.sleep(0.2)

                values = []
                for ch in range(8):
                    line = self.ser.readline().decode(errors="ignore").strip()
                    # robust int parse (handles "1234", "CH0:1234", "0 1234", etc.)
                    try:
                        tok = line.replace("CH", "").replace(":", " ").replace("=", " ").split()
                        adc_val = int(tok[-1])
                    except Exception:
                        self.log(f"[!] Channel {ch} read error: invalid int from line = {line!r}")
                        values.append(None)
                        continue

                    # 1) ADC -> engineering units via .cal (if available)
                    eng_val = None
                    try:
                        if self.calibration is not None:
                            cal = self.calibration.get_calibration(ch)
                            eng_val = self.convert_adc_to_eng_units(adc_val, cal)
                    except Exception as e:
                        self.log(f"[!] Channel {ch} calibration error: {e}")

                    if eng_val is None:
                        # fallback to raw ADC if no calibration; still usable with sensor scale/offset
                        eng_val = float(adc_val)

                    # 2) Apply sensor mapping scale/offset (from Device Settings)
                    eng_val = self._apply_sensor_cal(ch, eng_val)

                    values.append(round(eng_val, 3))

                return values

            except Exception as e:
                self.log(f"[✗] Serial read failed: {e}")
                return [None] * 8


    def close(self):
        self.ser.close()
