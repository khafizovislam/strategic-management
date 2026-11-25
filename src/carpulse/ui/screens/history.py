"""Past checks and the health-score trend."""

from __future__ import annotations

import flet as ft

from ... import units as u
from ...models import Report
from .. import theme as t
from .. import widgets as w
from ..app import Screen
from .home import counts_line


class HistoryScreen(Screen):
    tab = 3

    def build(self) -> ft.Control:
        reports = self.app.store.reports
        items: list[ft.Control] = [ft.Column([
            w.text("History", 26, ft.FontWeight.W_800),
            w.text(f"{len(reports)} check{'s' if len(reports) != 1 else ''} saved on this device",
                   14, color=t.MUTED),
        ], spacing=2)]

        if len(reports) >= 2:
            scores = [r.overall for r in reversed(reports)]
            items.append(w.card(ft.Column([
                ft.Row([w.text("Health trend", 15, ft.FontWeight.W_700),
                        w.text(f"{scores[0]} → {scores[-1]}", 14, ft.FontWeight.W_700,
                               t.score_color(scores[-1]))],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                w.sparkline([float(s) for s in scores], self.app.content_width - 36, 80,
                            color=t.PRIMARY, band=(80, 100)),
            ], spacing=10)))

        if not reports:
            items.append(w.card(ft.Column([
                w.icon_badge("HISTORY_ROUNDED", t.PRIMARY, "#EEF0FF", 56),
                w.text("No checks yet", 17, ft.FontWeight.W_700),
                w.text("Each check you run is saved here so you can see how your car changes.",
                       14, color=t.MUTED, text_align=ft.TextAlign.CENTER),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10), padding=28))

        items += [self._row(r) for r in reports]
        items.append(ft.Container(height=12))
        self.items = w.reveal(items, dy=0.06)
        return ft.ListView(self.items, spacing=12, expand=True,
                           padding=ft.Padding.symmetric(horizontal=t.GUTTER, vertical=14))

    def _row(self, r: Report) -> ft.Control:
        color = t.score_color(r.overall)
        return w.card(ft.Row([
            ft.Container(w.text(str(r.overall), 18, ft.FontWeight.W_800, color), width=52, height=52,
                         border_radius=26, alignment=ft.Alignment.CENTER,
                         border=ft.Border.all(3, color), bgcolor=t.CARD),
            ft.Column([
                w.text(f"{u.dmy(r.created_at)} · {r.created.strftime('%H:%M')}", 15, ft.FontWeight.W_700),
                w.text(counts_line(r.components), 13, color=t.MUTED),
                w.text(r.source, 12, color=t.SUBTLE, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ], spacing=1, expand=True),
            ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=t.SUBTLE),
        ], spacing=14), padding=14, on_click=lambda e, rep=r: self.open(rep))

    def open(self, r: Report):
        from .report import ReportScreen
        self.app.current_report = r
        self.app.go(ReportScreen)

    async def did_show(self):
        await w.play_reveal(self.items, 0.04)
