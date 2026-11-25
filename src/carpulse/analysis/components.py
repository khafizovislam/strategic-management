"""One scoring function per component, working only from recorded OBD samples.

Every function returns a ComponentResult with a 0-100 score, a status and a
plain-language explanation. Thresholds are typical values for petrol cars.
"""

from __future__ import annotations

import statistics as st
from datetime import date

from ..models import ComponentResult, Sample, Status, TroubleCode, VehicleProfile
from .. import units as u


def status_for(score: float) -> Status:
    if score >= 80:
        return Status.GOOD
    if score >= 55:
        return Status.WATCH
    return Status.SERVICE


def _clamp(x: float, lo: float = 0, hi: float = 100) -> int:
    return int(round(max(lo, min(hi, x))))


def _lerp_score(value: float, good: float, bad: float) -> int:
    """100 at `good` (or better), 30 at `bad`, linear in between, can go below."""
    if good == bad:
        return 100
    frac = (value - good) / (bad - good)
    return _clamp(100 - 70 * max(0.0, frac), 5, 100)


def _running(samples: list[Sample]) -> list[Sample]:
    return [s for s in samples if s.t > 0 and s.rpm > 300]


def _warm_closed_loop(samples: list[Sample]) -> list[Sample]:
    return [s for s in _running(samples) if s.coolant_c >= 70 and s.stft != 0 and s.t > 20]


# --------------------------------------------------------------------- engine
def engine_codes(codes: list[TroubleCode]) -> ComponentResult:
    if not codes:
        return ComponentResult(
            "engine", "Engine & fault codes", "CAR_REPAIR", Status.GOOD, 100,
            "No fault codes stored. Check-engine light is off.",
            ["The engine computer reported no stored or pending trouble codes."],
        )
    score = 60 if len(codes) == 1 else 40
    return ComponentResult(
        "engine", "Engine & fault codes", "CAR_REPAIR", status_for(score), score,
        f"{len(codes)} fault code{'s' if len(codes) > 1 else ''} stored. Check-engine light is on.",
        [f"{c.code}: {c.description}" for c in codes],
        action="Have a mechanic read and clear the codes after the repair.",
    )


# -------------------------------------------------------------------- battery
def battery(samples: list[Sample], profile: VehicleProfile) -> ComponentResult:
    rest = [s.voltage for s in samples if s.t < 0]
    crank = [s.voltage for s in samples if s.t == 0]
    rest_v = st.mean(rest) if rest else 12.6
    crank_v = min(crank) if crank else 10.5
    s_rest = _lerp_score(-rest_v, -12.55, -12.2)
    s_crank = _lerp_score(-crank_v, -10.2, -9.5)
    details = [f"Resting voltage: {u.volts(rest_v)} (healthy: 12.5 V or more)",
               f"Lowest voltage while starting: {u.volts(crank_v)} (healthy: above 10.0 V)"]
    age_years = None
    if profile.battery_installed:
        age_years = (date.today() - date.fromisoformat(profile.battery_installed)).days / 365.25
        details.append(f"Battery age: {age_years:.1f} years (typical life: 4–6 years)")
    s_age = 100 if age_years is None else _lerp_score(age_years, 4, 6.5)
    score = min(s_rest, s_crank, max(s_age, 60))
    if score >= 80:
        summary = "Battery holds charge well and starts the engine easily."
        action = ""
    elif s_crank < 80 or s_rest < 80:
        summary = "Battery is weak: low resting voltage and a deep dip when starting."
        action = "Test the battery and plan a replacement, especially before winter."
    else:
        summary = "Battery works but is getting old."
        action = "Have the battery tested at your next service."
    return ComponentResult("battery", "Battery", "BATTERY_CHARGING_FULL", status_for(score), score,
                           summary, details, action, series_key="voltage")


def charging(samples: list[Sample]) -> ComponentResult:
    run = [s.voltage for s in _running(samples) if s.t > 5]
    avg = st.mean(run) if run else 14.0
    low = min(run) if run else avg
    if avg > 15.0:
        score = _lerp_score(avg, 15.0, 15.4)
        summary = "Charging voltage is too high: the voltage regulator may be faulty."
    else:
        score = _lerp_score(-avg, -13.6, -13.1)
        summary = ("Alternator charges the battery normally." if score >= 80
                   else "Alternator is not charging the battery enough.")
    return ComponentResult(
        "charging", "Charging system", "ELECTRIC_BOLT", status_for(score), score, summary,
        [f"Average voltage while driving: {u.volts(avg)} (healthy: 13.6–14.7 V)",
         f"Lowest voltage while driving: {u.volts(low)}"],
        "" if score >= 80 else "Test the alternator, its belt and the battery cables.",
        series_key="voltage",
    )


