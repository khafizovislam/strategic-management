"""Plain data classes shared by the data sources, the analysis and the UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum


class Status(str, Enum):
    GOOD = "good"
    WATCH = "watch"
    SERVICE = "service"
    INFO = "info"  # not measurable over OBD, reminder only

    @property
    def label(self) -> str:
        return {
            Status.GOOD: "Good",
            Status.WATCH: "Watch",
            Status.SERVICE: "Service",
            Status.INFO: "Reminder",
        }[self]


@dataclass
class ServiceRecord:
    km: int
    date: str  # ISO yyyy-mm-dd
    estimated: bool = False


@dataclass
class VehicleProfile:
    make: str = "My"
    model: str = "Car"
    year: int = 2018
    fuel: str = "petrol"  # petrol | diesel | hybrid
    engine_l: float = 1.6
    odometer_km: int = 80_000
    km_per_week: int = 250
    battery_installed: str = ""  # ISO date, "" if unknown
    service_log: dict[str, ServiceRecord] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return f"{self.make} {self.model}".strip()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VehicleProfile":
        d = dict(d)
        log = {k: ServiceRecord(**v) for k, v in d.pop("service_log", {}).items()}
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known}, service_log=log)


@dataclass
class Sample:
    """One reading of every sensor, roughly what an OBD poll cycle returns."""

    t: float  # seconds since engine start (negative = engine off, before start)
    speed_kmh: float
    rpm: float
    coolant_c: float
    intake_c: float
    voltage: float
    stft: float  # short-term fuel trim, %
    ltft: float  # long-term fuel trim, %
    maf_gs: float  # mass air flow, g/s
    load_pct: float
    throttle_pct: float
    o2_up_v: float  # upstream oxygen sensor, volts
    o2_down_v: float  # downstream oxygen sensor, volts
    misfires: int  # cumulative misfire count since start
    ambient_c: float


@dataclass
class TroubleCode:
    code: str
    description: str


@dataclass
class ComponentResult:
    id: str
    name: str
    icon: str  # flet icon name, e.g. "BATTERY_CHARGING_FULL"
    status: Status
    score: int
    summary: str
    details: list[str] = field(default_factory=list)
    action: str = ""
    measured: bool = True
    series_key: str | None = None  # which sample field to chart
    due_km: int | None = None
    due_date: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ComponentResult":
        d = dict(d)
        d["status"] = Status(d["status"])
        return cls(**d)


@dataclass
class MaintenanceTask:
    id: str
    name: str
    icon: str
    reason: str
    due_km: int
    due_date: str
    days_left: int
    km_left: int
    urgency: Status
    from_fault: bool = False


@dataclass
class Report:
    id: str
    created_at: str  # ISO datetime
    source: str  # "simulation: Healthy car" or adapter name
    odometer_km: int
    duration_s: int
    distance_km: float
    avg_speed_kmh: float
    max_speed_kmh: float
    fuel_l_per_100km: float
    overall: int
    components: list[ComponentResult]
    trouble_codes: list[TroubleCode]
    series: dict[str, list[float]]  # downsampled sensor traces for charts

    @property
    def created(self) -> datetime:
        return datetime.fromisoformat(self.created_at)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["components"] = [c.to_dict() for c in self.components]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Report":
        d = dict(d)
        d["components"] = [ComponentResult.from_dict(c) for c in d["components"]]
        d["trouble_codes"] = [TroubleCode(**c) for c in d["trouble_codes"]]
        return cls(**d)


def today() -> date:
    return date.today()
