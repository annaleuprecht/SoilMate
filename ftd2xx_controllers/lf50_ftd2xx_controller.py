import ftd2xx
import time
import struct

class FTLoadFrameController:
    """
    Load frame controller using FTDI D2XX interface, mirroring GDSLab LF50 sequence.
    """

    MIN_POSITION_MM = -158.0
    MAX_POSITION_MM = 67.26
    MIN_VELOCITY = -90.0   # mm/min
    MAX_VELOCITY = 90.0    # mm/min

    def __init__(self, log=print, baud=1200000, default_move_velocity_mm_min: float = 10.0):
        self.dev = None
        self.serial = None
        self.log = log
        self.baud = baud
        self.should_stop = False
        self.default_move_velocity_mm_min = float(default_move_velocity_mm_min)  # NEW

        self._lf_min_pos = -50.0
        self._lf_max_pos =  50.0
        self._lf_max_vel =  50.0  # mm/min

    def set_motion_limits(self, min_pos_mm: float, max_pos_mm: float, max_vel_mm_min: float):
        self._lf_min_pos = float(min_pos_mm)
        self._lf_max_pos = float(max_pos_mm)
        self._lf_max_vel = float(max_vel_mm_min)
        drv = getattr(self, "driver", None)
        if drv and hasattr(drv, "set_motion_limits"):
            drv.set_motion_limits(self._lf_min_pos, self._lf_max_pos, self._lf_max_vel)

    def set_default_move_velocity(self, v_mm_min: float):
        self.default_move_velocity_mm_min = float(v_mm_min)

    def list_devices(self):
        """Return available FTDI serials for GUI dropdown."""
        try:
            devs = ftd2xx.listDevices() or []
            serials = [(d.decode() if isinstance(d, bytes) else str(d)) for d in devs]
            return [s for s in serials if s]  # NEW: drop blanks
        except Exception:
            self.log("[!] Unable to list FTDI devices")
            return []

    def connect(self, serial_number):
        # Fallback: pick a valid interface, never index 0 if it’s blank
        try:
            devs = ftd2xx.listDevices() or []
            serials = [d.decode() if isinstance(d, bytes) else str(d) for d in devs]
            idx_by_serial = {s: i for i, s in enumerate(serials) if s}  # skip blanks

            # Prefer the requested serial if it appears (case mismatch etc.)
            if serial_number and serial_number in idx_by_serial:
                idx = idx_by_serial[serial_number]
            else:
                # else pick the first non-empty entry
                idx = next(iter(idx_by_serial.values()), None)

            if idx is None:
                self.log("[✗] No usable FTDI interface found.")
                return False

            self.dev = ftd2xx.open(idx)
            self.serial = serials[idx]
            self.log(f"[✓] Opened by index {idx} (serial={self.serial})")
        except Exception as e:
            self.log(f"[✗] FTDI open fallback failed: {e}")
            return False

        # Initialization
        try:
            # ModemStatus
            try:
                status = self.dev.getModemStatus()
                self.log(f"[i] ModemStatus=0x{status:04x}")
            except Exception:
                self.log("[!] getModemStatus unavailable")

            # Flow control NONE
            try:
                self.dev.setFlowControl(ftd2xx.defines.FLOW_NONE, 0, 0)
            except Exception:
                self.dev.setFlowControl(0, 0, 0)
            self.log("[✓] FlowControl=NONE")

            # DTR/RTS
            try:
                self.dev.setDtr(); self.dev.setRts()
                self.log("[✓] DTR and RTS asserted")
            except Exception:
                self.log("[!] DTR/RTS not supported")

            # Baud rate
            self.dev.setBaudRate(self.baud)
            self.log(f"[✓] BaudRate={self.baud}")

            # Purge RX/TX
            try:
                self.dev.purge(ftd2xx.defines.PURGE_RX | ftd2xx.defines.PURGE_TX)
            except Exception:
                self.dev.purge(1|2)
            self.log("[✓] Purged RX/TX")

            return True
        except Exception as e:
            self.log(f"[✗] FTDI init failed: {e}")
            return False

    def crc16_gds(self, data: bytes) -> bytes:
        """
        CRC16-CCITT with initial 0x4489, produce two-byte big-endian.
        """
        crc = 0x4489
        for b in data:
            crc ^= (b << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return crc.to_bytes(2, 'big')

    def get_motion_limits(self):
        """Return (min_pos_mm, max_pos_mm, max_vel_mm_min) currently enforced."""
        return (self._lf_min_pos, self._lf_max_pos, self._lf_max_vel)

    def send_displacement(self, position_mm: float, velocity_mm_per_min: float | None = None):
        """
        Absolute move with LF50 framing.
        We prime motion exactly like the velocity command: 3 pre-frames + direction,
        then send the 0x0B14 position payload. Accepts optional velocity just to
        pick a direction if the caller supplies it.
        """
        if not (self._lf_min_pos <= float(position_mm) <= self._lf_max_pos):
            self.log(f"[!] Position {position_mm:.2f} mm outside {self._lf_min_pos:.2f}…{self._lf_max_pos:.2f} mm"); 
            return False
        if not self.dev:
            self.log("[✗] Device not connected")
            return False

        # choose direction: prefer provided velocity sign; else use target position sign
        v = self.default_move_velocity_mm_min if velocity_mm_per_min is None else float(velocity_mm_per_min)
        move_positive = (v > 0) if (velocity_mm_per_min is not None and v != 0) else (position_mm >= 0)

        self.should_stop = False

        # ---- Build main position payload (same as before) ----
        float_val = position_mm / 1000.0
        float_bytes = struct.pack('<f', float_val)
        self.log(f"[debug] {position_mm} mm → {float_val} m → bytes: {float_bytes.hex()}")
        payload_body = b'\x0b\x14' + float_bytes
        crc_val = self.crc16_gds(payload_body)
        main_frame = b'\xff\xffgds' + bytes([len(payload_body)]) + payload_body + crc_val

        # ---- 1) Pre-motion: use the SAME 3 frames as send_velocity ----
        pre_frames = [
            bytes.fromhex("ffff676473060014010000001df5"),
            bytes.fromhex("ffff676473040e1401000f6e"),
        ]
        for frame in pre_frames:
            if self.should_stop:
                self.log("[!] Displacement aborted before pre-commands finished.")
                return False
            self.dev.write(frame)
            self.log(f"[→] Pre-command: {frame.hex()}")
            time.sleep(0.05)

        # ---- 3) Main position payload ----
        if self.should_stop:
            self.log("[!] Displacement aborted before sending main payload.")
            return False
        self.dev.write(main_frame)
        self.log(f"[→] Displacement: {position_mm:.2f} mm → {main_frame.hex()}")
        time.sleep(0.05)

        # ---- 4) Cleanup (keep your existing three frames) ----
        cleanup = [
            bytes.fromhex("ffff676473020114a02d"),
            bytes.fromhex("ffff6764730209142984"),
            bytes.fromhex("ffffffffffffffffffffffffffffffff"),
        ]
        for frame in cleanup:
            if self.should_stop:
                self.log("[!] Aborted during cleanup.")
                return False
            self.dev.write(frame)
            self.log(f"[→] Cleanup: {frame.hex()}")
            time.sleep(0.05)

        self.log(f"[✓] Axial displacement command finished for {position_mm:.2f} mm.")
        return True

    def send_velocity(self, velocity: float) -> bool:
        """
        Send axial velocity sequence:
        1) Three pre-motion commands
        2) Direction payload based on sign of velocity
        3) Main velocity payload (0x0D14 + float32 LE(rps))
        4) Cleanup payloads (2 frames)
        """
        if not self.dev:
            self.log("[✗] Device not connected")
            return False

        # clamp velocity
        vmax = float(self._lf_max_vel)
        if abs(velocity) > vmax:
            self.log(f"[!] Velocity {velocity:.2f} mm/min exceeds vmax {vmax:.2f} mm/min"); 
            return False
        vel = max(self.MIN_VELOCITY, min(self.MAX_VELOCITY, velocity))
        self.should_stop = False

        # Build main velocity payload
        # velocity input in mm/min -> convert to m/s
        m_per_s = vel / 60000.0
        float_bytes = struct.pack('<f', m_per_s)
        self.log(f"[debug] {vel} mm/min → {m_per_s} m/s → bytes: {float_bytes.hex()}")
        payload_body = b'\x0d\x14' + float_bytes
        crc_val = self.crc16_gds(payload_body)
        main_frame = b'\xff\xffgds' + bytes([len(payload_body)]) + payload_body + crc_val

        # 1) Pre-motion commands
        pre_frames = [
            bytes.fromhex("ffff676473060014010000001df5"),
            bytes.fromhex("ffff676473042014050056be"),
            bytes.fromhex("ffff676473040e1401000f6e"),
        ]
        for frame in pre_frames:
            if self.should_stop:
                self.log("[!] Velocity aborted before motion payload.")
                return False
            self.dev.write(frame)
            self.log(f"[→] Pre-command: {frame.hex()}")
            time.sleep(0.05)

        # 2) Direction payload
        dir_frame = (bytes.fromhex("ffff676473060b14161f583d9b67") 
                     if vel > 0 else 
                     bytes.fromhex("ffff676473060b1409eedcbdc698"))
        self.dev.write(dir_frame)
        self.log(f"[→] Direction: {dir_frame.hex()}")
        time.sleep(0.05)

        # 3) Main velocity payload
        if self.should_stop:
            self.log("[!] Velocity aborted before sending main payload.")
            return False
        self.dev.write(main_frame)
        self.log(f"[→] Velocity: {vel:.2f} mm/min → {main_frame.hex()}")
        time.sleep(0.05)

        # 4) Cleanup
        cleanup = [
            bytes.fromhex("ffff676473021a147fa4"),
            bytes.fromhex("ffffffffffffffffffffffffffffffff"),
        ]
        for frame in cleanup:
            if self.should_stop:
                self.log("[!] Aborted during cleanup.")
                return False
            self.dev.write(frame)
            self.log(f"[→] Cleanup: {frame.hex()}")
            time.sleep(0.05)

        self.log(f"[✓] Axial velocity command finished for {vel:.2f} mm/min.")
        return True

    def stop_motion(self):
        """
        Send stop command twice to halt any ongoing motion and set the stop flag.
        """
        if not self.dev:
            self.log("[✗] Device not connected")
            return False

        stop_payload = bytes.fromhex("ffff676473020116806f")
        # Send twice with a small delay
        try:
            self.dev.write(stop_payload)
            time.sleep(0.1)
            self.dev.write(stop_payload)
            self.log("[→] Sent LF50 stop command (x2)")
            self.should_stop = True
            return True
        except Exception as e:
            self.log(f"[✗] Failed to send stop command: {e}")
            return False

    def is_ready(self): return self.dev is not None
    def stop(self): return getattr(self, "stop_motion", lambda: None)()
    def send_stop(self): return self.stop()
    def purge(self):
        if not self.dev: return False
        try:
            self.dev.purge(ftd2xx.defines.PURGE_RX | ftd2xx.defines.PURGE_TX)
            self.log("[✓] Purged RX/TX")
            return True
        except Exception as e:
            self.log(f"[!] Purge failed: {e}")
            return False

