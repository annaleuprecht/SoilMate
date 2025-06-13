import time
from device_controllers.lf50_movement import LF50Mover
import usb.core
import usb.util

class LoadFrameController:

    MIN_POSITION_MM = -158.0
    MAX_POSITION_MM = 67.26
    
    def __init__(self, log=print):
        self.dev = None
        self.serial = None
        self.log = log

    def connect(self, ftdi_device=None):
        if ftdi_device is None:
            self.log("[✗] No FTDI device provided.")
            return False

        try:
            self.dev = ftdi_device
            self.dev.set_configuration()
            usb.util.claim_interface(self.dev, 0)

            cfg = self.dev.get_active_configuration()
            intf = cfg[(0, 0)]
            
            self.ep_out = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            )
            self.ep_in = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            )

            if not self.ep_out or not self.ep_in:
                self.log("[✗] Failed to find endpoints.")
                return False

            self.serial = usb.util.get_string(self.dev, self.dev.iSerialNumber)
            self._initialize_ftdi()
            self.log(f"[*] Connected to LF50 ({self.serial})")
            return True

        except Exception as e:
            self.log(f"[✗] USB connect failed: {e}")
            return False
    def _initialize_ftdi(self):
        def ctrl(bm, req, val, idx, length=None, label=""):
            self.log(f"[TX] {label}")
            try:
                self.dev.ctrl_transfer(bm, req, val, idx, length)
                self.log(f"[✓] {label}")
            except Exception as e:
                self.log(f"[✗] {label}: {e}")

        time.sleep(0.1)
        ctrl(0x80, 6, 0x0100, 0x0000, 18, "GET_DESCRIPTOR: DEVICE")
        ctrl(0x80, 6, 0x0200, 0x0000, 32, "GET_DESCRIPTOR: CONFIGURATION")
        ctrl(0x00, 9, 0x0001, 0x0000, None, "SET_CONFIGURATION")
        time.sleep(0.1)
        ctrl(0x40, 0x00, 0x0000, 0x0000, None, "FTDI: Reset")
        ctrl(0xC0, 0x05, 0x0000, 0x0000, 2, "FTDI: GetModemStat")
        ctrl(0x40, 0x04, 0x0008, 0x0000, None, "FTDI: SetData")
        ctrl(0x40, 0x02, 0x0000, 0x0000, None, "FTDI: SetFlowCtrl")
        ctrl(0x40, 0x03, 0x4138, 0x0000, None, "FTDI: SetBaudRate")
        ctrl(0x40, 0x02, 0x0000, 0x0100, None, "FTDI: SetFlowCtrl (RTS/CTS)")
        ctrl(0x40, 0x01, 0x0202, 0x0000, None, "FTDI: ModemCtrl")
        ctrl(0x40, 0x04, 0x0008, 0x0000, None, "FTDI: SetData (repeat)")
        ctrl(0x40, 0x03, 0x0002, 0x0001, None, "FTDI: SetBaudRate (4800)")
        ctrl(0x40, 0x00, 0x0001, 0x0000, None, "FTDI: Reset (repeat)")

        for _ in range(10):
            ctrl(0x40, 0x00, 0x0001, 0x0000, None, "FTDI: Reset (extra)")
            time.sleep(0.05)

        self.log("[✓] FTDI/USB Init Sequence Complete.")

    def send_displacement(self, mm):
        if not self.dev:
            self.log("[✗] LF50 not connected.")
            return

        if mm < self.MIN_POSITION_MM or mm > self.MAX_POSITION_MM:
            self.log(f"[✗] Displacement {mm} mm out of range ({self.MIN_POSITION_MM} to {self.MAX_POSITION_MM}).")
            return

        try:
            mover = LF50Mover(self.dev, log=self.log)
            mover.send_displacement(mm)
            self.log(f"[→] Sent displacement command: {mm:.2f} mm")
        except Exception as e:
            self.log(f"[✗] Failed to send displacement: {e}")

    def stop(self):
        if self.dev:
            mover = LF50Mover(self.dev, log=self.log)
            mover.stop_motion()

