"""Each simulated fault must be detected, and a healthy car must come out clean."""

import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carpulse.analysis import analyze, build_plan  # noqa: E402
from carpulse.models import Status, VehicleProfile  # noqa: E402
from carpulse.sources import VirtualCar  # noqa: E402
from carpulse.storage import Store  # noqa: E402

PROFILE = VehicleProfile(make="Test", model="Car", odometer_km=84_300, battery_installed="2024-01-01")

# scenario -> component that must be flagged as needing service
EXPECTED = {
    "battery": "battery",
    "alternator": "charging",
    "thermostat": "thermostat",
    "overheat": "cooling",
    "vacuum": "fuel",
    "maf": "air",
    "misfire": "ignition",
    "catalyst": "catalyst",
}


def run(scenario: str, seed: int):
    car = VirtualCar(scenario, seed=seed)
    codes = asyncio.run(car.read_trouble_codes())
    return analyze(car.samples(), codes, PROFILE, car.name)


@pytest.mark.parametrize("seed", range(8))
def test_healthy_car_is_clean(seed):
    report = run("healthy", seed)
    flagged = [c.id for c in report.components if c.measured and c.status != Status.GOOD]
    assert flagged == []
    assert report.overall >= 90


@pytest.mark.parametrize("scenario,component", EXPECTED.items())
@pytest.mark.parametrize("seed", range(5))
def test_fault_is_detected(scenario, component, seed):
    report = run(scenario, seed)
    by_id = {c.id: c for c in report.components}
    assert by_id[component].status == Status.SERVICE, by_id[component]
    assert report.overall < 80
    # every other measured component that was flagged must be explained by the same fault
    unrelated = {c.id for c in report.components
                 if c.measured and c.status == Status.SERVICE} - {component, "engine", "fuel", "air", "ignition"}
    assert unrelated == set()


@pytest.mark.parametrize("scenario,component", EXPECTED.items())
def test_fault_puts_a_task_at_the_top_of_the_plan(scenario, component):
    report = run(scenario, 0)
    plan = build_plan(PROFILE, report.components)
    assert plan[0].days_left <= 7
    assert plan[0].urgency == Status.SERVICE


def test_estimated_schedule_is_not_absurdly_overdue():
    plan = build_plan(PROFILE, run("healthy", 0).components, today=date(2026, 11, 25))
    assert all(t.days_left > -30 for t in plan), [(t.name, t.days_left) for t in plan]


def test_report_round_trips_through_storage(tmp_path):
    store = Store(tmp_path / "data.json")
    store.set_profile(PROFILE)
    report = run("misfire", 1)
    store.add_report(report)
    again = Store(tmp_path / "data.json")
    assert again.profile.title == "Test Car"
    assert again.latest.to_dict() == report.to_dict()


def test_marking_work_done_clears_it_from_the_plan(tmp_path):
    store = Store(tmp_path / "data.json")
    store.set_profile(VehicleProfile.from_dict(PROFILE.to_dict()))
    report = run("misfire", 0)
    store.add_report(report)
    plan = build_plan(store.profile, report.components, report_date=report.created_at)
    assert plan[0].id in ("spark_plugs", "fix_engine") and plan[0].days_left <= 7

    for task_id in ("spark_plugs", "fix_engine"):
        store.mark_service_done(task_id, store.profile.odometer_km, date.today().isoformat())
    plan = build_plan(store.profile, report.components, report_date=report.created_at)
    ids = [t.id for t in plan]
    assert "fix_engine" not in ids
    spark = next(t for t in plan if t.id == "spark_plugs")
    assert spark.km_left == 60_000 and not spark.from_fault
