"""Home: overall health, the two ways to run a check, and what's due next."""

from __future__ import annotations

from datetime import datetime

import flet as ft

from ... import units as u
from ...models import Status
from .. import theme as t
from .. import widgets as w
from ..app import Screen


def greeting() -> str:
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"


def counts_line(components) -> str:
    service = sum(c.status == Status.SERVICE for c in components)
    watch = sum(c.status == Status.WATCH for c in components)
    if not service and not watch:
        return "All systems look healthy"
    parts = []
    if service:
        parts.append(f"{service} need{'s' if service == 1 else ''} service")
    if watch:
        parts.append(f"{watch} to watch")
    return ", ".join(parts).capitalize()


class HomeScreen(Screen):
    tab = 0

    def build(self) -> ft.Control:
        p = self.app.profile
        report = self.app.store.latest
        self.ring = None

        top = ft.Row([
            ft.Column([w.text(greeting(), 14, color=t.MUTED),
                       w.text(p.title or "My car", 26, ft.FontWeight.W_800)], spacing=0, expand=True),
            ft.Container(ft.Icon(ft.Icons.DIRECTIONS_CAR_ROUNDED, color=t.PRIMARY), width=48, height=48,
                         border_radius=16, bgcolor=t.CARD, shadow=t.SOFT_SHADOW,
                         alignment=ft.Alignment.CENTER, on_click=self.open_vehicle,
                         tooltip="Your vehicle"),
        ])

        if report:
            self.ring, self.number = w.score_ring(report.overall, size=128, stroke=12, light=True)
            hero_body = ft.Row([
                self.ring,
                ft.Column([
                    w.text("Last check", 13, color="#C7D2FE"),
                    w.text(f"{u.dmy(report.created_at)} · {report.created.strftime('%H:%M')}", 15,
                           ft.FontWeight.W_600, "white"),
                    w.text(counts_line(report.components), 14, ft.FontWeight.W_500, "white"),
                    ft.Container(
                        ft.Row([w.text("View report", 13, ft.FontWeight.W_600, t.PRIMARY),
                                ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=t.PRIMARY, size=18)],
                               spacing=2, tight=True),
                        bgcolor="white", border_radius=20, on_click=self.open_report,
                        padding=ft.Padding.only(left=12, right=6, top=6, bottom=6), margin=ft.Margin.only(top=4),
                    ),
                ], spacing=4, expand=True),
            ], spacing=18)
        else:
            hero_body = ft.Row([
                ft.Container(ft.Icon(ft.Icons.MONITOR_HEART_ROUNDED, color="white", size=44),
                             width=96, height=96, border_radius=48, alignment=ft.Alignment.CENTER,
                             bgcolor=ft.Colors.with_opacity(0.16, "white")),
                ft.Column([
                    w.text("No checks yet", 19, ft.FontWeight.W_700, "white"),
                    w.text("Run a 5-minute drive, or tap Test to simulate one and see "
                           "a full health report.", 14, color="#E0E7FF"),
                ], spacing=6, expand=True),
            ], spacing=18)
        hero = ft.Container(hero_body, gradient=t.HERO_GRADIENT, border_radius=28, padding=20,
                            shadow=t.LIFT_SHADOW)

        drive_card = w.card(ft.Row([
            w.icon_badge("BLUETOOTH_ROUNDED", t.SUBTLE, "#F1F5F9"),
            ft.Column([
                w.text("5-minute drive", 16, ft.FontWeight.W_700),
                w.text("Connect an OBD adapter, then drive normally.", 13, color=t.MUTED),
            ], spacing=2, expand=True),
            ft.Container(w.text("Adapter needed", 11, ft.FontWeight.W_600, t.MUTED),
                         bgcolor="#F1F5F9", border_radius=12,
                         padding=ft.Padding.symmetric(horizontal=8, vertical=4)),
        ], spacing=14), on_click=self.real_drive)

        test_btn = w.primary_button("Test: simulate a 5-min drive", "SCIENCE_ROUNDED", self.open_test)

        plan = self.app.plan()[:3]
        upcoming = [self._task_row(task) for task in plan]

        stats = ft.Row([
            self._stat("ROUTE_ROUNDED", u.km(p.odometer_km), "Odometer"),
            self._stat("SPEED_ROUNDED", f"{u.num(p.km_per_week)} km", "Per week"),
            self._stat("ASSESSMENT_ROUNDED", str(len(self.app.store.reports)), "Checks"),
        ], spacing=10)

        self.items = w.reveal([
            top, hero,
            w.section_title("Run a check"), test_btn, drive_card,
            w.section_title("Coming up", ft.TextButton("See plan", on_click=self.open_plan)),
            w.card(ft.Column(upcoming, spacing=4), padding=8),
            stats,
            ft.Container(height=12),
        ])
        return ft.ListView(self.items, spacing=14,
                           padding=ft.Padding.symmetric(horizontal=t.GUTTER, vertical=12), expand=True)

    def _task_row(self, task) -> ft.Control:
        color = t.STATUS_COLOR[task.urgency]
        return ft.Container(ft.Row([
            w.icon_badge(task.icon, color, t.STATUS_BG[task.urgency], 40),
            ft.Column([
                w.text(task.name, 15, ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                w.text(f"{u.when(task.days_left).capitalize()} · {u.dmy(task.due_date)}", 12, color=t.MUTED),
            ], spacing=1, expand=True),
            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=t.SUBTLE),
        ], spacing=12), padding=10, border_radius=16, on_click=self.open_plan)

    def _stat(self, icon_name: str, value: str, label: str) -> ft.Control:
        return w.card(ft.Column([
            ft.Icon(w.icon(icon_name), color=t.PRIMARY, size=20),
            w.text(value, 15, ft.FontWeight.W_700, max_lines=1),
            w.text(label, 12, color=t.MUTED),
        ], spacing=4), padding=14, expand=True)

    async def did_show(self):
        if self.ring:
            self.page.run_task(w.animate_score, self.ring, self.number, self.app.store.latest.overall)
        await w.play_reveal(self.items)

    # --------------------------------------------------------------- actions
    def open_vehicle(self, e):
        from .vehicle import VehicleScreen
        self.app.go(VehicleScreen)

    def open_report(self, e):
        from .report import ReportScreen
        self.app.current_report = self.app.store.latest
        self.app.go(ReportScreen)

    def open_plan(self, e):
        from .plan import PlanScreen
        self.app.go(PlanScreen)

    def open_test(self, e):
        from .drive import TestSetupScreen
        self.app.go(TestSetupScreen)

    def real_drive(self, e):
        self.app.toast("OBD adapter support is coming in a later version. Use Test for now.",
                       "INFO_OUTLINE_ROUNDED")
