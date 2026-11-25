"""A virtual car that produces realistic OBD readings for a scripted 5-minute drive.

The drive goes: engine off -> cold start -> idle -> two stop-and-go city blocks
-> hard acceleration -> highway cruise -> slowing down -> city -> idle.
Each scenario injects one or more faults so every kind of report can be shown.
"""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field, replace
from typing import AsyncIterator

from ..models import Sample, TroubleCode
from .base import DRIVE_SECONDS


@dataclass(frozen=True)
class Faults:
    rest_v: float = 12.65  # battery voltage with the engine off
    crank_v: float = 10.6  # lowest voltage while cranking
    charge_v: float = 14.2  # voltage while the alternator charges
    thermostat_stuck_open: bool = False
    cooling_fault: bool = False  # weak fan / low coolant: overheats at low speed
    vacuum_leak: float = 0.0  # extra lean % at idle
    maf_underread: float = 0.0  # fraction the MAF under-reads at high airflow
    misfire_rate: float = 0.0  # misfires per 1000 revolutions at idle
    worn_catalyst: bool = False
    codes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    icon: str
    faults: Faults = field(default_factory=Faults)


SCENARIOS: dict[str, Scenario] = {
    s.id: s
    for s in [
        Scenario("healthy", "Healthy car", "Everything works as it should.", "VERIFIED"),
        Scenario(
            "battery",
            "Weak battery",
            "Old battery that struggles to start the engine.",
            "BATTERY_ALERT",
            Faults(rest_v=12.18, crank_v=9.3),
        ),
        Scenario(
            "alternator",
            "Failing alternator",
            "The battery is not being charged properly.",
            "ELECTRIC_BOLT",
            Faults(charge_v=13.0, codes=(("P0562", "System voltage low"),)),
        ),
        Scenario(
            "thermostat",
            "Thermostat stuck open",
            "Engine never reaches its normal temperature.",
            "THERMOSTAT",
            Faults(
                thermostat_stuck_open=True,
                codes=(("P0128", "Coolant temperature below thermostat regulating temperature"),),
            ),
        ),
        Scenario(
            "overheat",
            "Cooling problem",
            "Weak radiator fan: engine runs hot in traffic.",
            "DEVICE_THERMOSTAT",
            Faults(cooling_fault=True),
        ),
        Scenario(
            "vacuum",
            "Vacuum leak",
            "Unmetered air makes the engine run lean at idle.",
            "AIR",
            Faults(vacuum_leak=15.0, codes=(("P0171", "System too lean (bank 1)"),)),
        ),
        Scenario(
            "maf",
            "Dirty air-flow sensor",
            "Air-flow sensor under-reads at higher speed.",
            "FILTER_ALT",
            Faults(maf_underread=0.22),
        ),
        Scenario(
            "misfire",
            "Misfiring cylinder",
            "Worn spark plug or coil on cylinder 3.",
            "OFFLINE_BOLT",
            Faults(
                misfire_rate=30.0,
                codes=(
                    ("P0300", "Random/multiple cylinder misfire detected"),
                    ("P0303", "Cylinder 3 misfire detected"),
                ),
            ),
        ),
        Scenario(
            "catalyst",
            "Worn catalytic converter",
            "Catalyst no longer cleans the exhaust efficiently.",
            "CO2",
            Faults(
                worn_catalyst=True,
                codes=(("P0420", "Catalyst system efficiency below threshold (bank 1)"),),
            ),
        ),
        Scenario("random", "Surprise me", "One or two random faults, revealed in the report.", "CASINO"),
    ]
}

_FAULT_IDS = [k for k in SCENARIOS if k not in ("healthy", "random")]

# (time s, speed km/h) keyframes of the scripted drive
_ROUTE = [
    (0, 0), (30, 0),
    (40, 45), (55, 45), (63, 0), (70, 0),  # city block 1
    (80, 40), (95, 48), (103, 0), (110, 0),  # city block 2
    (125, 95),  # hard acceleration onto the highway
    (225, 95),  # cruise
    (245, 50), (262, 30), (275, 0),  # off the highway, city
    (300, 0),  # idle
]


