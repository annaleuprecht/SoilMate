
import usb.core
import usb.util
import time

class STTDPCController:
    def __init__(self, log=print):
        self.dev = None
        self.log = log
        self.out_ep = 0x02

    def connect(self, usb_device=None):
        try:
            self.dev = usb_device or usb.core.find(idVendor=0x0403, idProduct=0x6001)
            if self.dev is None:
                self.log("[✗] STTDPC not found.")
                return False

            self.dev.set_configuration()
            usb.util.claim_interface(self.dev, 0)
            self.device = self.dev  # <--- ADD THIS LINE

            def write(data):
                self.dev.write(self.out_ep, data, timeout=100)

            # FTDI init sequence...
            write(bytes.fromhex("a0 03 00 00 00 00 00 00 00"))
            time.sleep(0.02)
            write(bytes.fromhex("a0 01 00 00 00 00 00 00 00"))
            time.sleep(0.02)
            write(bytes.fromhex("a0 02 00 00 00 00 00 00 00"))
            time.sleep(0.02)
            write(bytes.fromhex("a0 06 00 00 00 00 00 00 00"))
            time.sleep(0.02)

            self.log("[✓] STTDPC connected successfully.")

            product = usb.util.get_string(self.dev, self.dev.iProduct)
            serial = usb.util.get_string(self.dev, self.dev.iSerialNumber)
            self.log(f"[Debug] Connected to product: {product}, serial: {serial}")

            return True

        except Exception as e:
            self.log(f"[✗] Connection failed: {e}")
            return False

##    def encode_signed_24bit_le(self, value):
##        """Encodes a signed 24-bit integer as a 3-byte little-endian value."""
##        if not -8388608 <= value <= 8388607:
##            raise ValueError("Value out of 24-bit signed range.")
##        if value < 0:
##            value = (1 << 24) + value  # two's complement for negative values
##        return value.to_bytes(3, byteorder='little')

    def send_pressure(self, pressure_kpa):
        # From stddpc_usb_payload_user_input.py
        target_count = round((pressure_kpa + 7) / 5.414e-4)
        #target_bytes = self.encode_signed_24bit_le(target_count)
        
        payload_part_2 = bytearray(10)
        payload_part_2[0:2] = (0x0200).to_bytes(2, 'little')
        payload_part_2[2:4] = (1).to_bytes(2, 'little')  # mode
        payload_part_2[4:6] = (0).to_bytes(2, 'little')  # channel
        full_count_bytes = target_count.to_bytes(4, 'little', signed=True)
        payload_part_2[6:10] = full_count_bytes  # includes correct MSB for sign

        payload_part_1 = bytes([0x67, 0x64, 0x73, len(payload_part_2)])
        crc = self.calculate_crc(payload_part_2)
        full_payload = payload_part_1 + payload_part_2 + crc
        self.log(f"[→] Sending pressure payload: {full_payload.hex()}")
        self.dev.write(self.out_ep, full_payload, timeout=100)
        self.log(f"[→] Sent pressure command: {pressure_kpa} kPa")

    def send_volume(self, volume_mm3):
        # From stddpc_usb_volume_payload.py
        count = round(volume_mm3 / 6.26e-2)
        full_count_bytes = count.to_bytes(4, 'little', signed=True)
        payload_part_2 = bytearray(10)
        payload_part_2[0:2] = (0x0200).to_bytes(2, 'little')
        payload_part_2[2:4] = (1).to_bytes(2, 'little')  # mode
        payload_part_2[4:6] = (1).to_bytes(2, 'little')  # channel 1 for volume
        payload_part_2[6:9] = full_count_bytes[0:3]
        payload_part_2[9] = 0x00

        self.dev.write(self.out_ep, bytes.fromhex("67 64 73 0a"))
        self.dev.write(self.out_ep, payload_part_2)
        self.dev.write(self.out_ep, self.calculate_crc(payload_part_2))
        self.log(f"[→] Sent volume command: {volume_mm3} mm³")

    def calculate_crc(self, payload):
        crc = 0x4489
        for byte in payload:
            crc = self.next_crc_byte(crc, byte)
        return bytes([crc >> 8, crc & 0xFF])

    def next_crc_byte(self, crc, byte):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
        return crc & 0xFFFF
