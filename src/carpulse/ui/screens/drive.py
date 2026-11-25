"""Test setup (choose a simulated fault) and the live 5-minute drive screen."""

from __future__ import annotations

import asyncio
import time

import flet as ft

from ... import units as u
from ...analysis import analyze
from ...models import Sample
from ...sources import DRIVE_SECONDS, SCENARIOS, VirtualCar
from .. import theme as t
from .. import widgets as w
from ..app import Screen
from .vehicle import header

SPEEDS = [("1", "Real · 5 min"), ("10", "Fast · 30 s"), ("60", "Instant · 5 s")]


class TestSetupScreen(Screen):
    def build(self) -> ft.Control:
        self.selected = self.kwargs.get("scenario", "healthy")
        self.speed = "10"
        self.cards: dict[str, ft.Container] = {}
        rows = []
        ids = list(SCENARIOS)
        for i in range(0, len(ids), 2):
            rows.append(ft.Row([self._scenario_card(sid) for sid in ids[i:i + 2]], spacing=12))

        speed = ft.SegmentedButton(
            segments=[ft.Segment(value=v, label=ft.Text(label, size=13)) for v, label in SPEEDS],
            selected=[self.speed], allow_empty_selection=False, show_selected_icon=False, expand=True,
            on_change=self._on_speed,
            style=ft.ButtonStyle(
                bgcolor={ft.ControlState.SELECTED: "#E0E7FF", ft.ControlState.DEFAULT: t.CARD},
                color={ft.ControlState.SELECTED: t.PRIMARY_DARK, ft.ControlState.DEFAULT: t.MUTED},
                side=ft.BorderSide(1, t.BORDER), shape=ft.RoundedRectangleBorder(radius=14),
            ),
        )
        self.items = w.reveal(
            [w.text("Pick what the virtual car should have. The simulation drives the same "
                    "5-minute route a real check uses.", 14, color=t.MUTED)]
            + rows
            + [w.section_title("Simulation speed"), ft.Row([speed]),
               w.primary_button("Start test drive", "PLAY_ARROW_ROUNDED", self.start),
               ft.Container(height=16)],
            dy=0.05,
        )
        return ft.Column([
            header("Test drive", self.back, "Simulated, no car needed"),
            ft.ListView(self.items, spacing=12, expand=True,
                        padding=ft.Padding.only(left=t.GUTTER, right=t.GUTTER, bottom=12)),
        ], spacing=0, expand=True)

    def _scenario_card(self, sid: str) -> ft.Control:
        s = SCENARIOS[sid]
        tile = ft.Container(
            ft.Column([
                w.icon_badge(s.icon, t.PRIMARY, "#EEF0FF", 40),
                w.text(s.name, 14, ft.FontWeight.W_700),
                w.text(s.description, 12, color=t.MUTED),
            ], spacing=8),
            padding=14, border_radius=20, expand=True, height=158, data=sid, on_click=self._pick,
            animate=ft.Animation(220, t.EASE), animate_scale=ft.Animation(220, t.EASE),
        )
        self.cards[sid] = tile
        self._style(tile, sid == self.selected)
        return tile

    def _style(self, tile: ft.Container, on: bool) -> None:
        tile.bgcolor = "#EEF0FF" if on else t.CARD
        tile.border = ft.Border.all(2, t.PRIMARY if on else t.CARD)
        tile.shadow = t.LIFT_SHADOW if on else t.SOFT_SHADOW
        tile.scale = 1.0 if on else 0.98

    def _pick(self, e):
        self.selected = e.control.data
        for sid, tile in self.cards.items():
            self._style(tile, sid == self.selected)
            tile.update()

    def _on_speed(self, e):
        self.speed = e.control.selected[0]

    def back(self, e=None):
        from .home import HomeScreen
        self.app.go(HomeScreen)

    def start(self, e):
        self.app.go(DriveScreen, scenario=self.selected, speedup=float(self.speed))

    async def did_show(self):
        await w.play_reveal(self.items, 0.035)


PHASES = [(30, "Cold start & idle"), (110, "City driving"), (125, "Accelerating"),
          (225, "Highway cruise"), (280, "City driving"), (300, "Idling")]

CHECKS = [
    ("start", "Engine start"),
    ("idle", "Idle recorded"),
    ("city", "City driving"),
    ("highway", "Highway speed (90+ km/h)"),
    ("warm", "Engine warm (80 °C)"),
    ("done", "Drive complete"),
]


def phase_for(sec: float) -> str:
    return next((name for end, name in PHASES if sec < end), "Finishing")


