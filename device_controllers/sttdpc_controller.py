
import usb.core
import usb.util
import time

class STTDPCController:
    def __init__(self, log=print, calibration_manager=None):
        self.dev = None
        self.log = log
        self.ep_out = 0x02  # FTDI Bulk OUT endpoint
        self.calibration = None
        self.serial = None
        self.calibration_manager = calibration_manager

    def connect(self, dev):
        self.dev = dev
        self.serial = usb.util.get_string(dev, dev.iSerialNumber)

        if self.calibration_manager is None:
            raise ValueError("Calibration manager not provided")

        self.calibration = self.calibration_manager.get_pressure_calibration(self.serial)

        self._ftdi_init_sequence(self.dev)

        # Setup bulk endpoints
        cfg = self.dev.get_active_configuration()
        intf = cfg[(0, 0)]
        for ep in intf:
            if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT:
                self.bulk_out = ep
            elif usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                self.bulk_in = ep

        if not hasattr(self, "bulk_out") or not hasattr(self, "bulk_in"):
            raise ValueError("Could not find bulk endpoints")

        self.log(f"[✓] STDDPC initialized (serial: {self.serial})")
        return True

    def send_pressure(self, pressure_kpa):
        # From stddpc_usb_payload_user_input.py
        quanta = self.calibration["pressure_quanta"]
        offset = self.calibration["pressure_offset"]
        self.log(f"Offset: {offset}")
        target_count = round((pressure_kpa + offset) / quanta)
     
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
        if not self.ep_out:
            self.log("[✗] Cannot send: OUT endpoint not initialized.")
            return

        self.dev.write(self.ep_out, full_payload, timeout=100)
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

        self.dev.write(self.ep_out, bytes.fromhex("67 64 73 0a"), timeout=100)
        self.dev.write(self.ep_out, payload_part_2, timeout=100)
        self.dev.write(self.ep_out, self.calculate_crc(payload_part_2), timeout=100)

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

    def _ftdi_init_sequence(self, dev):
        def ct(bmRequestType, bRequest, wValue, wIndex, data_or_wLength, label):
            self.log(f"[TX] {label}")
            try:
                result = dev.ctrl_transfer(bmRequestType, bRequest, wValue, wIndex, data_or_wLength)
                self.log(f"[✓] Success: {label}")
                return result
            except usb.core.USBError as e:
                self.log(f"[✗] Failed: {label} - {e}")
                return None

        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        usb.util.claim_interface(dev, intf.bInterfaceNumber)

        time.sleep(0.1)
        ct(0x80, 6, 0x0100, 0x0000, 18, "GET_DESCRIPTOR: DEVICE")
        ct(0x80, 6, 0x0200, 0x0000, 32, "GET_DESCRIPTOR: CONFIGURATION")
        ct(0x00, 9, 0x0001, 0x0000, None, "SET_CONFIGURATION")

        time.sleep(0.1)
        ct(0x40, 0x00, 0x0000, 0x0000, None, "FTDI: Reset (Purge RX/TX)")
        ct(0xC0, 0x05, 0x0000, 0x0000, 2, "FTDI: GetModemStat")
        ct(0x40, 0x00, 0x0000, 0x0000, None, "FTDI: Reset (Repeat)")
        ct(0xC0, 0x05, 0x0000, 0x0000, 2, "FTDI: GetModemStat (Repeat)")
        ct(0x40, 0x02, 0x0000, 0x0100, None, "FTDI: SetFlowCtrl (RTS/CTS)")
        ct(0x40, 0x01, 0x0300, 0x0000, None, "FTDI: ModemCtrl")
        ct(0x40, 0x04, 0x0008, 0x0000, None, "FTDI: SetData")
        ct(0x40, 0x03, 0x0002, 0x0001, None, "FTDI: SetBaudRate (9600?)")  # ← Confirm this value

        for i in range(10):
            ct(0x40, 0x00, 0x0000, 0x0000, None, f"FTDI: Extra Reset #{i+1}")
            time.sleep(0.05)

        self.log("[✓] FTDI/USB Init Sequence Complete.")

    def stop(self):
        stop_cmd = bytes.fromhex("ffffffff676473020320b098ffffffffffffffff")
        self.dev.write(self.ep_out, stop_cmd, timeout=100)
        self.log("[→] Sent STDDPC stop command.")