# -------------------------------------------------------------------- cooling
def cooling(samples: list[Sample]) -> ComponentResult:
    run = _running(samples)
    max_c = max(s.coolant_c for s in run)
    end_idle = [s.coolant_c for s in run if s.t > 270]
    score = _lerp_score(max_c, 100, 106)
    details = [f"Highest coolant temperature: {u.celsius(max_c)} (normal: 85–100 °C)"]
    if end_idle:
        details.append(f"Temperature while idling at the end: {u.celsius(st.mean(end_idle))}")
    if score >= 80:
        summary = "Engine temperature stays in the normal range."
        action = ""
    else:
        summary = "Engine runs too hot at low speed: likely the radiator fan or low coolant."
        action = "Check the coolant level and radiator fan. Avoid long idling until fixed."
    return ComponentResult("cooling", "Cooling system", "WATER_DROP", status_for(score), score,
                           summary, details, action, series_key="coolant_c")


def thermostat(samples: list[Sample]) -> ComponentResult:
    run = _running(samples)
    max_c = max(s.coolant_c for s in run)
    reached = next((s.t for s in run if s.coolant_c >= 80), None)
    last = [s.coolant_c for s in run if s.t >= run[-1].t - 60]
    slope = (last[-1] - last[0]) / 60 if len(last) > 1 else 0
    details = [f"Highest coolant temperature: {u.celsius(max_c)}"]
    if reached is not None:
        details.append(f"Reached 80 °C after {u.duration(reached)} min (normal: within ~5 min)")
        score, summary, action = 100, "Engine warms up normally.", ""
    elif max_c >= 75 and slope > 0.08:
        score = 72
        summary = "Engine was still warming up when the drive ended."
        details.append("Repeat the check with a slightly longer drive to confirm.")
        action = "Re-test after a longer drive."
    else:
        score = min(50, _lerp_score(-max_c, -80, -60))
        summary = "Engine never reached normal temperature: thermostat is probably stuck open."
        details.append(f"Temperature stopped rising at about {u.celsius(last[-1])}.")
        action = "Replace the thermostat. A cold engine uses more fuel and wears faster."
    return ComponentResult("thermostat", "Thermostat", "THERMOSTAT", status_for(score), score,
                           summary, details, action, series_key="coolant_c")


# ---------------------------------------------------------------------- fuel
def _trims(samples: list[Sample]) -> tuple[float | None, float | None]:
    warm = _warm_closed_loop(samples)
    idle = [s.stft + s.ltft for s in warm if s.speed_kmh < 4]
    cruise = [s.stft + s.ltft for s in warm if s.speed_kmh > 60 and s.load_pct > 25]
    return (st.mean(idle) if idle else None, st.mean(cruise) if cruise else None)


def fuel_system(samples: list[Sample]) -> ComponentResult:
    idle, cruise = _trims(samples)
    vals = [v for v in (idle, cruise) if v is not None]
    if not vals:
        return ComponentResult("fuel", "Fuel system", "LOCAL_GAS_STATION", Status.INFO, 0,
                               "Not enough warm-engine data to judge fuelling.",
                               measured=False, series_key="trim")
    worst = max(vals, key=abs)
    score = _lerp_score(abs(worst), 8, 13)
    details = []
    if idle is not None:
        details.append(f"Total fuel trim at idle: {idle:+.1f} % (healthy: within ±8 %)")
    if cruise is not None:
        details.append(f"Total fuel trim at cruise: {cruise:+.1f} % (healthy: within ±8 %)")
    action = ""
    if score >= 80:
        summary = "Air-fuel mixture is well balanced."
    elif worst > 0 and idle is not None and cruise is not None and idle > cruise + 4:
        summary = "Engine runs lean mainly at idle: typical sign of a vacuum (air) leak."
        action = "Inspect vacuum hoses and the intake gasket for leaks."
    elif worst > 0 and idle is not None and cruise is not None and cruise > idle + 4:
        summary = "Engine runs lean mainly under load: air-flow sensor or fuel delivery issue."
        action = "Clean the air-flow (MAF) sensor and check fuel pressure."
    elif worst > 0:
        summary = "Engine runs lean: the computer is adding extra fuel."
        action = "Check for air leaks and fuel pressure."
    else:
        summary = "Engine runs rich: the computer is removing fuel."
        action = "Check injectors, the air filter and the oxygen sensor."
    return ComponentResult("fuel", "Fuel system", "LOCAL_GAS_STATION", status_for(score), score,
                           summary, details, action, series_key="trim")


