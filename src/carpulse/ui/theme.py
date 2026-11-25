"""Colours, spacing and the app-wide light theme."""

from __future__ import annotations

import flet as ft

from ..models import Status

PRIMARY = "#4F46E5"  # indigo
PRIMARY_DARK = "#3730A3"
VIOLET = "#7C3AED"
ACCENT = "#06B6D4"  # cyan
BG = "#F4F6FB"
CARD = "#FFFFFF"
TEXT = "#0F172A"
MUTED = "#64748B"
SUBTLE = "#94A3B8"
BORDER = "#E2E8F0"
TRACK = "#E9ECF5"
DANGER = "#EF4444"
GOOD = "#10B981"
WATCH = "#F59E0B"

STATUS_COLOR = {
    Status.GOOD: "#10B981",
    Status.WATCH: "#F59E0B",
    Status.SERVICE: "#EF4444",
    Status.INFO: "#94A3B8",
}
STATUS_BG = {
    Status.GOOD: "#ECFDF5",
    Status.WATCH: "#FFFBEB",
    Status.SERVICE: "#FEF2F2",
    Status.INFO: "#F1F5F9",
}

RADIUS = 22
GUTTER = 18
MAX_WIDTH = 480  # content never gets wider than a large phone

HERO_GRADIENT = ft.LinearGradient(
    begin=ft.Alignment(-1, -1), end=ft.Alignment(1, 1), colors=[PRIMARY, VIOLET]
)

SOFT_SHADOW = [ft.BoxShadow(blur_radius=24, spread_radius=-6, color=ft.Colors.with_opacity(0.10, "#1E3A5F"), offset=ft.Offset(0, 8))]
LIFT_SHADOW = [ft.BoxShadow(blur_radius=30, spread_radius=-4, color=ft.Colors.with_opacity(0.30, PRIMARY), offset=ft.Offset(0, 12))]

EASE = ft.AnimationCurve.EASE_OUT_CUBIC


def score_color(score: int) -> str:
    if score >= 80:
        return STATUS_COLOR[Status.GOOD]
    if score >= 55:
        return STATUS_COLOR[Status.WATCH]
    return STATUS_COLOR[Status.SERVICE]


def apply(page: ft.Page) -> None:
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = BG
    page.theme = ft.Theme(
        color_scheme_seed=PRIMARY,
        color_scheme=ft.ColorScheme(primary=PRIMARY, surface=CARD, on_surface=TEXT),
        scaffold_bgcolor=BG,
        page_transitions=ft.PageTransitionsTheme(
            android=ft.PageTransitionTheme.CUPERTINO,
            ios=ft.PageTransitionTheme.CUPERTINO,
            windows=ft.PageTransitionTheme.CUPERTINO,
            macos=ft.PageTransitionTheme.CUPERTINO,
            linux=ft.PageTransitionTheme.CUPERTINO,
        ),
    )
