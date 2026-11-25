"""Health report: overall score, drive stats, fault codes and every component."""

from __future__ import annotations

import flet as ft

from ... import units as u
from ...analysis.maintenance import UNMEASURED
from ...models import ComponentResult, Report, Status
from .. import theme as t
from .. import widgets as w
from ..app import Screen

SERIES_INFO = {
    "speed_kmh": ("Speed", "km/h", None),
    "rpm": ("Engine speed", "rpm", None),
    "coolant_c": ("Coolant temperature", "°C", (80, 100)),
    "voltage": ("Battery voltage", "V", (13.6, 14.7)),
    "trim": ("Total fuel trim", "%", (-8, 8)),
    "maf_gs": ("Air flow", "g/s", None),
    "o2_up_v": ("Front oxygen sensor", "V", None),
    "o2_down_v": ("Rear oxygen sensor", "V", None),
}

SCHEDULE_IDS = set(UNMEASURED)
ORDER = {Status.SERVICE: 0, Status.WATCH: 1, Status.GOOD: 2, Status.INFO: 3}


class ComponentTile:
    """Collapsed: icon, name, summary, status. Tap to expand details and a chart."""

    def __init__(self, c: ComponentResult, report: Report, chart_width: float):
        self.c, self.open = c, False
        color = t.STATUS_COLOR[c.status]
        self.arrow = ft.Icon(ft.Icons.EXPAND_MORE_ROUNDED, color=t.SUBTLE, rotate=0,
                             animate_rotation=ft.Animation(250, t.EASE))

        detail: list[ft.Control] = [ft.Divider(height=1, color=t.BORDER)]
        detail += [ft.Row([ft.Container(width=5, height=5, border_radius=3, bgcolor=t.SUBTLE,
                                        margin=ft.Margin.only(top=7)),
                           w.text(d, 13, color=t.MUTED, expand=True)],
                          spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)
                   for d in c.details]
        if c.action:
            detail.append(ft.Container(ft.Row([
                ft.Icon(ft.Icons.BUILD_ROUNDED, color=color, size=18),
                w.text(c.action, 13, ft.FontWeight.W_500, t.TEXT, expand=True),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START),
                bgcolor=t.STATUS_BG[c.status], border_radius=14, padding=12))
        if c.due_date:
            due = f"Next service: {u.dmy(c.due_date)}"
            if c.due_km:
                due += f" or at {u.km(c.due_km)}"
            detail.append(ft.Row([ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, size=16, color=t.PRIMARY),
                                  w.text(due, 13, ft.FontWeight.W_600, t.PRIMARY)], spacing=8))
        if c.series_key and report.series.get(c.series_key):
            name, unit, band = SERIES_INFO[c.series_key]
            values = report.series[c.series_key]
            detail.append(ft.Column([
                ft.Row([w.text(name, 12, ft.FontWeight.W_600, t.MUTED),
                        w.text(f"{min(values):g}–{max(values):g} {unit}", 12, color=t.SUBTLE)],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                w.sparkline(values, chart_width, 64, color=t.PRIMARY, band=band),
                ft.Row([w.text("start", 11, color=t.SUBTLE), w.text("5 min", 11, color=t.SUBTLE)],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=6))
        self.summary = w.text(c.summary, 13, color=t.MUTED, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
        self.details = ft.Container(ft.Column(detail, spacing=10), visible=False,
                                    padding=ft.Padding.only(top=12))

        score_bar = ft.Container()
        if c.status != Status.INFO and c.measured:
            score_bar = ft.Container(ft.Row([
                ft.Container(bgcolor=color, border_radius=2, height=4, expand=max(c.score, 1)),
                ft.Container(height=4, expand=max(100 - c.score, 1)),
            ], spacing=0), height=4, border_radius=2, bgcolor=t.TRACK, margin=ft.Margin.only(top=10))

        self.control = w.card(ft.Column([
            ft.Row([
                w.icon_badge(c.icon, color, t.STATUS_BG[c.status], 42),
                ft.Column([
                    w.text(c.name, 15, ft.FontWeight.W_700),
                    self.summary,
                ], spacing=2, expand=True),
                ft.Column([w.status_chip(c.status), self.arrow], spacing=4,
                          horizontal_alignment=ft.CrossAxisAlignment.END),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
            score_bar,
            self.details,
        ], spacing=0), padding=16, on_click=self.toggle,
            animate_size=ft.Animation(260, t.EASE))

    def toggle(self, e):
        self.open = not self.open
        self.details.visible = self.open
        self.summary.max_lines = None if self.open else 2
        self.arrow.rotate = 3.14159 if self.open else 0
        self.control.update()


class ReportScreen(Screen):
    tab = 1

    def build(self) -> ft.Control:
        r = self.app.current_report or self.app.store.latest
        self.report = r
        self.ring = None
        if not r:
            return ft.Container(ft.Column([
                w.icon_badge("ASSESSMENT_ROUNDED", t.PRIMARY, "#EEF0FF", 72),
                w.text("No report yet", 20, ft.FontWeight.W_800),
                w.text("Run a test drive to get your first health report.", 14, color=t.MUTED,
                       text_align=ft.TextAlign.CENTER),
                ft.Container(w.primary_button("Start a test drive", "SCIENCE_ROUNDED",
                                              lambda e: self._go_test(), expand=False), width=260),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14, tight=True),
                alignment=ft.Alignment.CENTER, expand=True, padding=30)

        self.ring, self.number = w.score_ring(r.overall, size=132, stroke=12, light=True)
        counts = {s: sum(c.status == s for c in r.components) for s in (Status.GOOD, Status.WATCH, Status.SERVICE)}
        chips = ft.Row([w.status_chip(s, f"{n} {s.label.lower()}") for s, n in counts.items() if n],
                       spacing=6, wrap=True, run_spacing=6)
        hero = ft.Container(ft.Column([
            ft.Row([
                self.ring,
                ft.Column([
                    w.text("Health report", 20, ft.FontWeight.W_800, "white"),
                    w.text(f"{u.dmy(r.created_at)} · {r.created.strftime('%H:%M')}", 14, color="#E0E7FF"),
                    w.text(f"At {u.km(r.odometer_km)}", 13, color="#C7D2FE"),
                ], spacing=3, expand=True),
            ], spacing=18),
            ft.Container(ft.Row([ft.Icon(ft.Icons.SCIENCE_ROUNDED if "Simulation" in r.source
                                         else ft.Icons.BLUETOOTH_ROUNDED, color="white", size=16),
                                 w.text(r.source, 12, ft.FontWeight.W_500, "white", expand=True)],
                                spacing=8),
                         bgcolor=ft.Colors.with_opacity(0.15, "white"), border_radius=12,
                         padding=ft.Padding.symmetric(horizontal=12, vertical=8)),
        ], spacing=14), gradient=t.HERO_GRADIENT, border_radius=28, padding=20, shadow=t.LIFT_SHADOW)

        stats = ft.Column([
            ft.Row([self._stat("ROUTE_ROUNDED", f"{r.distance_km:.1f} km", "Distance"),
                    self._stat("SPEED_ROUNDED", u.kmh(r.avg_speed_kmh), "Avg. speed")], spacing=10),
            ft.Row([self._stat("LOCAL_GAS_STATION_ROUNDED", f"{r.fuel_l_per_100km:.1f}", "L/100 km"),
                    self._stat("TIMER_ROUNDED", u.duration(r.duration_s), "Duration")], spacing=10),
        ], spacing=10)

        items: list[ft.Control] = [hero, chips, stats]
        if r.trouble_codes:
            items.append(w.card(ft.Column(
                [ft.Row([ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, color=t.DANGER),
                         w.text("Fault codes", 16, ft.FontWeight.W_700)], spacing=8)]
                + [ft.Row([ft.Container(w.text(code.code, 12, ft.FontWeight.W_700, t.DANGER),
                                        bgcolor=t.STATUS_BG[Status.SERVICE], border_radius=8,
                                        padding=ft.Padding.symmetric(horizontal=8, vertical=3)),
                           w.text(code.description, 13, color=t.MUTED, expand=True)], spacing=10)
                   for code in r.trouble_codes], spacing=10)))

        chart_w = self.app.content_width - 32
        schedule = [c for c in r.components if c.id in SCHEDULE_IDS]
        measured = sorted([c for c in r.components if c.id not in SCHEDULE_IDS],
                          key=lambda c: ORDER[c.status])
        items.append(w.section_title(f"Measured by OBD · {len(measured)}"))
        items += [ComponentTile(c, r, chart_w).control for c in measured]
        items.append(w.section_title("Based on mileage"))
        items += [ComponentTile(c, r, chart_w).control for c in schedule]
        items += [w.primary_button("Open maintenance plan", "BUILD_CIRCLE_ROUNDED", self._go_plan),
                  ft.Container(height=12)]

        self.items = w.reveal(items, dy=0.06)
        return ft.ListView(self.items, spacing=12, expand=True,
                           padding=ft.Padding.symmetric(horizontal=t.GUTTER, vertical=14))

    def _stat(self, icon_name: str, value: str, label: str) -> ft.Control:
        return w.card(ft.Row([
            w.icon_badge(icon_name, t.PRIMARY, "#EEF0FF", 38),
            ft.Column([w.text(value, 16, ft.FontWeight.W_700), w.text(label, 12, color=t.MUTED)], spacing=0),
        ], spacing=12), padding=12, expand=True)

    async def did_show(self):
        if self.ring:
            self.page.run_task(w.animate_score, self.ring, self.number, self.report.overall, 1.3)
        await w.play_reveal(getattr(self, "items", []), 0.045)
        if self.kwargs.get("fresh"):
            self.app.toast("Report saved. Tap any component for details.", "TASK_ALT_ROUNDED")

    def _go_plan(self, e):
        from .plan import PlanScreen
        self.app.go(PlanScreen)

    def _go_test(self):
        from .drive import TestSetupScreen
        self.app.go(TestSetupScreen)