class Gauge:
    """Small tile with a value, unit and an animated bar."""

    def __init__(self, label: str, icon_name: str, lo: float, hi: float, fmt, good=None):
        self.lo, self.hi, self.fmt, self.good = lo, hi, fmt, good
        self.value = w.text("–", 20, ft.FontWeight.W_800)
        self.bar = ft.ProgressBar(value=0, bar_height=6, border_radius=3, color=t.GOOD, bgcolor=t.TRACK)
        self.control = w.card(ft.Column([
            ft.Row([ft.Icon(w.icon(icon_name), size=16, color=t.MUTED),
                    w.text(label, 12, ft.FontWeight.W_600, t.MUTED)], spacing=6),
            self.value, self.bar,
        ], spacing=8), padding=14, expand=True)

    def set(self, v: float) -> None:
        self.value.value = self.fmt(v)
        self.bar.value = max(0.02, min(1.0, (v - self.lo) / (self.hi - self.lo)))
        ok = self.good(v) if self.good else True
        self.bar.color = t.GOOD if ok else t.WATCH


class DriveScreen(Screen):
    def build(self) -> ft.Control:
        self.car = VirtualCar(self.kwargs["scenario"], speedup=self.kwargs["speedup"],
                              engine_l=self.app.profile.engine_l)
        self.samples: list[Sample] = []
        self.cancelled = False
        self.done_checks: set[str] = set()

        self.time_text = w.text(u.duration(DRIVE_SECONDS), 44, ft.FontWeight.W_800)
        self.phase_text = w.text("Connecting…", 13, ft.FontWeight.W_500, t.MUTED)
        self.ring = w.Ring(220, 16, 0, center=ft.Column(
            [self.time_text, self.phase_text], spacing=0, tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER))

        self.speed_text = w.text("0", 40, ft.FontWeight.W_800)
        self.rpm_text = w.text("0 rpm", 15, ft.FontWeight.W_600, t.MUTED)
        speed_card = w.card(ft.Row([
            ft.Row([self.speed_text, w.text("km/h", 15, ft.FontWeight.W_600, t.MUTED)],
                   vertical_alignment=ft.CrossAxisAlignment.END, spacing=6),
            ft.Column([w.text("Engine", 12, color=t.MUTED), self.rpm_text],
                      spacing=0, horizontal_alignment=ft.CrossAxisAlignment.END),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=ft.Padding.symmetric(horizontal=20, vertical=12))

        self.g_cool = Gauge("Coolant", "THERMOSTAT", 0, 115, u.celsius, lambda v: v <= 102)
        self.g_volt = Gauge("Battery", "BATTERY_CHARGING_FULL", 11, 15.5, u.volts, lambda v: 13.5 <= v <= 14.8)
        self.g_trim = Gauge("Fuel trim", "LOCAL_GAS_STATION", 0, 25, lambda v: f"{v:+.0f} %",
                            lambda v: abs(v) <= 9)
        self.g_air = Gauge("Air flow", "AIR", 0, 45, lambda v: f"{v:.1f} g/s")

        self.check_icons: dict[str, ft.AnimatedSwitcher] = {}
        check_rows = []
        for cid, label in CHECKS:
            sw = ft.AnimatedSwitcher(self._check_icon(False), transition=ft.AnimatedSwitcherTransition.SCALE,
                                     duration=350, switch_in_curve=ft.AnimationCurve.EASE_OUT_BACK)
            self.check_icons[cid] = sw
            check_rows.append(ft.Row([sw, w.text(label, 14)], spacing=10))

        self.dot = ft.Container(width=9, height=9, border_radius=5, bgcolor=t.DANGER,
                                animate_opacity=ft.Animation(500, ft.AnimationCurve.EASE_IN_OUT))
        scenario = SCENARIOS[self.kwargs["scenario"]]
        top = ft.Container(ft.Row([
            ft.Container(ft.Icon(ft.Icons.CLOSE_ROUNDED, color=t.TEXT), width=44, height=44,
                         border_radius=14, bgcolor=t.CARD, shadow=t.SOFT_SHADOW,
                         alignment=ft.Alignment.CENTER, on_click=self.confirm_cancel),
            ft.Column([w.text("Simulated drive", 20, ft.FontWeight.W_800),
                       ft.Row([self.dot, w.text(f"Recording · {scenario.name}", 13, color=t.MUTED)],
                              spacing=6)], spacing=0, expand=True),
        ], spacing=14), padding=ft.Padding.only(left=t.GUTTER, right=t.GUTTER, top=12, bottom=4))

        self.overlay = ft.Container(
            ft.Column([
                ft.ProgressRing(width=46, height=46, stroke_width=4, color=t.PRIMARY),
                w.text("Analysing your car…", 17, ft.FontWeight.W_700),
                w.text("Checking 13 components", 13, color=t.MUTED),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14, tight=True),
            bgcolor=ft.Colors.with_opacity(0.92, t.BG), alignment=ft.Alignment.CENTER,
            opacity=0, visible=False, animate_opacity=ft.Animation(300, t.EASE),
            left=0, right=0, top=0, bottom=0,
        )

        body = ft.ListView([
            ft.Container(self.ring, alignment=ft.Alignment.CENTER, padding=ft.Padding.only(top=8, bottom=4)),
            speed_card,
            ft.Row([self.g_cool.control, self.g_volt.control], spacing=12),
            ft.Row([self.g_trim.control, self.g_air.control], spacing=12),
            w.card(ft.Column([w.text("Drive checklist", 15, ft.FontWeight.W_700)] + check_rows, spacing=10)),
            ft.Container(height=12),
        ], spacing=12, padding=ft.Padding.symmetric(horizontal=t.GUTTER, vertical=8), expand=True)

        return ft.Stack([ft.Column([top, body], spacing=0, expand=True), self.overlay], expand=True)

    @staticmethod
    def _check_icon(done: bool) -> ft.Icon:
        if done:
            return ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color=t.GOOD,
                           size=22, key="on")
        return ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED_ROUNDED, color=t.SUBTLE, size=22, key="off")

    def _tick(self, cid: str) -> None:
        if cid not in self.done_checks:
            self.done_checks.add(cid)
            self.check_icons[cid].content = self._check_icon(True)

    async def did_show(self):
        await self.car.connect()
        self.page.run_task(self._blink)
        last_ui = 0.0
        async for s in self.car.stream():
            if self.cancelled:
                return
            self.samples.append(s)
            if s.t < 0:
                continue
            now = time.monotonic()
            if now - last_ui >= 1 / 20 or s.t >= DRIVE_SECONDS - 1:
                last_ui = now
                self._render(s)
        if self.cancelled:
            return
        self._tick("done")
        self.time_text.value = "0:00"
        self.phase_text.value = "Complete"
        self.ring.set_colors([t.GOOD] * 2)
        self.ring._set(1)
        self.page.update()
        await asyncio.sleep(0.5)
        await self._finish()

    def _render(self, s: Sample) -> None:
        elapsed = s.t + 1
        self.ring._set(elapsed / DRIVE_SECONDS)
        self.time_text.value = u.duration(DRIVE_SECONDS - elapsed)
        self.phase_text.value = phase_for(s.t)
        self.speed_text.value = str(round(s.speed_kmh))
        self.rpm_text.value = f"{u.num(s.rpm)} rpm"
        self.g_cool.set(s.coolant_c)
        self.g_volt.set(s.voltage)
        trim = s.stft + s.ltft
        self.g_trim.set(abs(trim))
        self.g_trim.value.value = f"{trim:+.0f} %"
        self.g_air.set(s.maf_gs)
        self._tick("start")
        if s.t >= 25:
            self._tick("idle")
        if s.t >= 100:
            self._tick("city")
        if s.speed_kmh >= 90:
            self._tick("highway")
        if s.coolant_c >= 80:
            self._tick("warm")
        self.page.update()

    async def _blink(self):
        while not self.cancelled and len(self.samples) < DRIVE_SECONDS + 3:
            self.dot.opacity = 0.25 if self.dot.opacity == 1 else 1
            try:
                self.dot.update()
            except Exception:
                return
            await asyncio.sleep(0.6)

    async def _finish(self):
        self.overlay.visible = True
        self.overlay.update()
        await asyncio.sleep(0.05)
        self.overlay.opacity = 1
        self.overlay.update()
        codes = await self.car.read_trouble_codes()
        report = analyze(self.samples, codes, self.app.profile, self.car.name)
        await asyncio.sleep(1.4)  # let the user see the analysis step
        self.app.store.add_report(report)
        self.app.current_report = report
        from .report import ReportScreen
        self.app.go(ReportScreen, fresh=True)

    def confirm_cancel(self, e):
        def stop(_):
            self.page.pop_dialog()
            self.cancelled = True
            from .home import HomeScreen
            self.app.go(HomeScreen)

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Stop the drive?"),
            content=ft.Text("The readings from this drive will be discarded."),
            actions=[ft.TextButton("Keep driving", on_click=lambda _: self.page.pop_dialog()),
                     ft.TextButton("Stop", on_click=stop, style=ft.ButtonStyle(color=t.DANGER))],
            shape=ft.RoundedRectangleBorder(radius=20), bgcolor=t.CARD,
        ))

    def dispose(self):
        self.cancelled = True
