import ctypes
from ctypes import byref, c_void_p, c_ulong, c_uint, c_ubyte, c_char_p, WinDLL
import struct
from time import sleep
from typing import Optional
import ftd2xx
import threading, time as _time

# -------------------------
# D2XX: load and bind funcs
# -------------------------
d2xx = WinDLL("ftd2xx.dll")
FT_STATUS = c_uint

FT_OpenEx      = d2xx.FT_OpenEx
FT_OpenEx.argtypes = [c_void_p, c_ulong, ctypes.POINTER(c_void_p)]
FT_OpenEx.restype  = FT_STATUS
FT_Close       = d2xx.FT_Close
FT_Close.argtypes = [c_void_p]
FT_Close.restype  = FT_STATUS
FT_GetModemStatus = d2xx.FT_GetModemStatus
FT_GetModemStatus.argtypes = [c_void_p, ctypes.POINTER(c_ulong)]
FT_GetModemStatus.restype  = FT_STATUS
FT_SetFlowControl = d2xx.FT_SetFlowControl
FT_SetFlowControl.argtypes = [c_void_p, c_ulong, ctypes.c_ushort, ctypes.c_ushort]
FT_SetFlowControl.restype  = FT_STATUS
FT_SetDataCharacteristics = d2xx.FT_SetDataCharacteristics
FT_SetDataCharacteristics.argtypes = [c_void_p, ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ubyte]
FT_SetDataCharacteristics.restype  = FT_STATUS
FT_SetBaudRate = d2xx.FT_SetBaudRate
FT_SetBaudRate.argtypes = [c_void_p, c_ulong]
FT_SetBaudRate.restype  = FT_STATUS
FT_SetDtr = d2xx.FT_SetDtr
FT_SetDtr.argtypes = [c_void_p]
FT_SetDtr.restype  = FT_STATUS
FT_SetRts = d2xx.FT_SetRts
FT_SetRts.argtypes = [c_void_p]
FT_SetRts.restype  = FT_STATUS
FT_Purge = d2xx.FT_Purge
FT_Purge.argtypes = [c_void_p, c_ulong]
FT_Purge.restype  = FT_STATUS
FT_Write = d2xx.FT_Write
FT_Write.argtypes = [c_void_p, ctypes.c_void_p, c_ulong, ctypes.POINTER(c_ulong)]
FT_Write.restype  = FT_STATUS
FT_Read = d2xx.FT_Read
FT_Read.argtypes  = [c_void_p, ctypes.c_void_p, c_ulong, ctypes.POINTER(c_ulong)]
FT_Read.restype   = FT_STATUS
# bind once near the other bindings
FT_SetTimeouts = d2xx.FT_SetTimeouts
FT_SetTimeouts.argtypes = [c_void_p, c_ulong, c_ulong]
FT_SetTimeouts.restype  = FT_STATUS


FT_OPEN_BY_SERIAL_NUMBER = 1
FT_PURGE_RX = 0x0001
FT_PURGE_TX = 0x0002
FLOW_NONE   = 0x0000

# Vars we care about
REG_PRESSURE_IDS = {0x5319, 0x2053}
REG_VOLUME_IDS   = {0x5305}
VOL_QUANTA = 0.0626  # mm³ per count

class SimpleCalibrationManager:
    def __init__(self, pressure_quanta: float, pressure_offset: float):
        self.q = pressure_quanta
        self.o = pressure_offset
    def get_pressure_calibration(self, serial: str):
        return {"pressure_quanta": self.q, "pressure_offset": self.o}

