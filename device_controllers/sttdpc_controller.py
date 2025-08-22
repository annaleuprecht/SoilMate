# Shim for STDDPC v2: keeps the old GUI-facing API, delegates to FTDI impl.
# Place at: device_controllers/sttdpc_controller.py

from typing import Optional, Any
import usb.util  # only needed if GUI still passes a libusb device object

# ⬇️ UPDATE this import/path/class to your actual FTDI controller
# e.g. from ftd2xx_controllers.stddpc_ftd2xx_controller import STDDPC_FTDI_HandleController
from ftd2xx_controllers.stddpc_ftd2xx_controller import STDDPC_FTDI_HandleController
from ctypes import c_void_p

def _serial_from_usb_dev(dev: Any) -> str:
    """Extract serial from a legacy PyUSB device object."""
    return usb.util.get_string(dev, dev.iSerialNumber)


class STTDPCController:
    """
    Thin shim that delegates to an attached backend (FTDI/PyUSB/etc.).
    Quiet readiness checks; no '[✗]' logging from here.
    """

    def __init__(self, log=print, calibration_manager=None):
        self.driver = None
        self.log = log
        self.calibration_manager = calibration_manager
        # expose h on the shim for any legacy code that looks here
        self.h = None

    # --- attach already-connected backend ---
    def attach_driver(self, backend):
        self.driver = backend
        try:
            self.h = getattr(backend, "h", None)
        except Exception:
            self.h = None

    # --- optional: pass-through connect so old code still works ---
    def connect(self, serial: str):
        if self.driver is None:
            try:
                from ftd2xx_controllers.stddpc_ftd2xx_controller import STDDPC_FTDI_HandleController
            except Exception as e:
                self.log(f"[!] Could not import FTDI backend: {e}")
                return False
            self.driver = STDDPC_FTDI_HandleController(
                log=self.log,
                calibration_manager=self.calibration_manager,
            )
        ok = False
        try:
            ok = bool(self.driver.connect(serial))
        except Exception as e:
            self.log(f"[!] STDDPC shim connect failed: {e}")
            ok = False
        # mirror handle for any legacy checks
        try:
            self.h = getattr(self.driver, "h", None)
        except Exception:
            self.h = None
        return ok

    # --- quiet readiness ---
    def _unwrap(self):
        return self.driver or self

    def is_ready(self) -> bool:
        d = self._unwrap()
        h = getattr(d, "h", None)
        if not (isinstance(h, c_void_p) and bool(h)):
            return False
        # prefer backend's is_ready if present
        f = getattr(d, "is_ready", None)
        try:
            return bool(f()) if callable(f) else True
        except Exception:
            return True

    def _ensure_ready(self, action: str) -> bool:
        if not self.is_ready():
            try:
                self.log(f"[dbg] STDDPC shim not ready — {action} skipped.")
            except Exception:
                pass
            return False
        return True

    # --- delegates (no '[✗]' logging) ---
    def send_pressure(self, kpa: float):
        if not self._ensure_ready("send_pressure"):
            return False
        d = self._unwrap()
        f = getattr(d, "send_pressure", None)
        try:
            return bool(f(kpa)) if callable(f) else False
        except Exception as e:
            self.log(f"[!] shim send_pressure failed: {e}")
            return False

    def read_pressure_kpa(self, timeout_s: float = 0.6):
        if not self.is_ready():
            return None
        d = self._unwrap()
        f = getattr(d, "read_pressure_kpa", None)
        try:
            return f(timeout_s=timeout_s) if callable(f) else None
        except Exception:
            return None

    def read_volume_mm3(self, timeout_s: float = 0.6):
        if not self.is_ready():
            return None
        d = self._unwrap()
        f = getattr(d, "read_volume_mm3", None)
        try:
            return f(timeout_s=timeout_s) if callable(f) else None
        except Exception:
            return None

    def get_cached_pressure(self, max_age_s: float = 0.5):
        d = self._unwrap()
        f = getattr(d, "get_cached_pressure", None)
        try:
            return f(max_age_s) if callable(f) else None
        except Exception:
            return None

    def get_cached_volume(self, max_age_s: float = 0.5):
        d = self._unwrap()
        f = getattr(d, "get_cached_volume", None)
        try:
            return f(max_age_s) if callable(f) else None
        except Exception:
            return None

    def stop(self):
        if not self._ensure_ready("stop"):
            return False
        d = self._unwrap()
        for name in ("stop", "abort", "halt"):
            f = getattr(d, name, None)
            if callable(f):
                try:
                    f()
                    return True
                except Exception:
                    pass
        return False
