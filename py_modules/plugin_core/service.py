"""Common backend wiring for the download-client plugins.

A plugin subclasses MonitorService and supplies the client-specific parts. The
service owns settings, secrets, the poller, the update check and import from
file. `main.py` stays a thin adapter over Decky, which keeps this testable
without a running loader.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable, Mapping

from . import poller as poll
from .errors import PluginError, classify
from .http import fetch_json
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
        self.updates = UpdateChecker(
            load_build_info(plugin_dir),
            version,
            os.path.join(runtime_dir, "update.json"),
            fetch_json,
        )
        self.last_data: Any = None
        self.first_poll = True
        self._update_task: asyncio.Task | None = None
        self.update_info: dict[str, Any] | None = None

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

    connection_keys = frozenset({"base_url", "tls_verify", "ca_file"})

    # Lifecycle

    async def start(self) -> None:
        self.poller.start()
        # The loop always runs. check_update returns early while the user has it off.
        self._update_task = asyncio.get_event_loop().create_task(self._update_loop())

    async def stop(self) -> None:
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
            self.update_info = None
            return None
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
            "update": self.update_info,
            "import_path": import_path(self.user_home, self.plugin_id),
        }

    def set_visible(self, visible: bool) -> None:
        self.poller.set_visible(bool(visible))

    def set_game_running(self, running: bool) -> None:
        self.poller.set_game_running(bool(running))

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