class STDDPC_FTDI_HandleController:
    def __init__(self, log=print, calibration_manager=None):
        # Canonical FTDI handle and connection state
        self.h: c_void_p = c_void_p()         # null handle by default
        self.connected: bool = False
        self.handle = self.h                   # legacy alias kept in sync on connect/close

        self.serial: Optional[str] = None
        self.calib = None
        self.log = log
        self.calibration_manager = calibration_manager

        self._last_pressure_kpa = None
        self._last_volume_mm3   = None
        self._last_ts           = 0.0
        self._reader_thread     = None
        self._reader_run        = False

        self._io_lock = threading.Lock()

    def get_cached_pressure(self, max_age_s: float = 0.5):
        if self._last_pressure_kpa is None: return None
        return self._last_pressure_kpa if (_time.monotonic() - self._last_ts) <= max_age_s else None

    def get_cached_volume(self, max_age_s: float = 0.5):
        if self._last_volume_mm3 is None:
            return None
        return self._last_volume_mm3 if (_time.monotonic() - self._last_ts) <= max_age_s else None

    def set_command_limits(self, lo_kpa: float, hi_kpa: float):
        self._limit_min = float(lo_kpa)
        self._limit_max = float(hi_kpa)

    def _check(self, status: int, name: str):
        if status != 0:
            raise RuntimeError(f"{name} failed with status {status}")

    @staticmethod
    def _crc_ccitt_0x1021(payload: bytes, seed: int = 0x4489) -> bytes:
        crc = seed
        for b in payload:
            crc ^= (b & 0xFF) << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        return bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    def connect(self, serial: str, baud: int = 1_250_000):
        # reset state
        self.connected = False
        self.h = c_void_p()
        self.handle = self.h

        devs = ftd2xx.listDevices() or []
        dev_strs = [(d.decode() if isinstance(d, bytes) else str(d)) for d in devs]
        self.log(f"[i] FTDI devices: {dev_strs}")

        h = c_void_p()
        arg = c_char_p(serial.encode('ascii'))
        self._check(FT_OpenEx(ctypes.cast(arg, c_void_p), FT_OPEN_BY_SERIAL_NUMBER, byref(h)), f"FT_OpenEx({serial!r})")
        self.h = h
        self.handle = self.h  # keep alias current

        mod = c_ulong(0)
        self._check(FT_GetModemStatus(self.h, byref(mod)), "FT_GetModemStatus")
        self.log(f"[i] ModemStatus=0x{mod.value:04x}")

        self._check(FT_SetFlowControl(self.h, FLOW_NONE, 0, 0), "FT_SetFlowControl")
        self._check(FT_SetDtr(self.h), "FT_SetDtr")
        self._check(FT_SetRts(self.h), "FT_SetRts")
        self._check(FT_SetBaudRate(self.h, baud), "FT_SetBaudRate")

        self._check(FT_SetTimeouts(self.h, 20, 20), "FT_SetTimeouts")  # 20 ms RX/TX


        self._check(FT_Purge(self.h, FT_PURGE_RX | FT_PURGE_TX), "FT_Purge")
        self.log("[✓] Purged RX/TX")

        if self.calibration_manager is None:
            raise ValueError("Calibration manager not provided")
        self.calib = self.calibration_manager.get_pressure_calibration(serial)
        self.log(f"[✓] Calibration loaded: quanta={self.calib['pressure_quanta']} kPa/count, offset={self.calib['pressure_offset']} kPa")

        self.connected = True
        self.serial = serial

        self._reader_run = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        return True

    def close(self):
        self._reader_run = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)

        try:
            if self.is_ready():
                FT_Close(self.h)
        except Exception:
            pass
        finally:
            self.connected = False
            self.h = c_void_p()
            self.handle = self.h
            self.log("[✓] Handle closed")

    def _reader_loop(self):
        while self._reader_run and self.is_ready():
            try:
                raw = self._read_chunk(96 * 4)
                if raw:
                    self._parse_stddpc_vars(raw)
                    _time.sleep(0.001)  # yield a tick when busy
                else:
                    _time.sleep(0.02)
            except Exception:
                _time.sleep(0.05)

    def _write(self, data: bytes) -> int:
        buf = (c_ubyte * len(data)).from_buffer_copy(data)
        written = c_ulong(0)
        with self._io_lock:
            self._check(FT_Write(self.h, buf, len(data), byref(written)), "FT_Write")
        return int(written.value)

    def send_pressure(self, pressure_kpa: float):
        if not self._ensure_ready("send_pressure"):
            return False
            # enforce limits if present
        lo = getattr(self, "_limit_min", None)
        hi = getattr(self, "_limit_max", None)
        if (lo is not None) and (hi is not None):
            if not (lo <= pressure_kpa <= hi):
                self.log(f"[!] send_pressure blocked: {pressure_kpa:.3f} outside {lo:.3f}…{hi:.3f} kPa")
                return False
        if not self.calib:
            self.calib = {"pressure_quanta": 1.0, "pressure_offset": 0.0}
        try:
            quanta = self.calib["pressure_quanta"]
            offset = self.calib["pressure_offset"]
            target_count = int(round((pressure_kpa + offset) / quanta))

            frame = self.build_set_pressure_frame(target_count)
            wrote = self._write(frame)
            self.log(f"[→] Pressure set: {pressure_kpa:.3f} kPa | counts={target_count} | {wrote}B")

            # small read window to pull device diagnostics right after the set
            deadline = _time.monotonic() + 0.03
            while _time.monotonic() < deadline:
                self._read_and_parse_once()  # updates cache if frames arrive
                _time.sleep(0.005)
            return True
        except Exception as e:
            self.log(f"[!] send_pressure failed: {e}")
            return False

    def build_set_pressure_frame(self, target_count: int) -> bytes:
        """
        Build the *same* frame your PyUSB controller sends:
          header: 67 64 73 0a
          body (10B): 0x0200, mode=1, channel=0, int32 count (LE)
          crc: CCITT 0x1021 with seed 0x4489 over the 10-byte body
        """
        body = bytearray(10)
        body[0:2] = (0x0200).to_bytes(2, 'little')   # command/subcode
        body[2:4] = (1).to_bytes(2, 'little')        # mode
        body[4:6] = (0).to_bytes(2, 'little')        # channel 0 = pressure
        body[6:10] = int(target_count).to_bytes(4, 'little', signed=True)

        crc = self._crc_ccitt_0x1021(bytes(body), seed=0x4489)
        header = b"\x67\x64\x73\x0a"                 # 4B: 'gd s' + body length=0x0a
        return header + bytes(body) + crc

    def read_pressure_kpa(self, timeout_s: float = 0.6):
        if not self.is_ready():
            return None
        deadline = _time.monotonic() + timeout_s
        try:
            while _time.monotonic() < deadline:
                for v in self._read_and_parse_once():
                    if v["var_id_int"] in REG_PRESSURE_IDS:
                        val = float(v["engineering_value"])
                        self._last_pressure_kpa = val
                        self._last_ts = _time.monotonic()
                        return val
                _time.sleep(0.01)
            return None
        except Exception as e:
            self.log(f"[!] read_pressure_kpa failed: {e}")
            return None

    def read_volume_mm3(self, timeout_s: float = 0.6):
        if not self.is_ready():
            return None
        deadline = _time.monotonic() + timeout_s
        try:
            while _time.monotonic() < deadline:
                for v in self._read_and_parse_once():
                    if v["var_id_int"] in REG_VOLUME_IDS:
                        val = float(v["engineering_value"])
                        self._last_volume_mm3 = val
                        self._last_ts = _time.monotonic()
                        return val
                _time.sleep(0.01)
            return None
        except Exception:
            return None

    def stop(self):
        if not self._ensure_ready("stop"):
            return False
        try:
            FT_Purge(self.h, FT_PURGE_RX | FT_PURGE_TX)
            self.log("[→] STDDPC stop (purged RX/TX)")
            return True
        except Exception as e:
            self.log(f"[!] stop failed: {e}")
            return False

    def _read_chunk(self, max_len=384) -> bytes:
        with self._io_lock:
            buf = (c_ubyte * max_len)()
            got = c_ulong(0)
            self._check(FT_Read(self.h, buf, max_len, byref(got)), "FT_Read")
        return bytes(buf[:int(got.value)])

    def _parse_stddpc_vars(self, data: bytes):
        HEADER = b'\xff\xff\x67\x64'
        WANT   = REG_PRESSURE_IDS | REG_VOLUME_IDS
        out = []
        i = 0
        while i < len(data):
            start = data.find(HEADER, i)
            if start == -1:
                break
            next_start = data.find(HEADER, start + 4)
            if next_start == -1:
                next_start = len(data)
            pkt = data[start:next_start]

            if len(pkt) >= 14:
                vid_le = int.from_bytes(pkt[8:10], "little")
                vid_be = int.from_bytes(pkt[8:10], "big")
                canonical = vid_le if vid_le in WANT else (vid_be if vid_be in WANT else None)
                if canonical is not None:
                    signed32 = int.from_bytes(pkt[10:14], "little", signed=True)
                    if canonical in REG_PRESSURE_IDS:
                        eng_val = signed32 * self.calib["pressure_quanta"] - self.calib["pressure_offset"]
                        self._last_pressure_kpa = float(eng_val)
                        self._last_ts = _time.monotonic()
                    elif canonical in REG_VOLUME_IDS:
                        eng_val = signed32 * VOL_QUANTA
                        self._last_volume_mm3 = float(eng_val)
                        self._last_ts = _time.monotonic()
                    else:
                        eng_val = None
                    out.append({"var_id_int": canonical, "engineering_value": eng_val})
            i = next_start
        return out

    def _read_and_parse_once(self):
        raw = self._read_chunk(96 * 4)
        return self._parse_stddpc_vars(raw) if raw else []

    def is_ready(self) -> bool:
        """Ready when we have a non-null FTDI handle and we’re marked connected."""
        h = getattr(self, "h", None)
        return isinstance(h, c_void_p) and bool(h) and bool(getattr(self, "connected", False))

    def _ensure_ready(self, action: str) -> bool:
        if not self.is_ready():
            # DO NOT use “[✗]” here; it triggers a modal in MainWindow.log()
            try:
                self.log(f"[dbg] ensure_ready({action}) → not ready; h={getattr(self, 'h', None)!r}")
            except Exception:
                pass
            return False
        return True

    def purge(self) -> bool:
        """Optional, but helpful so manager can purge at stage handoff."""
        if not self.is_ready():
            return False
        try:
            FT_Purge(self.h, FT_PURGE_RX | FT_PURGE_TX)
            self.log("[✓] Purged RX/TX")
            return True
        except Exception as e:
            self.log(f"[!] Purge failed: {e}")
            return False

    ## RAMP FUNCTION ##
    def ramp_pressure(
            self,
            target_kpa: float,
            rate_kpa_per_min: float,
            step_kpa: float = 0.5,
            tol_kpa: float = 0.5,
            settle_time_s: float = 0.30,
            max_duration_s: float = 120.0,
            min_step_kpa: float = 0.05,
        ):
        """
        Slew pressure toward target_kpa using feedback (read_pressure_kpa).
        - rate_kpa_per_min: desired ramp rate (positive value).
        - step_kpa: nominal step size for setpoint updates.
        - tol_kpa: completion tolerance |meas - target| <= tol_kpa.
        - settle_time_s: wait time after each setpoint change before reading back.
        - max_duration_s: safety timeout for the entire ramp.
        - min_step_kpa: smallest step we’ll command when close to target.

        Returns (reached: bool, last_meas: float|None)
        """
        import time
        if rate_kpa_per_min <= 0:
            raise ValueError("rate_kpa_per_min must be > 0")

        if not self._ensure_ready("ramp_pressure"):
            return False, None

        # initial measurement
        meas = self.read_pressure_kpa(timeout_s=0.6)
        if meas is None:
            self.log("[ramp] No initial pressure reading — aborting.")
            return False, None

        self.log(f"[ramp] Start {meas:.3f} → {target_kpa:.3f} kPa @ {rate_kpa_per_min} kPa/min")

        # time between setpoint updates for given step size
        base_dt = (step_kpa / rate_kpa_per_min) * 60.0
        base_dt = min(max(base_dt, 0.02), 1.0)  # clamp to [0.02, 1.0] s

        start = time.monotonic()
        last = meas

        while True:
            # timeout?
            if time.monotonic() - start > max_duration_s:
                self.log("[ramp] Timeout.")
                return False, last

            # check done
            err = target_kpa - last
            if abs(err) <= tol_kpa:
                self.log(f"[ramp] Reached target (|error|={abs(err):.3f} ≤ {tol_kpa}).")
                return True, last

            # choose a step toward the target, and shrink as we get close
            this_step = max(min(abs(err) / 2.0, step_kpa), min_step_kpa)
            next_sp = last + (this_step if err > 0 else -this_step)

            # command next setpoint
            try:
                self.send_pressure(next_sp)
            except Exception as e:
                self.log(f"[ramp] send_pressure({next_sp:.3f}) failed: {e}")
                return False, last

            # allow device to respond; wait a little “settle” time first
            time.sleep(settle_time_s)

            # poll once or twice for a fresh value
            new_meas = self.read_pressure_kpa(timeout_s=0.5)
            if new_meas is None:
                time.sleep(0.05)
                new_meas = self.read_pressure_kpa(timeout_s=0.5)

            if new_meas is None:
                self.log("[ramp] Readback timeout; continuing cautiously.")
                time.sleep(base_dt)
                continue

            # update
            last = new_meas

            # cadence control to respect the desired ramp rate
            time.sleep(base_dt)
