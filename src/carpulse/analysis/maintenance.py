"""Maintenance schedule: standard intervals adjusted by the latest check results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..models import ComponentResult, MaintenanceTask, ServiceRecord, Status, VehicleProfile


@dataclass(frozen=True)
class ServiceItem:
    id: str
    name: str
    icon: str
    interval_km: int | None
    interval_months: int | None
    component: str | None = None  # linked ComponentResult id
    note: str = ""


SERVICE_ITEMS: list[ServiceItem] = [
    ServiceItem("oil", "Engine oil & filter", "OIL_BARREL", 10_000, 12, "oil",
                "Fresh oil protects the engine from wear."),
    ServiceItem("air_filter", "Air filter", "FILTER_ALT", 30_000, 24, "air"),
    ServiceItem("spark_plugs", "Spark plugs", "OFFLINE_BOLT", 60_000, 48, "ignition"),
    ServiceItem("coolant", "Coolant", "WATER_DROP", 100_000, 60),
    ServiceItem("battery", "Battery", "BATTERY_CHARGING_FULL", None, 60, "battery"),
    ServiceItem("brake_pads", "Brake pads & discs", "DISC_FULL", 20_000, 12, "brakes",
                "Inspect thickness; replace when below 3 mm."),
    ServiceItem("brake_fluid", "Brake fluid", "OPACITY", None, 24, "brakes"),
    ServiceItem("tyres", "Tyres: rotate & inspect", "TIRE_REPAIR", 10_000, 12, "tyres",
                "Check tread (min. 1.6 mm, 3 mm recommended) and pressure."),
    ServiceItem("gearbox", "Gearbox oil", "SETTINGS", 60_000, 48),
    ServiceItem("timing_belt", "Timing belt", "SYNC", 120_000, 72, note="Check your manual: some engines use a chain."),
]

# Task names for faults that need a repair rather than a regular service.
FIX_NAMES = {
    "engine": "Diagnose fault codes",
    "charging": "Repair charging system",
    "cooling": "Check radiator fan & coolant",
    "thermostat": "Replace thermostat",
    "fuel": "Fix air-fuel mixture problem",
    "o2": "Replace oxygen sensor",
    "catalyst": "Check catalytic converter",
}

# Components that OBD cannot measure; their condition comes from the schedule only.
UNMEASURED = {
    "oil": ("Engine oil", "OIL_BARREL", ["oil"]),
    "brakes": ("Brakes", "DISC_FULL", ["brake_pads", "brake_fluid"]),
    "tyres": ("Tyres", "TIRE_REPAIR", ["tyres"]),
}


def last_service(item: ServiceItem, profile: VehicleProfile, today: date) -> ServiceRecord:
    if item.id in profile.service_log:
        return profile.service_log[item.id]
    if item.id == "battery" and profile.battery_installed:
        return ServiceRecord(profile.odometer_km, profile.battery_installed)
    # Unknown: assume it was done at the last regular interval.
    if item.interval_km:
        km = profile.odometer_km // item.interval_km * item.interval_km
        # assume it was done on schedule, so time and distance used up match
        used = (profile.odometer_km - km) / item.interval_km
        when = today - timedelta(days=used * (item.interval_months or 12) * 30.44)
    else:
        km = profile.odometer_km
        when = today - timedelta(days=item.interval_months * 30.4 / 2)  # assume halfway
    return ServiceRecord(int(km), when.isoformat(), estimated=True)


def build_plan(profile: VehicleProfile, components: list[ComponentResult],
               today: date | None = None, report_date: str | None = None) -> list[MaintenanceTask]:
    """`report_date` (ISO) is when `components` were measured; work logged on or after
    that date counts as having fixed the faults found then."""
    today = today or date.today()

    def fixed_since_report(item_id: str) -> bool:
        rec = profile.service_log.get(item_id)
        return bool(rec and not rec.estimated and report_date and rec.date >= report_date[:10])

    by_id = {c.id: c for c in components}
    weekly = max(profile.km_per_week, 1)
    tasks: list[MaintenanceTask] = []

    for item in SERVICE_ITEMS:
        last = last_service(item, profile, today)
        options = []
        due_km = None
        if item.interval_km:
            due_km = last.km + item.interval_km
            options.append((due_km - profile.odometer_km) / weekly * 7)
        if item.interval_months:
            due_by_time = date.fromisoformat(last.date) + timedelta(days=item.interval_months * 30.44)
            options.append((due_by_time - today).days)
        days = int(min(options))
        reason = "Regular interval"
        if last.estimated:
            reason += " (last service date estimated: add it to improve accuracy)"
        comp = by_id.get(item.component or "")
        from_fault = False
        if (comp and comp.measured and comp.status in (Status.SERVICE, Status.WATCH)
                and not fixed_since_report(item.id)):
            limit = 7 if comp.status == Status.SERVICE else 30
            if days > limit:
                days, reason, from_fault = limit, comp.action or comp.summary, True
        if due_km is None:
            due_km = profile.odometer_km + int(days / 7 * weekly)
        km_left = int(days / 7 * weekly) if from_fault else due_km - profile.odometer_km
        tasks.append(_task(item.id, item.name, item.icon, reason, profile, today, days, km_left, from_fault))

    # Faults that are not covered by a regular service item get their own task.
    covered = {i.component for i in SERVICE_ITEMS}
    for c in components:
        if (c.measured and c.status in (Status.SERVICE, Status.WATCH) and c.id not in covered
                and c.action and not fixed_since_report(f"fix_{c.id}")):
            days = 7 if c.status == Status.SERVICE else 30
            name = FIX_NAMES.get(c.id, c.name)
            tasks.append(_task(f"fix_{c.id}", name, c.icon, c.action, profile,
                               today, days, int(days / 7 * weekly), True))

    tasks.sort(key=lambda t: (t.days_left, -t.from_fault))
    return tasks


def _task(id_, name, icon, reason, profile, today, days, km_left, from_fault) -> MaintenanceTask:
    if days <= 14 or km_left <= 500:
        urgency = Status.SERVICE
    elif days <= 60 or km_left <= 1_500:
        urgency = Status.WATCH
    else:
        urgency = Status.GOOD
    return MaintenanceTask(
        id=id_, name=name, icon=icon, reason=reason,
        due_km=profile.odometer_km + max(km_left, 0),
        due_date=(today + timedelta(days=max(days, 0))).isoformat(),
        days_left=days, km_left=km_left, urgency=urgency, from_fault=from_fault,
    )


def schedule_components(profile: VehicleProfile, plan: list[MaintenanceTask]) -> list[ComponentResult]:
    """Results for components OBD can't see (oil, brakes, tyres), from the schedule."""
    by_id = {t.id: t for t in plan}
    out = []
    for cid, (name, icon, items) in UNMEASURED.items():
        tasks = [by_id[i] for i in items if i in by_id]
        soonest = min(tasks, key=lambda t: t.days_left)
        score = max(5, min(100, 40 + soonest.days_left // 3))
        status = {Status.SERVICE: Status.SERVICE, Status.WATCH: Status.WATCH}.get(soonest.urgency, Status.GOOD)
        summary = (f"{soonest.name} due now." if soonest.urgency == Status.SERVICE
                   else f"Next: {soonest.name.lower()}.")
        out.append(ComponentResult(
            cid, name, icon, status, score, summary,
            ["Not measurable over OBD. Based on mileage and time since the last service."]
            + [f"{t.name}: due at {t.due_km:,} km or {t.due_date}".replace(",", " ") for t in tasks],
            measured=False, due_km=soonest.due_km, due_date=soonest.due_date,
        ))
    return out
