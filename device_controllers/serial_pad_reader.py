import serial
import time

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
        self.calibration = calibration  # should be a CalibrationManager
        self.log = log

    def convert_adc_to_eng_units(self, adc_output, cal):
        return (((adc_output / cal["adc_range"]) * cal["full_scale_mv"]) * cal["sensitivity"]) + cal["soft_zero_offset"]

    def read_channels(self):
        try:
            self.ser.reset_input_buffer()
            self.ser.write(b'SS\r\n')
            time.sleep(0.2)

            values = []
            for ch in range(8):
                line = self.ser.readline().decode(errors="ignore").strip()
                try:
                    adc_val = int(line)
                    cal = self.calibration.get_calibration(ch)
                    eng_val = self.convert_adc_to_eng_units(adc_val, cal)
                    values.append(round(eng_val, 3))
                except Exception as e:
                    self.log(f"[!] Channel {ch} read error: {e}")
                    values.append(None)

            return values

        except Exception as e:
            self.log(f"[✗] Serial read failed: {e}")
            return [None] * 8

    def close(self):
        self.ser.close()