def air_intake(samples: list[Sample], profile: VehicleProfile) -> ComponentResult:
    loaded = [s for s in _running(samples) if s.load_pct > 35 and s.rpm > 1200]
    if len(loaded) < 10:
        return ComponentResult("air", "Air intake & air-flow sensor", "AIR", Status.INFO, 0,
                               "Not enough data under load.", measured=False, series_key="maf_gs")
    # volumetric efficiency implied by the MAF reading vs the engine's reported load
    ratios = [s.maf_gs / (s.rpm / 60 * profile.engine_l / 2 * 1.2) / (s.load_pct / 100) for s in loaded]
    ratio = st.median(ratios)
    idle, cruise = _trims(samples)
    score = _lerp_score(-ratio, -0.9, -0.78)
    if cruise is not None and idle is not None and cruise > idle + 6:
        score = min(score, 50)
    details = [f"Measured air flow is {ratio * 100:.0f} % of what the engine load suggests (healthy: 90 % or more)",
               f"Peak air flow: {max(s.maf_gs for s in loaded):.1f} g/s"]
    if score >= 80:
        summary, action = "Air flow readings match the engine load.", ""
    else:
        summary = "Air-flow sensor reads low at higher speed: dirty sensor or clogged air filter."
        action = "Clean the MAF sensor with MAF cleaner and check the air filter."
    return ComponentResult("air", "Air intake & air-flow sensor", "AIR", status_for(score), score,
                           summary, details, action, series_key="maf_gs")


# ------------------------------------------------------------------- ignition
def ignition(samples: list[Sample]) -> ComponentResult:
    run = _running(samples)
    revs = sum(s.rpm / 60 for s in run)
    mis = run[-1].misfires if run else 0
    per_k = mis / max(revs / 1000, 1)
    idle = [s.rpm for s in run if s.speed_kmh < 4 and s.coolant_c > 60]
    rough = st.pstdev(idle) if len(idle) > 5 else 0
    score = min(_lerp_score(per_k, 1.0, 6.0), _lerp_score(rough, 30, 70))
    details = [f"Misfires: {mis} in {u.num(revs)} engine revolutions ({per_k:.1f} per 1000; healthy: under 1)",
               f"Idle speed variation: ±{rough:.0f} rpm (healthy: under ±30 rpm)"]
    if score >= 80:
        summary, action = "Smooth idle and no misfires.", ""
    else:
        summary = "Engine misfires and idles roughly: worn spark plug or ignition coil."
        action = "Replace spark plugs and test the ignition coils. Misfires can damage the catalyst."
    return ComponentResult("ignition", "Ignition & spark plugs", "OFFLINE_BOLT", status_for(score), score,
                           summary, details, action, series_key="rpm")


# ------------------------------------------------------------------- exhaust
def oxygen_sensors(samples: list[Sample]) -> ComponentResult:
    warm = _warm_closed_loop(samples)
    if len(warm) < 30:
        return ComponentResult("o2", "Oxygen sensors", "SENSORS", Status.INFO, 0,
                               "Engine didn't warm up enough to test the sensors.",
                               ["Repeat the drive once the engine reaches normal temperature."],
                               measured=False, series_key="o2_up_v")
    ups = [s.o2_up_v for s in warm]
    crossings = sum((a - 0.45) * (b - 0.45) < 0 for a, b in zip(ups, ups[1:]))
    per_min = crossings / (len(warm) / 60)
    lo, hi = min(ups), max(ups)
    score = min(_lerp_score(-per_min, -20, -6), _lerp_score(lo, 0.2, 0.35), _lerp_score(-hi, -0.7, -0.55))
    return ComponentResult(
        "o2", "Oxygen sensors", "SENSORS", status_for(score), score,
        "Front oxygen sensor responds quickly." if score >= 80 else "Front oxygen sensor responds slowly.",
        [f"Front sensor switches {per_min:.0f} times per minute (healthy: 20 or more)",
         f"Voltage range: {lo:.2f}–{hi:.2f} V (healthy: below 0.2 V to above 0.7 V)"],
        "" if score >= 80 else "Replace the front oxygen sensor.",
        series_key="o2_up_v",
    )


def catalyst(samples: list[Sample]) -> ComponentResult:
    warm = [s for s in _warm_closed_loop(samples) if s.t > 60]
    if len(warm) < 30:
        return ComponentResult("catalyst", "Catalytic converter", "CO2", Status.INFO, 0,
                               "Engine didn't warm up enough to test the catalyst.",
                               ["Repeat the drive once the engine reaches normal temperature."],
                               measured=False, series_key="o2_down_v")
    up = st.pstdev(s.o2_up_v for s in warm)
    down = st.pstdev(s.o2_down_v for s in warm)
    ratio = down / max(up, 0.01)
    score = _lerp_score(ratio, 0.3, 0.7)
    return ComponentResult(
        "catalyst", "Catalytic converter", "CO2", status_for(score), score,
        "Catalyst cleans the exhaust efficiently." if score >= 80
        else "Catalyst efficiency is low: rear sensor copies the front sensor.",
        [f"Rear/front oxygen-sensor activity ratio: {ratio:.2f} (healthy: below 0.3)"],
        "" if score >= 80 else "Have the catalytic converter checked. Fix any misfires first.",
        series_key="o2_down_v",
    )
