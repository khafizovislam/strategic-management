"""Maintenance plan grouped by urgency, with 'mark as done'."""

from __future__ import annotations

from datetime import date

import flet as ft

from ... import units as u
from ...models import MaintenanceTask, Status
from .. import theme as t
from .. import widgets as w
from ..app import Screen

GROUPS = [(Status.SERVICE, "Due now"), (Status.WATCH, "Coming soon"), (Status.GOOD, "Later")]


class PlanScreen(Screen):
    tab = 2

    def build(self) -> ft.Control:
        p = self.app.profile
        plan = self.app.plan()
        items: list[ft.Control] = [ft.Column([
            w.text("Maintenance plan", 26, ft.FontWeight.W_800),
            w.text(f"Based on {u.km(p.odometer_km)} and about {u.num(p.km_per_week)} km per week"
                   + (" plus your latest check." if self.app.store.latest else "."), 14, color=t.MUTED),
        ], spacing=2)]

        summary = ft.Row([self._count(s, label, sum(x.urgency == s for x in plan)) for s, label in GROUPS],
                         spacing=10)
        items.append(summary)
        for status, label in GROUPS:
            tasks = [x for x in plan if x.urgency == status]
            if tasks:
                items.append(w.section_title(label))
                items += [self._task(x) for x in tasks]
        items.append(ft.Container(height=12))
        self.items = w.reveal(items, dy=0.06)
        return ft.ListView(self.items, spacing=12, expand=True,
                           padding=ft.Padding.symmetric(horizontal=t.GUTTER, vertical=14))

    def _count(self, status: Status, label: str, n: int) -> ft.Control:
        return ft.Container(ft.Column([
            w.text(str(n), 24, ft.FontWeight.W_800, t.STATUS_COLOR[status]),
            w.text(label, 12, ft.FontWeight.W_600, t.MUTED),
        ], spacing=0), bgcolor=t.STATUS_BG[status], border_radius=18, padding=14, expand=True)

    def _task(self, task: MaintenanceTask) -> ft.Control:
        color = t.STATUS_COLOR[task.urgency]
        overdue = task.days_left < 0
        when = "Overdue" if overdue else u.when(task.days_left).capitalize()
        meta = ft.Row([
            ft.Icon(ft.Icons.CALENDAR_MONTH_ROUNDED, size=15, color=t.SUBTLE),
            w.text(u.dmy(task.due_date), 12, color=t.MUTED),
            ft.Icon(ft.Icons.ROUTE_ROUNDED, size=15, color=t.SUBTLE),
            w.text(f"at {u.km(task.due_km)}", 12, color=t.MUTED),
        ], spacing=4, wrap=True)
        badges = [w.status_chip(task.urgency, when)]
        if task.from_fault:
            badges.append(ft.Container(w.text("From last check", 11, ft.FontWeight.W_600, t.PRIMARY),
                                       bgcolor="#EEF0FF", border_radius=20,
                                       padding=ft.Padding.symmetric(horizontal=9, vertical=5)))
        done_btn = ft.Container(
            ft.Row([ft.Icon(ft.Icons.CHECK_ROUNDED, size=16, color=t.PRIMARY),
                    w.text("Done", 13, ft.FontWeight.W_600, t.PRIMARY)], spacing=4, tight=True),
            bgcolor="#EEF0FF", border_radius=12, padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            on_click=lambda e, x=task: self.confirm_done(x),
        )
        return w.card(ft.Column([
            ft.Row([
                w.icon_badge(task.icon, color, t.STATUS_BG[task.urgency], 42),
                ft.Column([w.text(task.name, 15, ft.FontWeight.W_700),
                           w.text(task.reason, 12, color=t.MUTED, max_lines=3,
                                  overflow=ft.TextOverflow.ELLIPSIS)], spacing=2, expand=True),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
            meta,
            ft.Row([ft.Row(badges, spacing=6, wrap=True, expand=True), done_btn],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=10), padding=16)

    def confirm_done(self, task: MaintenanceTask):
        p = self.app.profile

        def done(_):
            self.page.pop_dialog()
            self.app.store.mark_service_done(task.id, p.odometer_km, date.today().isoformat())
            self.app.toast(f"{task.name}: marked as done")
            self.app.go(PlanScreen)

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Mark as done?"),
            content=ft.Text(f"“{task.name}” done today ({u.dmy(date.today())}) at {u.km(p.odometer_km)}. "
                            + ("It will be removed from the plan until the next check finds it again."
                               if task.from_fault and task.id.startswith("fix_")
                               else "The next due date will be recalculated.")),
            actions=[ft.TextButton("Cancel", on_click=lambda _: self.page.pop_dialog()),
                     ft.TextButton("Mark done", on_click=done)],
            shape=ft.RoundedRectangleBorder(radius=20), bgcolor=t.CARD,
        ))

    async def did_show(self):
        await w.play_reveal(self.items, 0.04)
