"""App shell: holds state, switches screens with an animation, shows the tab bar."""

from __future__ import annotations

import flet as ft

from ..analysis import build_plan
from ..models import MaintenanceTask, Report
from ..storage import Store
from . import theme as t

TABS = [
    ("Home", "HOME_OUTLINED", "HOME_ROUNDED"),
    ("Report", "ASSESSMENT_OUTLINED", "ASSESSMENT_ROUNDED"),
    ("Plan", "BUILD_CIRCLE_OUTLINED", "BUILD_CIRCLE_ROUNDED"),
    ("History", "HISTORY_OUTLINED", "HISTORY_ROUNDED"),
]


class Screen:
    """Base class. `tab` is the highlighted tab index, or None to hide the tab bar."""

    tab: int | None = None

    def __init__(self, app: "CarPulseApp", **kwargs):
        self.app = app
        self.page = app.page
        self.kwargs = kwargs

    def build(self) -> ft.Control:
        raise NotImplementedError

    async def did_show(self) -> None:
        """Runs after the screen is on screen; used for entrance animations."""

    def dispose(self) -> None:
        """Runs when the user leaves the screen."""


class CarPulseApp:
    def __init__(self, page: ft.Page, store: Store | None = None):
        self.page = page
        self.store = store or Store()
        self.current_report: Report | None = self.store.latest
        self.screen: Screen | None = None

        page.title = "CarPulse"
        page.padding = 0
        page.spacing = 0
        t.apply(page)
        if not page.web and page.platform in (ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS,
                                               ft.PagePlatform.LINUX):
            page.window.width = 410
            page.window.height = 860
            page.window.min_width = 340

        self.switcher = ft.AnimatedSwitcher(
            content=ft.Container(),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=320, reverse_duration=180,
            switch_in_curve=t.EASE, switch_out_curve=ft.AnimationCurve.EASE_IN,
            expand=True,
        )
        self.nav = ft.NavigationBar(
            destinations=[
                ft.NavigationBarDestination(label=label, icon=getattr(ft.Icons, i),
                                            selected_icon=getattr(ft.Icons, si))
                for label, i, si in TABS
            ],
            bgcolor=t.CARD, indicator_color="#E0E7FF", elevation=0,
            shadow_color=t.BORDER, on_change=self._on_tab,
            animation_duration=400,
        )
        page.add(ft.SafeArea(
            ft.Container(self.switcher, alignment=ft.Alignment.TOP_CENTER, expand=True),
            expand=True,
        ))

        page.on_disconnect = lambda e: self.screen and self.screen.dispose()
        from .screens import HomeScreen, OnboardingScreen
        self.go(HomeScreen if self.store.profile else OnboardingScreen)

    # --------------------------------------------------------------- state
    @property
    def profile(self):
        return self.store.profile

    def plan(self) -> list[MaintenanceTask]:
        report = self.store.latest
        return build_plan(self.profile, report.components if report else [],
                          report_date=report.created_at[:10] if report else None)

    @property
    def content_width(self) -> float:
        width = self.page.width or t.MAX_WIDTH
        return min(width, t.MAX_WIDTH) - 2 * t.GUTTER

    # ----------------------------------------------------------- navigation
    def go(self, screen_cls: type[Screen], **kwargs) -> None:
        if self.screen:
            self.screen.dispose()
        screen = screen_cls(self, **kwargs)
        self.screen = screen
        body = ft.Container(
            screen.build(), width=t.MAX_WIDTH, expand=True,
            key=f"{screen_cls.__name__}-{id(screen)}",  # new key -> the switcher animates
        )
        self.switcher.content = body
        if screen.tab is None:
            self.page.navigation_bar = None
        else:
            self.nav.selected_index = screen.tab
            self.page.navigation_bar = self.nav
        try:
            self.page.update()
            self.page.run_task(screen.did_show)
        except (AttributeError, RuntimeError):
            screen.dispose()  # window/session already closed

    def _on_tab(self, e) -> None:
        from .screens import HistoryScreen, HomeScreen, PlanScreen, ReportScreen
        target = [HomeScreen, ReportScreen, PlanScreen, HistoryScreen][e.control.selected_index]
        if target is ReportScreen:
            self.current_report = self.current_report or self.store.latest
        self.go(target)

    def toast(self, message: str, icon_name: str = "CHECK_CIRCLE_ROUNDED") -> None:
        self.page.show_dialog(ft.SnackBar(
            ft.Row([ft.Icon(getattr(ft.Icons, icon_name), color="white", size=20),
                    ft.Text(message, color="white", expand=True)], spacing=10),
            bgcolor=t.TEXT, behavior=ft.SnackBarBehavior.FLOATING,
            shape=ft.RoundedRectangleBorder(radius=14), duration=2600,
            margin=ft.Margin.all(16),
        ))
