"""Saves the vehicle profile and past reports as a JSON file on the device."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Report, ServiceRecord, VehicleProfile

MAX_REPORTS = 30


def data_dir() -> Path:
    # Flet sets this inside packaged iOS/Android apps; fall back to the home folder.
    base = os.environ.get("FLET_APP_STORAGE_DATA") or os.path.join(Path.home(), ".carpulse")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "carpulse.json"
        self.profile: VehicleProfile | None = None
        self.reports: list[Report] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("profile"):
                self.profile = VehicleProfile.from_dict(raw["profile"])
            self.reports = [Report.from_dict(r) for r in raw.get("reports", [])]
        except (ValueError, KeyError, TypeError):
            # Corrupt or old-format file: keep a backup and start fresh.
            self.path.replace(self.path.with_suffix(".bak"))

    def save(self) -> None:
        data = {
            "profile": self.profile.to_dict() if self.profile else None,
            "reports": [r.to_dict() for r in self.reports[:MAX_REPORTS]],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def latest(self) -> Report | None:
        return self.reports[0] if self.reports else None

    def add_report(self, report: Report) -> None:
        self.reports.insert(0, report)
        self.save()

    def set_profile(self, profile: VehicleProfile) -> None:
        self.profile = profile
        self.save()

    def mark_service_done(self, item_id: str, km: int, when: str) -> None:
        assert self.profile is not None
        self.profile.service_log[item_id] = ServiceRecord(km, when)
        if item_id == "battery":
            self.profile.battery_installed = when
        self.save()

    def reset(self) -> None:
        self.profile = None
        self.reports = []
        if self.path.exists():
            self.path.unlink()
