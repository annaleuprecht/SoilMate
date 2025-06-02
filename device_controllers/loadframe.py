import usb.core
import usb.util
import time
from device_controllers.lf50_movement import LF50Mover


class LoadFrameController:
    def __init__(self, log=print):
        self.device = None
        self.log = log
        self.out_ep = 0x02

    def connect(self, usb_device=None):
        self.device = usb_device if usb_device is not None else usb.core.find(idVendor=0x0403, idProduct=0x6001)
        self.log(f"[*] Connecting to LF50 load frame at address {self.device.address}")
        self.log(f"Serial Number: {usb.util.get_string(self.device, self.device.iSerialNumber)}")
        if self.device is None:
            self.log("[✗] Device not found.")
            return False

        try:
            # Always release in case already claimed
            try:
                usb.util.release_interface(self.device, 0)
            except usb.core.USBError:
                pass  # Already released or not yet claimed

            self.device.set_configuration()
            cfg = self.device.get_active_configuration()
            intf = cfg[(0, 0)]
            usb.util.claim_interface(self.device, intf.bInterfaceNumber)

            time.sleep(0.1)
            self._init_sequence()
            self.log("[✓] Connected successfully")
            return True

        except Exception as e:
            self.log(f"[✗] Connection failed: {e}")
            return False

    def send_displacement(self, mm):
        if not self.device:
            self.log("[✗] LF50 not connected.")
            return

        try:
            mover = LF50Mover(self.device, log=self.log)
            mover.send_displacement(mm)
            self.log(f"[→] Sent displacement command: {mm:.2f} mm")
        except Exception as e:
            self.log(f"[✗] Failed to send displacement: {e}")


    def _xfer(self, bmRequestType, bRequest, wValue, wIndex, data_or_wLength, label):
        try:
            self.log(f"[TX] {label}")
            self.device.ctrl_transfer(bmRequestType, bRequest, wValue, wIndex, data_or_wLength)
        except usb.core.USBError as e:
            self.log(f"[✗] {label} failed - {e}")

    def _init_sequence(self):
        self._xfer(0x80, 6, 0x0100, 0x0000, 18, "GET_DESCRIPTOR: DEVICE")
        self._xfer(0x80, 6, 0x0200, 0x0000, 32, "GET_DESCRIPTOR: CONFIGURATION")
        self._xfer(0x00, 9, 0x0001, 0x0000, None, "SET_CONFIGURATION")
        time.sleep(0.1)

        self._xfer(0x40, 0x00, 0x0000, 0x0000, None, "FTDI: Reset (Purge RX/TX)")
        self._xfer(0xC0, 0x05, 0x0000, 0x0000, 2, "FTDI: GetModemStat")
        self._xfer(0x40, 0x04, 0x0008, 0x0000, None, "FTDI: SetData")
        self._xfer(0x40, 0x02, 0x0000, 0x0000, None, "FTDI: SetFlowCtrl")
        self._xfer(0x40, 0x03, 0x4138, 0x0000, None, "FTDI: SetBaudRate")
        self._xfer(0x40, 0x02, 0x0000, 0x0100, None, "FTDI: SetFlowCtrl")
        self._xfer(0x40, 0x01, 0x0202, 0x0000, None, "FTDI: ModemCtrl")
        self._xfer(0x40, 0x04, 0x0008, 0x0000, None, "FTDI: SetData")
        self._xfer(0x40, 0x03, 0x0002, 0x0001, None, "FTDI: SetBaudRate")
        self._xfer(0x40, 0x00, 0x0001, 0x0000, None, "FTDI: Reset (Repeat)")
        for _ in range(10):
            self._xfer(0x40, 0x00, 0x0001, 0x0000, None, "FTDI: Reset (Loop)")
            time.sleep(0.05)
