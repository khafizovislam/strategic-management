"""Reusable, animated building blocks for the CarPulse screens."""

from __future__ import annotations

import asyncio
import math
from typing import Callable

import flet as ft
import flet.canvas as cv

from ..models import Status
from . import theme as t


def icon(name: str) -> ft.IconData:
    return getattr(ft.Icons, name, ft.Icons.CIRCLE)


def text(value: str, size: float = 14, weight: ft.FontWeight | None = None,
         color: str = t.TEXT, **kw) -> ft.Text:
    return ft.Text(value, size=size, weight=weight, color=color, **kw)


def card(content: ft.Control, padding: float = 18, on_click=None, bgcolor: str = t.CARD,
         **kw) -> ft.Container:
    return ft.Container(
        content=content, padding=padding, bgcolor=bgcolor, border_radius=t.RADIUS,
        shadow=t.SOFT_SHADOW, on_click=on_click, ink=False, **kw,
    )


def section_title(title: str, trailing: ft.Control | None = None) -> ft.Control:
    row = [text(title, 17, ft.FontWeight.W_700)]
    if trailing:
        row.append(trailing)
    return ft.Container(
        ft.Row(row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=ft.Padding.only(left=4, top=10, bottom=2),
    )


def status_chip(status: Status, label: str | None = None) -> ft.Container:
    return ft.Container(
        ft.Row([
            ft.Container(width=7, height=7, border_radius=4, bgcolor=t.STATUS_COLOR[status]),
            text(label or status.label, 12, ft.FontWeight.W_600, t.STATUS_COLOR[status]),
        ], spacing=6, tight=True),
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        border_radius=20, bgcolor=t.STATUS_BG[status],
    )


def icon_badge(name: str, color: str, bg: str, size: float = 44) -> ft.Container:
    return ft.Container(
        ft.Icon(icon(name), color=color, size=size * 0.5),
        width=size, height=size, border_radius=size * 0.32, bgcolor=bg,
        alignment=ft.Alignment.CENTER,
    )


def primary_button(label: str, icon_name: str | None, on_click, expand: bool = True,
                   disabled: bool = False) -> ft.Container:
    """Gradient pill button that springs slightly when pressed."""
    btn = ft.Container(
        ft.Row(
            ([ft.Icon(icon(icon_name), color="white", size=20)] if icon_name else [])
            + [text(label, 16, ft.FontWeight.W_600, "white")],
            alignment=ft.MainAxisAlignment.CENTER, spacing=8,
        ),
        height=56, border_radius=18, gradient=t.HERO_GRADIENT, shadow=t.LIFT_SHADOW,
        expand=expand, scale=1, animate_scale=ft.Animation(160, t.EASE),
        opacity=0.45 if disabled else 1, disabled=disabled,
    )

    async def press(e):
        btn.scale = 0.96
        btn.update()
        await asyncio.sleep(0.12)
        btn.scale = 1
        btn.update()
        result = on_click(e)
        if asyncio.iscoroutine(result):
            await result

    btn.on_click = press
    return btn


def secondary_button(label: str, icon_name: str | None, on_click, expand: bool = True) -> ft.Container:
    return ft.Container(
        ft.Row(
            ([ft.Icon(icon(icon_name), color=t.PRIMARY, size=20)] if icon_name else [])
            + [text(label, 15, ft.FontWeight.W_600, t.PRIMARY)],
            alignment=ft.MainAxisAlignment.CENTER, spacing=8,
        ),
        height=52, border_radius=16, bgcolor="#EEF0FF", expand=expand, on_click=on_click,
    )


# ------------------------------------------------------------------ rings
class Ring(ft.Stack):
    """Circular progress ring drawn on a canvas, with an animated fill."""

    def __init__(self, size: float = 180, stroke: float = 16, value: float = 0,
                 colors: list[str] | None = None, track: str = t.TRACK,
                 center: ft.Control | None = None):
        self.size, self.stroke, self.value = size, stroke, value
        self.colors = colors or [t.ACCENT, t.PRIMARY, t.VIOLET]
        r = size / 2
        self._arc = cv.Arc(stroke / 2, stroke / 2, size - stroke, size - stroke,
                           start_angle=-math.pi / 2, sweep_angle=0, paint=self._paint())
        self._track = cv.Circle(r, r, r - stroke / 2, paint=ft.Paint(
            color=track, stroke_width=stroke, style=ft.PaintingStyle.STROKE))
        self.canvas = cv.Canvas([self._track, self._arc], width=size, height=size)
        super().__init__(
            [self.canvas, ft.Container(center, width=size, height=size, alignment=ft.Alignment.CENTER)],
            width=size, height=size,
        )
        self._set(value)

    def _paint(self) -> ft.Paint:
        r = self.size / 2
        return ft.Paint(
            stroke_width=self.stroke, style=ft.PaintingStyle.STROKE, stroke_cap=ft.StrokeCap.ROUND,
            gradient=ft.PaintSweepGradient(
                center=(r, r), colors=self.colors, start_angle=0, end_angle=math.pi * 2,
                rotation=-math.pi / 2 - 0.14,  # keep the colour seam away from the round start cap
            ),
        )

    def _set(self, value: float) -> None:
        self.value = max(0.0, min(1.0, value))
        self._arc.sweep_angle = math.pi * 2 * max(self.value, 0.001)

    def set_colors(self, colors: list[str]) -> None:
        self.colors = colors
        self._arc.paint = self._paint()

    def set_value(self, value: float) -> None:
        self._set(value)
        self.canvas.update()

    async def animate_to(self, value: float, duration: float = 0.9,
                         on_step: Callable[[float], None] | None = None) -> None:
        start = self.value
        frames = max(1, int(duration * 50))
        for i in range(1, frames + 1):
            k = 1 - (1 - i / frames) ** 3  # ease-out cubic
            self._set(start + (value - start) * k)
            if on_step:
                on_step(k)
            self.update()
            await asyncio.sleep(duration / frames)


def score_ring(score: int, size: float = 170, stroke: float = 15, light: bool = False) -> tuple[Ring, ft.Text]:
    """Overall health ring with a big number in the middle. Animate with ring.animate_to()."""
    number = ft.Text("0", size=size * 0.27, weight=ft.FontWeight.W_800,
                     color="white" if light else t.TEXT)
    caption = text("health", size * 0.075, ft.FontWeight.W_500, "#E0E7FF" if light else t.MUTED)
    color = t.score_color(score)
    colors = [color, color] if not light else ["#FFFFFF", "#C7D2FE"]
    ring = Ring(size, stroke, 0, colors=colors, track=ft.Colors.with_opacity(0.2, "#FFFFFF") if light else t.TRACK,
                center=ft.Column([number, caption], spacing=0, tight=True,
                                 horizontal_alignment=ft.CrossAxisAlignment.CENTER))
    return ring, number


async def animate_score(ring: Ring, number: ft.Text, score: int, duration: float = 1.1) -> None:
    def step(k: float) -> None:
        number.value = str(round(score * k))
    await ring.animate_to(score / 100, duration, step)


# ------------------------------------------------------------------ charts
def sparkline(values: list[float], width: float, height: float = 70, color: str = t.PRIMARY,
              band: tuple[float, float] | None = None) -> cv.Canvas:
    """Smooth-looking line chart with a soft gradient fill and an optional 'healthy' band."""
    if not values:
        return cv.Canvas(width=width, height=height)
    lo, hi = min(values), max(values)
    if band:
        lo, hi = min(lo, band[0]), max(hi, band[1])
    pad = (hi - lo) * 0.12 or 1
    lo, hi = lo - pad, hi + pad

    def y(v: float) -> float:
        return height - (v - lo) / (hi - lo) * height

    n = len(values)
    xs = [i * width / max(n - 1, 1) for i in range(n)]
    line = [cv.Path.MoveTo(xs[0], y(values[0]))] + [cv.Path.LineTo(x, y(v)) for x, v in zip(xs[1:], values[1:])]
    area = line + [cv.Path.LineTo(xs[-1], height), cv.Path.LineTo(0, height), cv.Path.Close()]
    shapes: list = []
    if band:
        shapes.append(cv.Rect(0, y(band[1]), width, y(band[0]) - y(band[1]),
                              paint=ft.Paint(color=ft.Colors.with_opacity(0.08, "#10B981"))))
    shapes += [
        cv.Path(area, paint=ft.Paint(gradient=ft.PaintLinearGradient(
            begin=(0, 0), end=(0, height), colors=[ft.Colors.with_opacity(0.25, color), ft.Colors.with_opacity(0.0, color)]))),
        cv.Path(line, paint=ft.Paint(color=color, stroke_width=2.4, style=ft.PaintingStyle.STROKE,
                                     stroke_join=ft.StrokeJoin.ROUND, stroke_cap=ft.StrokeCap.ROUND)),
        cv.Circle(xs[-1], y(values[-1]), 3.5, paint=ft.Paint(color=color)),
    ]
    return cv.Canvas(shapes, width=width, height=height)


# --------------------------------------------------------------- entrance
def reveal(controls: list[ft.Control], dy: float = 0.08) -> list[ft.Control]:
    """Wrap controls so they can fade and slide in; call `play_reveal` after showing them."""
    out = []
    for c in controls:
        out.append(ft.Container(
            c, opacity=0, offset=ft.Offset(0, dy),
            animate_opacity=ft.Animation(420, t.EASE), animate_offset=ft.Animation(520, t.EASE),
        ))
    return out


async def play_reveal(wrapped: list[ft.Control], stagger: float = 0.06) -> None:
    for w in wrapped:
        w.opacity = 1
        w.offset = ft.Offset(0, 0)
        try:
            w.update()
        except Exception:  # control was removed (user navigated away)
            return
        await asyncio.sleep(stagger)
