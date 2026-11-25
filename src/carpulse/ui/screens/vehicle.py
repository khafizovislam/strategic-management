"""First-launch welcome screen and the vehicle settings screen (same form)."""

from __future__ import annotations

from datetime import date, timedelta

import flet as ft

from ...models import ServiceRecord, VehicleProfile
from .. import theme as t
from .. import widgets as w
from ..app import Screen


def _field(label: str, value: str = "", hint: str = "", number: bool = False,
           suffix: str = "", expand: bool = True) -> ft.TextField:
    return ft.TextField(
        label=label, value=value, hint_text=hint, expand=expand,
        keyboard_type=ft.KeyboardType.NUMBER if number else ft.KeyboardType.TEXT,
        suffix=ft.Text(suffix, color=t.MUTED) if suffix else None,
        border_radius=14, filled=True, fill_color="#F8FAFC", border_color=t.BORDER,
        focused_border_color=t.PRIMARY, label_style=ft.TextStyle(color=t.MUTED),
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=14),
    )


def _parse_date(value: str) -> date:
    d, m, y = value.strip().replace("/", ".").replace("-", ".").split(".")
    return date(int(y), int(m), int(d))


class VehicleForm:
    def __init__(self, profile: VehicleProfile | None):
        p = profile or VehicleProfile(make="", model="", odometer_km=0)
        oil = p.service_log.get("oil")
        battery_age = ""
        if p.battery_installed:
            years = (date.today() - date.fromisoformat(p.battery_installed)).days / 365.25
            battery_age = f"{years:.1f}".rstrip("0").rstrip(".")
        self.base = p
        self.make = _field("Make", p.make, "e.g. Toyota")
        self.model = _field("Model", p.model, "e.g. Corolla")
        self.year = _field("Year", str(p.year) if profile else "", "2018", number=True)
        self.engine = _field("Engine size", f"{p.engine_l:g}", "1.6", number=True, suffix="L")
        self.fuel = ft.Dropdown(
            label="Fuel", value=p.fuel, expand=True, border_radius=14, filled=True,
            fill_color="#F8FAFC", border_color=t.BORDER, focused_border_color=t.PRIMARY,
            options=[ft.DropdownOption(key="petrol", text="Petrol"),
                     ft.DropdownOption(key="diesel", text="Diesel"),
                     ft.DropdownOption(key="hybrid", text="Hybrid")],
        )
        self.odometer = _field("Odometer", str(p.odometer_km) if profile else "", "84300",
                               number=True, suffix="km")
        self.weekly = _field("Typical driving", str(p.km_per_week), "250", number=True,
                             suffix="km/week")
        self.oil_km = _field("Last oil change", str(oil.km) if oil and not oil.estimated else "",
                             "optional", number=True, suffix="km")
        self.oil_date = _field("Oil change date", _dmy(oil.date) if oil and not oil.estimated else "",
                               "dd.mm.yyyy")
        self.battery = _field("Battery age", battery_age, "optional", number=True, suffix="years")
        self.error = w.text("", 13, color=t.DANGER, visible=False)

    def controls(self) -> list[ft.Control]:
        def group(title: str, rows: list[ft.Control]) -> ft.Control:
            return w.card(ft.Column([w.text(title, 14, ft.FontWeight.W_700, t.MUTED)] + rows, spacing=12))
        return [
            group("Your car", [ft.Row([self.make, self.model], spacing=10),
                               ft.Row([self.year, self.engine], spacing=10), self.fuel]),
            group("Usage", [self.odometer, self.weekly]),
            group("Service history", [ft.Row([self.oil_km, self.oil_date], spacing=10), self.battery,
                                      w.text("Leave blank if you don't know. CarPulse will estimate.",
                                             12, color=t.MUTED)]),
            self.error,
        ]

    def parse(self) -> VehicleProfile | None:
        def num(field: ft.TextField, kind=int, required=True):
            raw = (field.value or "").strip().replace(" ", "").replace(",", ".")
            if not raw:
                if required:
                    raise ValueError(f"Please fill in “{field.label}”.")
                return None
            try:
                return kind(float(raw)) if kind is int else kind(raw)
            except ValueError:
                raise ValueError(f"“{field.label}” must be a number.")

        try:
            if not (self.make.value or "").strip():
                raise ValueError("Please fill in “Make”.")
            log = dict(self.base.service_log)
            oil_km = num(self.oil_km, required=False)
            if oil_km is not None or (self.oil_date.value or "").strip():
                try:
                    oil_day = _parse_date(self.oil_date.value) if self.oil_date.value.strip() else date.today()
                except (ValueError, AttributeError):
                    raise ValueError("Oil change date must look like 25.11.2026.")
                odometer = num(self.odometer)
                log["oil"] = ServiceRecord(oil_km if oil_km is not None else odometer, oil_day.isoformat())
            battery_years = num(self.battery, float, required=False)
            installed = ""
            if battery_years is not None:
                installed = (date.today() - timedelta(days=battery_years * 365.25)).isoformat()
            profile = VehicleProfile(
                make=self.make.value.strip(), model=(self.model.value or "").strip(),
                year=num(self.year), fuel=self.fuel.value or "petrol",
                engine_l=num(self.engine, float), odometer_km=num(self.odometer),
                km_per_week=num(self.weekly), battery_installed=installed, service_log=log,
            )
            if not 0.6 <= profile.engine_l <= 8:
                raise ValueError("Engine size should be between 0.6 and 8 litres.")
            self.error.visible = False
            return profile
        except ValueError as exc:
            self.error.value = str(exc)
            self.error.visible = True
            self.error.update()
            return None


