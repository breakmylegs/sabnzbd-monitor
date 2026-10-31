"""Common backend wiring for the download-client plugins.

A plugin subclasses MonitorService and supplies the client-specific parts. The
service owns settings, secrets, the poller, the update check and import from
file. `main.py` stays a thin adapter over Decky, which keeps this testable
without a running loader.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any, Awaitable, Callable, Mapping

from . import poller as poll
from .errors import PluginError, classify
from .game_mode import GameModeMemory
from .http import fetch_json, set_user_agent
from .secrets import SecretStore, apply_import, import_path, read_import_file
from .settings import JsonStore
from .update_check import UpdateChecker, load_build_info

Emit = Callable[..., Awaitable[None]]

COMMON_DEFAULTS: dict[str, Any] = {
    "base_url": "",
    "tls_verify": True,
    "ca_file": "",
    "notifications": True,
    "notify_in_game": True,
    "update_check": True,
    "remove_data_on_uninstall": False,
}

EVENT_STATUS = "status"
EVENT_DATA = "data"
EVENT_NOTIFY = "notify"
EVENT_UPDATE = "update"
EVENT_SETTINGS = "settings"


class MonitorService:
    plugin_id = "plugin"
    secret_names: tuple[str, ...] = ()
    extra_defaults: Mapping[str, Any] = {}

    def __init__(
        self,
        settings_dir: str,
        runtime_dir: str,
        plugin_dir: str,
        user_home: str,
        version: str,
        emit: Emit,
        logger: Any,
    ):
        self.settings_dir = settings_dir
        self.runtime_dir = runtime_dir
        self.user_home = user_home
        self.version = version
        self._emit = emit
        self.log = logger
        self.settings = JsonStore(os.path.join(settings_dir, "settings.json"), {**COMMON_DEFAULTS, **self.extra_defaults})
        self.secrets = SecretStore(os.path.join(settings_dir, "secrets.json"), self.secret_names)
        self.poller = poll.Poller(self._fetch, self._on_data, self._on_status, self.is_configured)
        build_info = load_build_info(plugin_dir)
        set_user_agent(build_info, version)
        self.updates = UpdateChecker(
            build_info,
            version,
            os.path.join(runtime_dir, "update.json"),
            fetch_json,
        )
        self.last_data: Any = None
        self.first_poll = True
        self._update_task: asyncio.Task | None = None
        self.update_info: dict[str, Any] | None = None
        self.game_memory = GameModeMemory(runtime_dir)
        self._game_lock = asyncio.Lock()
        self._game_task: asyncio.Task | None = None
        self._panel_visible = False
        self._route_visible = False
        # False until the frontend first says whether a game runs. Until then a
        # leftover game-time record is not undone, because a game may be running.
        self.game_state_known = False

    # Hooks for subclasses

    def is_configured(self) -> bool:
        return bool(self.settings.get("base_url"))

    def on_connection_changed(self) -> None:
        """Drop clients and caches built from the old settings."""

    async def fetch(self) -> Any:
        raise NotImplementedError

    def notifications_for(self, data: Any) -> list[dict[str, str]]:
        """Return toasts for transitions since the last poll. Called on every poll,
        including the first, so subclasses can record the baseline."""
        return []

    def project(self, data: Any) -> Any:
        """The compact payload sent to the frontend."""
        return data

    async def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    def game_changed_blocking(self, running: bool) -> None:
        """Called in a worker thread when a game starts or stops. Subclasses
        apply or undo their opt-in game-time change here. Errors are logged."""

    connection_keys = frozenset({"base_url", "tls_verify", "ca_file"})

    # Lifecycle

    async def start(self) -> None:
        self.poller.start()
        # The loop always runs. check_update returns early while the user has it off.
        self._update_task = asyncio.get_event_loop().create_task(self._update_loop())

    async def stop(self) -> None:
        if self._game_task and not self._game_task.done():
            # Let a pending game-time change or undo finish, briefly.
            try:
                await asyncio.wait_for(asyncio.shield(self._game_task), timeout=6)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        await self.poller.stop()
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None

    async def uninstall(self) -> None:
        """Remove stored data only if the user opted in."""
        if self.settings.get("remove_data_on_uninstall"):
            self.secrets.delete_file()
            self.settings.delete_file()

    # Poll plumbing

    async def _fetch(self) -> Any:
        return await self.fetch()

    async def _on_data(self, data: Any) -> None:
        toasts = self.notifications_for(data)
        first = self.first_poll
        self.first_poll = False
        self.last_data = self.project(data)
        await self._emit(EVENT_DATA, self.last_data)
        if first or not self._toasts_allowed():
            return
        for toast in toasts:
            await self._emit(EVENT_NOTIFY, toast)

    def _toasts_allowed(self) -> bool:
        if not self.settings.get("notifications"):
            return False
        if self.poller.game_running and not self.settings.get("notify_in_game"):
            return False
        return True

    async def _on_status(self, status: dict) -> None:
        await self._emit(EVENT_STATUS, status)

    async def _update_loop(self) -> None:
        while True:
            await self.check_update()
            await asyncio.sleep(60 * 60)

    async def check_update(self, force: bool = False) -> dict[str, Any] | None:
        if not self.settings.get("update_check") and not force:
            # No network call, but the panel still gets the version and link.
            self.update_info = self.updates.known()
            return self.update_info
        self.update_info = await asyncio.to_thread(self.updates.check, force)
        await self._emit(EVENT_UPDATE, self.update_info)
        return self.update_info

    # Frontend API

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "settings": self.settings.snapshot(),
            "secrets": self.secrets.public_view(),
            "status": self.poller.status(),
            "data": self.last_data,
            # Before the first check, still send the version and install link.
            "update": self.update_info or self.updates.known(),
            "import_path": import_path(self.user_home, self.plugin_id),
        }

    def set_visible(self, visible: bool) -> None:
        self._panel_visible = bool(visible)
        self.poller.set_visible(self._panel_visible or self._route_visible)

    def set_route_visible(self, visible: bool) -> None:
        """A full-screen page is open. The Quick Access Menu reports hidden
        then, so the page keeps the fast poll on by itself."""
        self._route_visible = bool(visible)
        self.poller.set_visible(self._panel_visible or self._route_visible)

    def _server_tag(self) -> str:
        return hashlib.sha256(str(self.settings.get("base_url")).encode("utf-8")).hexdigest()[:16]

    def remember_game_change(self, record: dict[str, Any]) -> None:
        self.game_memory.set({**record, "server": self._server_tag()})

    def game_change(self) -> dict[str, Any] | None:
        """The recorded game-time change, if it was made on the server in use now."""
        record = self.game_memory.get()
        if record and record.get("server") != self._server_tag():
            # Made on another server. Undoing it here would change the wrong one.
            self.game_memory.clear()
            return None
        return record

    def game_ended_undo_due(self) -> bool:
        """A leftover game-time change should be undone now: the frontend has
        reported, no game runs, and a record is on disk."""
        return self.game_state_known and not self.poller.game_running and self.game_memory.get() is not None

    def set_game_running(self, running: bool) -> None:
        running = bool(running)
        # The first report counts as a change, so a record left by a restart
        # mid-game is undone as soon as the panel says no game is running.
        changed = running != self.poller.game_running or not self.game_state_known
        self.game_state_known = True
        self.poller.set_game_running(running)
        if not changed or not self.is_configured():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop, as in synchronous tests. Decky always calls this from one.
            return
        self._game_task = loop.create_task(self._game_changed(running))

    async def _game_changed(self, running: bool) -> None:
        # One change at a time, so a quick start and stop apply in order.
        async with self._game_lock:
            try:
                await asyncio.to_thread(self.game_changed_blocking, running)
            except Exception as exc:  # noqa: BLE001, classified
                self.log.warning("game-time change failed: %s", classify(exc).kind)
            else:
                self.poller.wake()

    def _connection_reset(self) -> None:
        self.on_connection_changed()
        self.first_poll = True
        self.last_data = None
        self.poller.reset()

    def save_settings(self, values: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(values, Mapping):
            raise ValueError("settings must be an object")
        changed = self.settings.update(values)
        if self.connection_keys.intersection(changed):
            self._connection_reset()
        return self.snapshot()

    def set_secret(self, name: str, value: str) -> dict[str, Any]:
        self.secrets.set(name, value)
        self._connection_reset()
        return self.snapshot()

    def clear_secret(self, name: str) -> dict[str, Any]:
        self.secrets.clear(name)
        self._connection_reset()
        return self.snapshot()

    def import_from_file(self) -> dict[str, Any]:
        path = import_path(self.user_home, self.plugin_id)
        try:
            settings, secrets = read_import_file(path, self.settings.defaults.keys(), self.secret_names)
            if settings:
                # Same validation as the settings form.
                self.save_settings(settings)
            apply_import(self.secrets, secrets)
        except ValueError as err:
            return {"ok": False, "message": str(err), "path": path}
        self._connection_reset()
        imported = sorted(list(settings) + list(secrets))
        self.log.info("imported %d values from file", len(imported))
        return {"ok": True, "imported": imported, "path": path, "snapshot": self.snapshot()}

    def delete_import_file(self) -> dict[str, Any]:
        path = import_path(self.user_home, self.plugin_id)
        try:
            os.unlink(path)
        except FileNotFoundError:
            return {"ok": True, "message": "The import file was already gone."}
        except OSError:
            return {"ok": False, "message": f"Could not delete {path}. Delete it with a file manager."}
        return {"ok": True, "message": "Import file deleted."}

    async def run_action(self, fn: Callable[[], Any]) -> dict[str, Any]:
        """Run a blocking client call, then poll at once so the UI catches up."""
        try:
            await asyncio.to_thread(fn)
        except Exception as exc:  # noqa: BLE001, classified
            err = classify(exc)
            self.log.warning("action failed: %s", err.kind)
            return {"ok": False, "error": err.to_dict()}
        self.poller.wake()
        return {"ok": True}


def error_result(exc: BaseException) -> dict[str, Any]:
    err = exc if isinstance(exc, PluginError) else classify(exc)
    return {"ok": False, "error": err.to_dict()}
