import usb.core
import usb.util
import struct
import time

class LF50Mover:
    def __init__(self, device, log=print):
        if device is None:
            raise RuntimeError("LF50Mover requires a connected device.")
        self.dev = device
        self.log = log
        self.log("Using existing USB device handle.")
        self.should_stop = False

    def crc16_gds(self, data: bytes) -> bytes:
        crc = 0x4489
        for b in data:
            crc ^= (b << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return crc.to_bytes(2, 'big')

    def send_payload(self, payload):
        self.log(f"[TX] Writing: {payload.hex()}")
        self.dev.write(0x02, payload, timeout=100)

    def send_displacement(self, position_mm: float):
        self.should_stop = False  # Reset flag at start

        float_val = position_mm / 1000
        float_bytes = struct.pack('<f', float_val)
        self.log(f"[debug] {position_mm} mm → {float_val} m → bytes: {float_bytes.hex()}")
        payload_body = b'\x0b\x14' + float_bytes
        crc_val = self.crc16_gds(payload_body)
        payload_part_3 = b'\xff\xff' + b'gds' + bytes([len(payload_body)]) + payload_body + crc_val

        # First 2 pre-motion commands
        for payload in [
            bytes.fromhex("ffff676473060014010000001df5"),
            bytes.fromhex("ffff676473040e1401000f6e")
        ]:
            if self.should_stop:
                self.log("[!] Movement aborted before motion payload.")
                return
            self.send_payload(payload)
            time.sleep(0.05)

        # Main movement payload
        if self.should_stop:
            self.log("[!] Movement aborted before displacement.")
            return
        self.send_payload(payload_part_3)
        time.sleep(0.05)

        # Check again immediately after main motion
        if self.should_stop:
            self.log("[!] Movement aborted after displacement.")
            return

        # Remaining cleanup payloads
        for payload in [
            bytes.fromhex("ffff676473020114a02d"),
            bytes.fromhex("ffff6764730209142984"),
            bytes.fromhex("ffffffffffffffffffffffffffffffff")
        ]:
            if self.should_stop:
                self.log("[!] Aborted during cleanup sequence.")
                return
            self.send_payload(payload)
            time.sleep(0.05)

        self.log(f"[✓] Axial displacement command finished for {position_mm:.2f} mm.")

    def stop_motion(self):
        stop_payload = bytes.fromhex("ffff676473020116806f")
        self.send_payload(stop_payload)
        time.sleep(0.1)  # Give firmware time to “unlock” for stop
        self.send_payload(stop_payload)
        self.log("[→] Sent LF50 stop command (x2)")
        self.should_stop = True