def _dmy(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


class OnboardingScreen(Screen):
    def build(self) -> ft.Control:
        self.form = VehicleForm(None)
        hero = ft.Container(
            ft.Column([
                ft.Container(ft.Icon(ft.Icons.DIRECTIONS_CAR_ROUNDED, color="white", size=40),
                             width=76, height=76, border_radius=24, alignment=ft.Alignment.CENTER,
                             bgcolor=ft.Colors.with_opacity(0.18, "white")),
                w.text("Welcome to CarPulse", 28, ft.FontWeight.W_800, "white"),
                w.text("Check your car's health with one 5-minute drive. "
                       "First, tell us about your car.", 15, color="#E0E7FF"),
            ], spacing=12),
            gradient=t.HERO_GRADIENT, padding=ft.Padding.only(left=24, right=24, top=36, bottom=32),
            border_radius=ft.BorderRadius.only(bottom_left=32, bottom_right=32),
        )
        self.items = w.reveal(self.form.controls() + [
            w.primary_button("Get started", "ARROW_FORWARD_ROUNDED", self.save),
            ft.Container(height=24),
        ])
        return ft.Column([
            hero,
            ft.Container(ft.Column(self.items, spacing=14),
                         padding=ft.Padding.symmetric(horizontal=t.GUTTER, vertical=16)),
        ], scroll=ft.ScrollMode.AUTO, spacing=0, expand=True)

    async def did_show(self):
        await w.play_reveal(self.items)

    def save(self, e):
        profile = self.form.parse()
        if profile:
            self.app.store.set_profile(profile)
            from .home import HomeScreen
            self.app.go(HomeScreen)


class VehicleScreen(Screen):
    def build(self) -> ft.Control:
        self.form = VehicleForm(self.app.profile)
        self.items = w.reveal(self.form.controls() + [
            w.primary_button("Save changes", "CHECK_ROUNDED", self.save),
            w.secondary_button("Reset all data", "DELETE_OUTLINE_ROUNDED", self.confirm_reset),
            ft.Container(height=24),
        ])
        return ft.Column([
            header("Your vehicle", self.back),
            ft.Container(ft.Column(self.items, spacing=14),
                         padding=ft.Padding.symmetric(horizontal=t.GUTTER)),
        ], scroll=ft.ScrollMode.AUTO, spacing=8, expand=True)

    async def did_show(self):
        await w.play_reveal(self.items, 0.04)

    def back(self, e=None):
        from .home import HomeScreen
        self.app.go(HomeScreen)

    def save(self, e):
        profile = self.form.parse()
        if profile:
            self.app.store.set_profile(profile)
            self.app.toast("Vehicle saved")
            self.back()

    def confirm_reset(self, e):
        def do_reset(_):
            self.page.pop_dialog()
            self.app.store.reset()
            self.app.current_report = None
            self.app.go(OnboardingScreen)

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Reset all data?"),
            content=ft.Text("This deletes your vehicle and every saved report from this device."),
            actions=[ft.TextButton("Cancel", on_click=lambda _: self.page.pop_dialog()),
                     ft.TextButton("Reset", on_click=do_reset,
                                   style=ft.ButtonStyle(color=t.DANGER))],
            shape=ft.RoundedRectangleBorder(radius=20), bgcolor=t.CARD,
        ))


def header(title: str, on_back, subtitle: str | None = None,
           trailing: ft.Control | None = None) -> ft.Control:
    left = ft.Container(ft.Icon(ft.Icons.ARROW_BACK_ROUNDED, color=t.TEXT), width=44, height=44,
                        border_radius=14, bgcolor=t.CARD, alignment=ft.Alignment.CENTER,
                        on_click=on_back, shadow=t.SOFT_SHADOW)
    col = [w.text(title, 22, ft.FontWeight.W_800)]
    if subtitle:
        col.append(w.text(subtitle, 13, color=t.MUTED))
    row = [left, ft.Column(col, spacing=0, expand=True)]
    if trailing:
        row.append(trailing)
    return ft.Container(ft.Row(row, spacing=14),
                        padding=ft.Padding.only(left=t.GUTTER, right=t.GUTTER, top=12, bottom=8))
