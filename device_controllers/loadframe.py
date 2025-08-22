# Shim for LF50 load frame: keeps the old GUI-facing API, delegates to FTDI impl.
# Place at: device_controllers/loadframe.py

from typing import Optional, Any
import usb.util  # only needed if GUI still passes a libusb device object

# ⬇️ UPDATE this import/path/class to your actual FTDI load frame controller
# e.g. from ftd2xx_controllers.lf50_ftd2xx_controller import FTLoadFrameController
from ftd2xx_controllers.lf50_ftd2xx_controller import FTLoadFrameController


def _serial_from_usb_dev(dev: Any) -> str:
    """Extract serial from a legacy PyUSB device object."""
    return usb.util.get_string(dev, dev.iSerialNumber)


class LoadFrameController:
    """GUI-facing controller (stable surface)."""

    MIN_POSITION_MM = -158.0
    MAX_POSITION_MM = 67.26
    MIN_VELOCITY = -90.0
    MAX_VELOCITY = 90.0

    def __init__(self, log=print, baud=1_200_000):
        self.log = log
        self._baud = baud
        self._impl: Optional[FTLoadFrameController] = None

        self._lf_min_pos = -50.0
        self._lf_max_pos =  50.0
        self._lf_max_vel =  50.0  # mm/min

    def connect(self, ftdi_device=None, usb_device=None, usb_dev=None) -> bool:
        """
        Accepts either:
          - a libusb device object (legacy), or
          - a serial string (preferred).
        Opens via ftd2xx by serial.
        """
        src = ftdi_device or usb_device or usb_dev
        if src is None:
            self.log("[✗] No device provided to connect().")
            return False

        serial = (
            _serial_from_usb_dev(src) if hasattr(src, "iSerialNumber") else str(src)
        )
        self._impl = FTLoadFrameController(log=self.log, baud=self._baud)
        ok = self._impl.connect(serial)
        if ok:
            self.log(f"[✓] LF50 (FTDI) connected: {serial}")
            # NEW: immediately push any saved limits into the driver
            try:
                self._impl.set_motion_limits(self._lf_min_pos, self._lf_max_pos, self._lf_max_vel)
            except Exception:
                pass
        else:
            self.log("[✗] LF50 connect failed")
        return ok

    def send_displacement(self, position_mm: float, velocity_mm_per_min: float = 10.0):
        if not self._impl:
            return self.log("[✗] LF50 not connected.")
        if not (self.MIN_POSITION_MM <= position_mm <= self.MAX_POSITION_MM):
            return self.log(
                f"[✗] Position {position_mm} mm out of range ({self.MIN_POSITION_MM}..{self.MAX_POSITION_MM})."
            )
        return self._impl.send_displacement(position_mm, velocity_mm_per_min)

    def send_velocity(self, velocity_mm_per_min: float):
        if not self._impl:
            return self.log("[✗] LF50 not connected.")
        if not (self.MIN_VELOCITY <= velocity_mm_per_min <= self.MAX_VELOCITY):
            return self.log(
                f"[✗] Velocity {velocity_mm_per_min} mm/min out of range ({self.MIN_VELOCITY}..{self.MAX_VELOCITY})."
            )
        return self._impl.send_velocity(velocity_mm_per_min)

    def stop(self):
        if self._impl and hasattr(self._impl, "stop_motion"):
            return self._impl.stop_motion()

    # NEW: public API used by MainWindow / Device Settings page
    def set_motion_limits(self, min_pos_mm: float, max_pos_mm: float, max_vel_mm_min: float):
        self._lf_min_pos = float(min_pos_mm)
        self._lf_max_pos = float(max_pos_mm)
        self._lf_max_vel = float(max_vel_mm_min)
        if self._impl and hasattr(self._impl, "set_motion_limits"):
            self._impl.set_motion_limits(self._lf_min_pos, self._lf_max_pos, self._lf_max_vel)

    def get_motion_limits(self):
        if self._impl and hasattr(self._impl, "get_motion_limits"):
            return self._impl.get_motion_limits()
        return (self._lf_min_pos, self._lf_max_pos, self._lf_max_vel)

    def list_devices(self):
        # Works even before connect
        if self._impl and hasattr(self._impl, "list_devices"):
            return self._impl.list_devices()
        try:
            # fall back to a temp instance
            return FTLoadFrameController(log=self.log, baud=self._baud).list_devices()
        except Exception:
            return []

    def close(self):
        if self._impl and hasattr(self._impl, "close"):
            return self._impl.close()
