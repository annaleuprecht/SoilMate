import usb.core
import usb.util

class FtdiDeviceManager:
    def __init__(self, log=print):
        self.log = log

    def list_serials(self):
        serials = []
        devices = usb.core.find(find_all=True, idVendor=0x0403, idProduct=0x6001)
        for dev in devices:
            try:
                serial = usb.util.get_string(dev, dev.iSerialNumber)
                if serial:
                    serials.append(serial)
            except Exception as e:
                self.log(f"[!] Error reading serial: {e}")
        return serials

    def open_by_serial(self, serial):
        devices = usb.core.find(find_all=True, idVendor=0x0403, idProduct=0x6001)
        for dev in devices:
            try:
                dev_serial = usb.util.get_string(dev, dev.iSerialNumber)
                if dev_serial == serial:
                    dev.set_configuration()
                    usb.util.claim_interface(dev, 0)
                    return dev
            except Exception as e:
                self.log(f"[✗] Error opening {serial}: {e}")
        self.log(f"[✗] Could not find device with serial {serial}")
        return None
