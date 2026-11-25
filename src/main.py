"""CarPulse: check your car's health with a 5-minute drive.

Run on a computer:   flet run src/main.py      (or: python src/main.py)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flet as ft  # noqa: E402

from carpulse.ui.app import CarPulseApp  # noqa: E402


def main(page: ft.Page) -> None:
    CarPulseApp(page)


if __name__ == "__main__":
    if os.environ.get("CARPULSE_WEB"):  # serve in a browser instead of a desktop window
        ft.run(main, view=None, port=int(os.environ.get("CARPULSE_PORT", "8550")), no_cdn=True)
    else:
        ft.run(main)
