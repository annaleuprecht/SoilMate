
"""
mock_controllers.py
Stage-aware simulation for STDDPC, LF50, and SerialPad devices.
"""
import time, random, math

def _now():
    return time.time()

class BaseMockController:
    def __init__(self, name="MockDevice"):
        self.name = name
        self.active_stage = None
        self.stage_start_ts = None
        self.connected = False
        self.state = {}

    def connect(self, *args, **kwargs):
        self.connected = True
        return True

    def is_connected(self):
        return self.connected

    def status_api(self):
        return {
            "status": "OK" if self.connected else "DISCONNECTED",
            "connected": bool(self.connected),
            "serial_number": getattr(self, "serial_number", f"SIM-{self.name}")
        }

    def set_stage_profile(self, stage_data):
        self.active_stage = stage_data
        self.stage_start_ts = _now()
        self.state.clear()
        print(f"[SIM] {self.name} stage -> {getattr(stage_data,'stage_type','?')}")

    def tick(self):
        pass


class MockSTDDPCController(BaseMockController):
    """Simulates a pressure/volume controller (used for cell & back)."""
    def __init__(self, name="MockSTDDPC"):
        super().__init__(name)
        self.serial_number = f"{name}-SN"
        self._pressure_kpa = 0.0
        self._volume_mm3 = 0.0

    # --- public API (minimal) ---
    def read_pressure(self):
        return float(self._pressure_kpa)

    def read_volume(self):
        return float(self._volume_mm3)

    # compatible aliases some code might call
    def send_pressure(self, kpa):
        self._pressure_kpa = float(kpa)

    def set_pressure(self, kpa):
        self.send_pressure(kpa)

    def stop(self):
        pass

    def tick(self):
        if not self.active_stage:
            # idle noise
            self._pressure_kpa += random.uniform(-0.02, 0.02)
            return
        sd = self.active_stage
        stype = str(getattr(sd, "stage_type", "")).lower()
        dt = max(0.0, _now() - (self.stage_start_ts or _now()))
        # Optional ramp rate in kPa/min
        ramp_rate = float(getattr(sd, "ramp_rate", 10.0))  # default 10 kPa/min in sim
        step_kpa = ramp_rate / 60.0  # per second

        if stype == "saturation":
            # ramp both cell/back (this instance may represent either)
            target = float(getattr(sd, "cell_pressure", 0.0) if "Cell" in self.name else getattr(sd, "back_pressure", 0.0))
            if self._pressure_kpa < target:
                self._pressure_kpa = min(target, self._pressure_kpa + step_kpa)
            else:
                self._pressure_kpa = max(target, self._pressure_kpa - step_kpa/4)  # settle toward target
            # small volume creep
            self._volume_mm3 += random.uniform(-0.8, 0.8)

        elif stype == "consolidation":
            target = float(getattr(sd, "cell_pressure", 0.0) if "Cell" in self.name else getattr(sd, "back_pressure", 0.0))
            # instant to target, then slow drift in volume
            self._pressure_kpa += (target - self._pressure_kpa) * 0.5
            # simple consolidation creep
            self._volume_mm3 += (-0.3 + random.uniform(-0.05, 0.05))

        elif stype == "b check":
            # cell controller jumps; back holds
            if "Cell" in self.name:
                target = float(getattr(sd, "cell_pressure", 0.0))
                self._pressure_kpa += (target - self._pressure_kpa) * 0.4
            else:
                # back: small perturbation
                self._pressure_kpa += random.uniform(-0.05, 0.05)
            self._volume_mm3 += random.uniform(-0.3, 0.3)

        elif stype in ("shear", "automated docking"):
            # hold cell/back steady (whatever last set was)
            self._pressure_kpa += random.uniform(-0.02, 0.02)
            self._volume_mm3 += random.uniform(-0.2, 0.2)

        else:
            self._pressure_kpa += random.uniform(-0.02, 0.02)


