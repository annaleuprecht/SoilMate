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
        # Encode float
        float_bytes = struct.pack('<f', position_mm / 1000)
        payload_body = b'\x0b\x14' + float_bytes
        crc_val = self.crc16_gds(payload_body)
        payload_part_3 = b'\xff\xff' + b'gds' + bytes([len(payload_body)]) + payload_body + crc_val

        payloads = [
            bytes.fromhex("ffff676473060014010000001df5"),
            bytes.fromhex("ffff676473040e1401000f6e"),
            payload_part_3,
            bytes.fromhex("ffff676473020114a02d"),
            bytes.fromhex("ffff6764730209142984"),
            bytes.fromhex("ffffffffffffffffffffffffffffffff")
        ]

        for payload in payloads:
            self.send_payload(payload)
            self.log(f"Sent: {payload.hex()}")
            time.sleep(0.05)

        self.log(f"Axial displacement command sent for {position_mm:.2f} mm.")
