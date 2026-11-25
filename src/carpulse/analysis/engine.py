"""Turns a recorded drive into a full Report."""

from __future__ import annotations

import statistics as st
import uuid
from datetime import datetime

from ..models import Report, Sample, Status, TroubleCode, VehicleProfile
from . import components as c
from .maintenance import SERVICE_ITEMS, build_plan, schedule_components

SERIES = ["speed_kmh", "rpm", "coolant_c", "voltage", "trim", "maf_gs", "o2_up_v", "o2_down_v"]


def analyze(samples: list[Sample], codes: list[TroubleCode], profile: VehicleProfile,
            source: str) -> Report:
    measured = [
        c.engine_codes(codes),
        c.battery(samples, profile),
        c.charging(samples),
        c.cooling(samples),
        c.thermostat(samples),
        c.fuel_system(samples),
        c.air_intake(samples, profile),
        c.ignition(samples),
        c.oxygen_sensors(samples),
        c.catalyst(samples),
    ]
    plan = build_plan(profile, measured)
    results = measured + schedule_components(profile, plan)

    # attach the next service due to every component that has one
    by_component = {}
    item_comp = {i.id: i.component for i in SERVICE_ITEMS}
    for t in plan:
        comp = item_comp.get(t.id) or (t.id[4:] if t.id.startswith("fix_") else None)
        if comp and comp not in by_component:
            by_component[comp] = t
    for r in results:
        if r.id in by_component and r.due_date is None:
            r.due_km, r.due_date = by_component[r.id].due_km, by_component[r.id].due_date

    run = [s for s in samples if s.t >= 0]
    distance = sum(s.speed_kmh for s in run) / 3600
    moving = [s.speed_kmh for s in run if s.speed_kmh > 3]
    fuel_l = sum(s.maf_gs / 14.7 / 745 for s in run)  # g air -> g fuel -> litres
    return Report(
        id=uuid.uuid4().hex[:12],
        created_at=datetime.now().isoformat(timespec="seconds"),
        source=source,
        odometer_km=profile.odometer_km,
        duration_s=len(run),
        distance_km=round(distance, 2),
        avg_speed_kmh=round(st.mean(moving), 1) if moving else 0,
        max_speed_kmh=round(max(moving), 1) if moving else 0,
        fuel_l_per_100km=round(fuel_l / distance * 100, 1) if distance > 0.1 else 0,
        overall=overall_score(results),
        components=results,
        trouble_codes=codes,
        series=_series(run),
    )


def overall_score(results) -> int:
    scored = [r for r in results if r.status != Status.INFO]
    weights = {"engine": 2.0}
    total = sum(r.score * weights.get(r.id, 1.0) for r in scored)
    mean = total / sum(weights.get(r.id, 1.0) for r in scored)
    n_service = sum(r.status == Status.SERVICE for r in scored)
    n_watch = sum(r.status == Status.WATCH for r in scored)
    if n_service:
        mean = min(mean, 74 - 6 * (n_service - 1))
    elif n_watch:
        mean = min(mean, 89 - 2 * (n_watch - 1))
    return int(round(max(5, mean)))


def _series(run: list[Sample], points: int = 100) -> dict[str, list[float]]:
    step = max(1, len(run) // points)
    picked = run[::step]
    out: dict[str, list[float]] = {}
    for key in SERIES:
        if key == "trim":
            out[key] = [round(s.stft + s.ltft, 1) for s in picked]
        else:
            out[key] = [getattr(s, key) for s in picked]
    return out
