"""Poll loop with visibility-aware intervals, backoff and a quiet offline state.

Interval policy:
- 2 s while the Quick Access Menu panel is visible. The user is looking at it,
  so this wins even while a game runs.
- 60 s while the panel is hidden or a game runs.
- On failure, back off from 5 s, doubling to 5 min.
- After 3 consecutive unreachable failures, enter the offline state. Report it
  once, then stay quiet until a poll succeeds.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from .errors import UNREACHABLE, PluginError, classify

VISIBLE_INTERVAL = 2.0
HIDDEN_INTERVAL = 60.0
BACKOFF_START = 5.0
BACKOFF_MAX = 300.0
OFFLINE_AFTER = 3

UNCONFIGURED = "unconfigured"
CONNECTING = "connecting"
ONLINE = "online"
OFFLINE = "offline"
ERROR = "error"

Fetch = Callable[[], Awaitable[Any]]
Notify = Callable[[Any], Awaitable[None]]


class Poller:
    def __init__(
        self,
        fetch: Fetch,
        on_data: Notify,
        on_status: Notify,
        is_configured: Callable[[], bool] = lambda: True,
    ):
        self._fetch = fetch
        self._on_data = on_data
        self._on_status = on_status
        self._is_configured = is_configured
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.visible = False
        self.game_running = False
        self.failures = 0
        self.unreachable = 0
        self.state = CONNECTING
        self.error: PluginError | None = None
        self.last_success: float | None = None
        self._last_reported: dict | None = None

    # Inputs from the frontend

    def set_visible(self, visible: bool) -> None:
        changed = visible and not self.visible
        self.visible = bool(visible)
        if changed:
            self.wake()

    def set_game_running(self, running: bool) -> None:
        self.game_running = bool(running)

    def wake(self) -> None:
        """Poll now, for example after a user action or a settings change."""
        self._wake.set()

    def reset(self) -> None:
        """Forget failure history. Call when the connection settings change."""
        self.failures = 0
        self.unreachable = 0
        self.state = CONNECTING
        self.error = None
        self._last_reported = None
        self.wake()

    # Policy

    def interval(self) -> float:
        if self.failures:
            return min(BACKOFF_START * (2 ** (self.failures - 1)), BACKOFF_MAX)
        if self.visible:
            return VISIBLE_INTERVAL
        return HIDDEN_INTERVAL

    def status(self) -> dict:
        return {
            "state": self.state,
            "error": self.error.to_dict() if self.error else None,
            "last_success": self.last_success,
        }

    # Loop

    async def poll_once(self) -> None:
        if not self._is_configured():
            self.failures = 0
            self.state = UNCONFIGURED
            self.error = None
            await self._report()
            return
        try:
            data = await self._fetch()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001, classified
            self._record_failure(classify(exc))
            await self._report()
            return
        self.failures = 0
        self.unreachable = 0
        self.error = None
        self.state = ONLINE
        self.last_success = time.time()
        await self._report()
        await self._on_data(data)

    def _record_failure(self, err: PluginError) -> None:
        self.failures += 1
        if err.kind in UNREACHABLE:
            self.unreachable += 1
        else:
            self.unreachable = 0
        if err.kind in UNREACHABLE and self.unreachable >= OFFLINE_AFTER:
            self.state = OFFLINE
        elif err.kind in UNREACHABLE and self.state in (ONLINE, CONNECTING):
            # Do not flap the UI on one dropped poll. Keep the last state.
            pass
        elif err.kind not in UNREACHABLE:
            self.state = ERROR
        self.error = err

    async def _report(self) -> None:
        """Emit status only when the state or error message changes. This keeps the
        offline state to one event."""
        key = {"state": self.state, "message": self.error.message if self.error else None}
        if key == self._last_reported:
            return
        self._last_reported = key
        await self._on_status(self.status())

    async def run(self) -> None:
        while True:
            self._wake.clear()
            await self.poll_once()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.interval())
            except asyncio.TimeoutError:
                pass

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.get_event_loop().create_task(self.run())
        return self._task

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
