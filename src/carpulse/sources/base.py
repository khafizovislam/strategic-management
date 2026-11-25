"""The interface every vehicle data source implements.

The simulator implements it now. A real Bluetooth LE OBD adapter will implement
the same interface later, so nothing else in the app has to change.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from ..models import Sample, TroubleCode

DRIVE_SECONDS = 300  # the 5-minute check drive


class DataSource(Protocol):
    name: str

    async def connect(self) -> None: ...

    def stream(self) -> AsyncIterator[Sample]:
        """Yield one Sample per second of driving until the drive is complete."""
        ...

    async def read_trouble_codes(self) -> list[TroubleCode]: ...

    async def close(self) -> None: ...