def _route_speed(t: float) -> float:
    for (t0, v0), (t1, v1) in zip(_ROUTE, _ROUTE[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return 0.0


def _merge(a: Faults, b: Faults) -> Faults:
    base = Faults()
    out = {}
    for f in base.__dataclass_fields__:
        va, vb, v0 = getattr(a, f), getattr(b, f), getattr(base, f)
        if f == "codes":
            out[f] = va + vb
        else:
            out[f] = vb if vb != v0 else va
    return Faults(**out)


class VirtualCar:
    """DataSource implementation that simulates a car on the scripted route."""

    def __init__(self, scenario_id: str = "healthy", speedup: float = 10.0,
                 engine_l: float = 1.6, seed: int | None = None):
        self.rng = random.Random(seed)
        self.speedup = speedup
        self.engine_l = engine_l
        scenario = SCENARIOS[scenario_id]
        self.hidden: list[str] = []
        if scenario_id == "random":
            picks = self.rng.sample(_FAULT_IDS, self.rng.choice([1, 1, 2]))
            faults = Faults()
            for p in picks:
                faults = _merge(faults, SCENARIOS[p].faults)
            self.hidden = [SCENARIOS[p].name for p in picks]
            scenario = replace(scenario, faults=faults)
        self.scenario = scenario
        self.f = scenario.faults
        self.name = f"Simulation · {scenario.name}"
        if self.hidden:
            self.name += f" ({', '.join(self.hidden)})"

    async def connect(self) -> None:
        await asyncio.sleep(0.3 / max(self.speedup, 1) if self.speedup else 0)

    async def read_trouble_codes(self) -> list[TroubleCode]:
        return [TroubleCode(c, d) for c, d in dict(self.f.codes).items()]

    async def close(self) -> None:
        return None

    async def stream(self) -> AsyncIterator[Sample]:
        delay = 1.0 / self.speedup if self.speedup else 0.0
        for s in self.samples():
            yield s
            if delay:
                await asyncio.sleep(delay)

    # ------------------------------------------------------------------ physics
    def samples(self) -> list[Sample]:
        """Generate the whole drive at once (used directly by tests)."""
        rng, f = self.rng, self.f
        ambient = rng.uniform(8, 20)
        coolant = ambient + rng.uniform(4, 10)
        ltft_cell = 1.5 + rng.uniform(-1, 1)
        misfires = 0.0
        out: list[Sample] = []

        # engine off: resting battery voltage
        for t in (-3, -2, -1):
            out.append(Sample(t, 0, 0, coolant, ambient, f.rest_v + rng.gauss(0, 0.01),
                              0, ltft_cell, 0, 0, 0, 0.1, 0.1, 0, ambient))

        prev_v = 0.0
        for t in range(0, DRIVE_SECONDS):
            target = _route_speed(t)
            speed = max(0.0, target + (rng.gauss(0, 1.2) if target > 5 else 0))
            accel = speed - prev_v
            prev_v = speed

            # gearbox and engine speed
            hard = accel > 2.5
            bands = [15, 28, 42, 60, 80]
            if hard:
                bands = [b * 1.4 for b in bands]
            gear = 1 + sum(speed >= b for b in bands)
            ratios = {1: 110, 2: 62, 3: 42, 4: 32, 5: 26, 6: 22}
            idle_rpm = 780 + max(0.0, 60 - coolant) * 6
            if t == 0:
                rpm = 220.0  # cranking
            elif speed < 4:
                rpm = idle_rpm
            else:
                rpm = max(idle_rpm + 250, speed * ratios[gear])
            rpm += rng.gauss(0, 9)

            # driver input and load
            if speed < 4:
                throttle = rng.uniform(0, 1.5)
                load = 22 + rng.gauss(0, 1.5)
            elif accel >= -0.5:
                throttle = min(100, 6 + max(accel, 0) * 11 + speed * 0.17)
                load = min(100, 16 + throttle * 0.85 + rng.gauss(0, 2))
            else:  # coasting / braking, fuel cut
                throttle = 0.0
                load = 12 + rng.gauss(0, 1.5)

            # misfires roughen the idle
            if f.misfire_rate and t > 0:
                idle_factor = 1.0 if speed < 4 else 0.45
                misfires += rpm / 60 / 2 * f.misfire_rate / 1000 * idle_factor * rng.uniform(0.5, 1.5)
                rpm += rng.gauss(0, 55 if speed < 4 else 25)

            # air flow (true and as measured by the sensor)
            maf_true = rpm / 60 * self.engine_l / 2 * 1.2 * (load / 100) * 0.98 if t > 0 else 0
            maf = maf_true * (1 - f.maf_underread * min(1.0, maf_true / 22))

            # coolant temperature
            heat = 1.25 * (0.10 + 0.32 * load / 100 + 0.00004 * rpm)
            if f.thermostat_stuck_open:
                coolant += heat - 0.00275 * (coolant - ambient) * (1 + speed / 60)
            elif coolant < 88:
                coolant += heat
            else:
                target_c = 89.5
                if f.cooling_fault:
                    target_c = 93 + 16 * (1 - min(speed, 50) / 50)
                coolant += (target_c - coolant) * (0.06 if f.cooling_fault else 0.25)
            coolant += rng.gauss(0, 0.15)

            # charging system
            if t == 0:
                voltage = f.crank_v + rng.gauss(0, 0.05)
            else:
                cold_boost = 0.2 if coolant < 50 else 0.0
                idle_dip = 0.3 if (f.charge_v < 13.5 and speed < 4) else 0.0
                voltage = f.charge_v + cold_boost - idle_dip + rng.gauss(0, 0.05)

            # fuelling: lean faults push trims positive
            closed_loop = t > 20 and coolant > 40 and throttle < 85
            lean = 0.0
            if f.vacuum_leak and maf > 0:
                lean += f.vacuum_leak * min(1.0, 3.2 / max(maf, 0.1))
            if f.maf_underread and maf_true > 0:
                lean += 100 * (maf_true / max(maf, 0.1) - 1)
            required = 1.5 + lean
            if closed_loop:
                ltft_cell += (required - ltft_cell) / 6
                stft = required - ltft_cell + rng.gauss(0, 2.2)
            else:
                stft = 0.0
            ltft = ltft_cell + rng.gauss(0, 0.2)

            # oxygen sensors
            if t == 0:
                o2_up = 0.1
            elif accel < -0.5 and speed > 4:
                o2_up = 0.05 + rng.uniform(0, 0.05)  # fuel cut
            elif not closed_loop:
                o2_up = 0.75 + rng.gauss(0, 0.04)  # open loop, rich
            else:
                phase = math.sin(2 * math.pi * t / 2.3 + rng.uniform(-0.6, 0.6))
                o2_up = 0.45 + 0.37 * (1 if phase > 0 else -1) + rng.gauss(0, 0.04)
            cat_warm = t > 60 and coolant > 60
            if f.worn_catalyst or not cat_warm:
                o2_down = 0.45 + 0.8 * (o2_up - 0.45) + rng.gauss(0, 0.03)
            else:
                o2_down = 0.64 + rng.gauss(0, 0.025)

            intake = ambient + (10 if speed < 4 else 4) + rng.gauss(0, 0.3)

            out.append(Sample(
                t=t, speed_kmh=round(speed, 1), rpm=round(max(rpm, 0)), coolant_c=round(coolant, 1),
                intake_c=round(intake, 1), voltage=round(voltage, 2), stft=round(stft, 1),
                ltft=round(ltft, 1), maf_gs=round(maf, 2), load_pct=round(max(load, 0), 1),
                throttle_pct=round(throttle, 1), o2_up_v=round(min(max(o2_up, 0), 1), 3),
                o2_down_v=round(min(max(o2_down, 0), 1), 3), misfires=int(misfires),
                ambient_c=round(ambient, 1),
            ))
        return out