class MockLF50Controller(BaseMockController):
    """Simulates the axial actuator."""
    def __init__(self, name="MockLF50"):
        super().__init__(name)
        self.serial_number = f"{name}-SN"
        self._position_mm = 0.0
        self._velocity_mm_min = 0.0

    # --- public API ---
    def read_position(self):
        return float(self._position_mm)

    # compatibility with stage code
    def send_velocity(self, mm_per_min):
        self._velocity_mm_min = float(mm_per_min)

    def send_stop(self):
        self._velocity_mm_min = 0.0

    def stop(self):
        self._velocity_mm_min = 0.0

    def send_displacement(self, target_mm):
        # snap to target in sim
        self._position_mm = float(target_mm)

    def tick(self):
        if not self.active_stage:
            # drift slightly
            self._position_mm += random.uniform(-0.002, 0.002)
            return
        sd = self.active_stage
        stype = str(getattr(sd, "stage_type", "")).lower()
        vel = float(getattr(sd, "axial_velocity", 0.0))  # mm/min from StageData
        dt = max(0.0, _now() - (self.state.get("last_ts") or _now()))
        if stype in ("shear", "automated docking"):
            # move at configured velocity; automated docking could be faster but we respect param if set
            v = vel if vel > 0 else self._velocity_mm_min
            self._position_mm += (v / 60.0) * dt
        else:
            # hold
            pass
        self.state["last_ts"] = _now()


class MockSerialPad(BaseMockController):
    """Simulates 8 analog channels.

    Channel mapping (to align with triaxial_test_manager._tick):

      0 = axial_load (kN)

      1 = pore_pressure (kPa)

      2 = axial_displacement (mm)

      3 = local_axial_1_mv

      4 = local_axial_2_mv

      5 = local_radial_mv

      6,7 = noise

    """
    def __init__(self, name="MockSerialPad"):
        super().__init__(name)
        self.serial_number = f"{name}-SN"
        self._channels = [0.0] * 8
        self.refs = {}

    def link_refs(self, cell_controller=None, back_controller=None, lf_controller=None):
        self.refs["cell"] = cell_controller
        self.refs["back"] = back_controller
        self.refs["lf"] = lf_controller

    def read_channels(self):
        return list(self._channels)

    def tick(self):
        # derive values from references + stage profile
        cell = self.refs.get("cell").read_pressure() if self.refs.get("cell") else 0.0
        back = self.refs.get("back").read_pressure() if self.refs.get("back") else 0.0
        pos  = self.refs.get("lf").read_position() if self.refs.get("lf") else 0.0

        sd = self.active_stage
        stype = str(getattr(sd, "stage_type", "" )).lower() if sd else ""

        # Defaults
        axial_load = self._channels[0]
        pore_kpa   = back
        disp_mm    = pos

        if stype == "saturation":
            # load small, pore ~ back pressure
            axial_load = max(0.0, axial_load + random.uniform(-0.01, 0.02))
            pore_kpa   = back + random.uniform(-0.2, 0.2)
            disp_mm    = pos

        elif stype == "consolidation":
            axial_load = max(0.0, axial_load + random.uniform(-0.02, 0.02))
            pore_kpa   = back + random.uniform(-0.1, 0.1)
            disp_mm    = pos + random.uniform(-0.01, 0.01)

        elif stype == "b check":
            # step in pore pressure reflecting cell pulse
            pore_kpa   = back + 0.95 * max(0.0, cell - back)
            axial_load = axial_load + random.uniform(-0.02, 0.02)
            disp_mm    = pos

        elif stype == "shear":
            # rising load proportional to displacement until safety threshold
            safety = float(getattr(sd, "safety_load_kN", 9999.0)) if sd else 9999.0
            slope  = 0.02  # kN per mm (sim)
            want   = min(safety * 0.98, slope * max(0.0, disp_mm))
            axial_load += (want - axial_load) * 0.2  # approach target
            pore_kpa = back
            disp_mm  = pos

        elif stype == "automated docking":
            threshold = float(getattr(sd, "load_threshold", 1.0)) if sd else 1.0
            # ramp toward threshold quickly
            axial_load += (threshold - axial_load) * 0.15
            pore_kpa = back
            disp_mm  = pos

        else:
            axial_load = max(0.0, axial_load + random.uniform(-0.01, 0.02))
            pore_kpa   = back + random.uniform(-0.1, 0.1)
            disp_mm    = pos

        # locals noise
        self._channels[0] = max(0.0, axial_load)
        self._channels[1] = pore_kpa
        self._channels[2] = disp_mm
        self._channels[3] = math.sin(_now() * 0.8) * 2 + random.uniform(-0.3, 0.3)
        self._channels[4] = math.cos(_now() * 0.6) * 2 + random.uniform(-0.3, 0.3)
        self._channels[5] = math.sin(_now() * 0.4) * 1 + random.uniform(-0.2, 0.2)
        self._channels[6] = random.uniform(-0.5, 0.5)
        self._channels[7] = random.uniform(-0.5, 0.5)
