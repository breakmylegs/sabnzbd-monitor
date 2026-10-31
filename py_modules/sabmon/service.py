"""SABnzbd monitor backend."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from plugin_core import conntest
from plugin_core.errors import BAD_RESPONSE, UNREACHABLE, PluginError, classify
from plugin_core.http import TlsOptions, parse_base_url
from plugin_core.service import MonitorService

from .client import HINT_CONFIG_LOCKED, SabClient
from .states import num, pause_seconds
from .sync import HISTORY_LIMIT, QUEUE_TOP, SabState, TransitionTracker, project, project_history_slot

JOB_ACTIONS = ("pause", "resume")
TIMED_PAUSES = (15, 30, 60)
SPEED_LIMITS = (25, 50, 75, 100)
MOVES = ("top", "bottom")
HISTORY_PAGE = 50

# What to do while a game runs. Off unless the user picks one.
GAME_OFF = "off"
GAME_PAUSE = "pause"
GAME_LIMITS = {"limit_25": 25, "limit_50": 50}
GAME_ACTIONS = (GAME_OFF, GAME_PAUSE, *GAME_LIMITS)

# Releases before this one have authentication bypasses (GHSA-xrfq-jhgh-wqch,
# GHSA-rgqj-28c2-gxwp, GHSA-q326-jpxx-jmjc), per the 5.1.3 release notes.
SAFE_VERSION = (5, 1, 3)


def _bad(message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"kind": "bad_response", "message": message}}


def parse_version(text: str) -> tuple[int, ...]:
    """Leading numbers only: "5.1.3" gives (5, 1, 3) and "5.2.0Beta1" gives (5, 2, 0)."""
    parts = []
    for piece in str(text).strip().split("."):
        digits = ""
        for ch in piece:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
        if len(digits) < len(piece):
            break
    return tuple(parts)


class SabService(MonitorService):
    plugin_id = "sabnzbd-monitor"
    secret_names = ("api_key",)
    extra_defaults = {"game_action": GAME_OFF}

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.client: SabClient | None = None
        self.state = SabState()
        self.tracker = TransitionTracker()
        self.config_locked = False
        self._categories: list[str] | None = None
        self._game_mutex = threading.Lock()

    def save_settings(self, values):  # type: ignore[override]
        action = values.get("game_action") if hasattr(values, "get") else None
        if action is not None and action not in GAME_ACTIONS:
            raise ValueError("unknown game action")
        return super().save_settings(values)

    # Client

    def tls(self) -> TlsOptions:
        return TlsOptions(verify=self.settings.get("tls_verify"), ca_file=self.settings.get("ca_file"))

    def build_client(self) -> SabClient:
        return SabClient(parse_base_url(self.settings.get("base_url")), self.secrets.get("api_key"), self.tls())

    def get_client(self) -> SabClient:
        if self.client is None:
            self.client = self.build_client()
        return self.client

    def on_connection_changed(self) -> None:
        self.client = None
        self.state.reset()
        self.tracker.reset()
        self.config_locked = False
        self._categories = None

    # Poll

    def _poll_blocking(self) -> SabState:
        client = self.get_client()
        queue = client.queue(limit=QUEUE_TOP)
        history = client.history(limit=HISTORY_LIMIT, last_update=self.state.last_history_update)
        self.state.apply(queue, history)
        if self.game_ended_undo_due():
            # The undo at game end failed, for example while offline. Try again now.
            try:
                self._undo_game_change(client, from_poll=True)
            except Exception as exc:  # noqa: BLE001, classified
                self.log.warning("game-time undo failed: %s", classify(exc).kind)
        return self.state

    async def fetch(self) -> SabState:
        try:
            return await asyncio.to_thread(self._poll_blocking)
        except ValueError as err:
            raise PluginError(BAD_RESPONSE, "invalid base URL") from err

    def notifications_for(self, data: SabState) -> list[dict[str, str]]:
        return self.tracker.changes(data)

    def project(self, data: SabState) -> dict[str, Any]:
        out = project(data)
        out["config_locked"] = self.config_locked
        return out

    # Actions

    async def _config_action(self, fn) -> dict[str, Any]:
        """Run a config call and remember a config lock so the panel can say so."""
        result = await self.run_action(fn)
        error = result.get("error") or {}
        if not result["ok"] and error.get("message") == HINT_CONFIG_LOCKED:
            self.config_locked = True
        elif result["ok"]:
            self.config_locked = False
        return result

    async def pause_all(self) -> dict[str, Any]:
        client = self.get_client()
        return await self.run_action(client.pause)

    async def resume_all(self) -> dict[str, Any]:
        client = self.get_client()
        return await self.run_action(client.resume)

    async def pause_for(self, minutes: int) -> dict[str, Any]:
        if minutes not in TIMED_PAUSES:
            return {"ok": False, "error": {"kind": "bad_response", "message": "Pick 15, 30 or 60 minutes."}}
        client = self.get_client()
        return await self._config_action(lambda: client.pause_for(minutes))

    async def set_speed_limit(self, percent: int) -> dict[str, Any]:
        if percent not in SPEED_LIMITS:
            return {"ok": False, "error": {"kind": "bad_response", "message": "Pick 25, 50, 75 or 100 percent."}}
        client = self.get_client()
        return await self._config_action(lambda: client.set_speed_limit(percent))

    async def job_action(self, action: str, nzo_id: str) -> dict[str, Any]:
        if action not in JOB_ACTIONS:
            return {"ok": False, "error": {"kind": "bad_response", "message": "Unknown action."}}
        client = self.get_client()
        fn = client.pause_job if action == "pause" else client.resume_job
        return await self.run_action(lambda: fn(nzo_id))

    async def set_priority(self, nzo_id: str, priority: int) -> dict[str, Any]:
        client = self.get_client()
        return await self.run_action(lambda: client.set_priority(nzo_id, int(priority)))

    async def delete_job(self, nzo_id: str, delete_files: bool) -> dict[str, Any]:
        if not isinstance(nzo_id, str) or not nzo_id:
            return {"ok": False, "error": {"kind": "bad_response", "message": "Delete one job at a time."}}
        client = self.get_client()
        return await self.run_action(lambda: client.delete_jobs([nzo_id], bool(delete_files)))

    async def move_job(self, nzo_id: str, where: str) -> dict[str, Any]:
        if where not in MOVES:
            return _bad("Unknown move.")
        jobs = int(num(self.state.queue.get("noofslots_total")))
        if jobs < 2:
            # Also true just after a reconnect, before the first poll.
            return _bad("Nothing to move past. Wait for the queue to load, then try again.")
        position = 0 if where == "top" else jobs - 1
        client = self.get_client()
        return await self.run_action(lambda: client.move_job(nzo_id, position))

    async def get_categories(self) -> dict[str, Any]:
        """Fetched each time the list opens, so a category added on the server shows."""
        client = self.get_client()
        try:
            self._categories = await asyncio.to_thread(client.categories)
        except Exception as exc:  # noqa: BLE001, classified
            return {"ok": False, "error": classify(exc).to_dict()}
        return {"ok": True, "categories": list(self._categories)}

    async def change_category(self, nzo_id: str, category: str) -> dict[str, Any]:
        if self._categories is not None and category not in self._categories:
            return _bad("SABnzbd has no category with that name. Open the list again.")
        client = self.get_client()
        return await self.run_action(lambda: client.change_category(nzo_id, category))

    async def clear_warnings(self) -> dict[str, Any]:
        client = self.get_client()
        return await self.run_action(client.clear_warnings)

    async def get_history(self, failed_only: bool = False) -> dict[str, Any]:
        """The full history page. Fetched when the page opens, not on every poll."""
        client = self.get_client()
        try:
            history = await asyncio.to_thread(client.history_page, HISTORY_PAGE, bool(failed_only))
        except Exception as exc:  # noqa: BLE001, classified
            return {"ok": False, "error": classify(exc).to_dict()}
        slots = [s for s in history.get("slots") or [] if isinstance(s, dict)]
        return {
            "ok": True,
            "jobs": [project_history_slot(s) for s in slots],
            "total": int(num(history.get("noofslots"))),
            "limit": HISTORY_PAGE,
        }

    async def retry_job(self, nzo_id: str) -> dict[str, Any]:
        client = self.get_client()
        return await self.run_action(lambda: client.retry(nzo_id))

    async def retry_all(self) -> dict[str, Any]:
        client = self.get_client()
        return await self.run_action(client.retry_all)

    async def delete_history(self, nzo_id: str, delete_files: bool) -> dict[str, Any]:
        """One job, or "failed" for every failed job."""
        if not isinstance(nzo_id, str) or not nzo_id:
            return _bad("Pick a job.")
        client = self.get_client()
        return await self.run_action(lambda: client.delete_history(nzo_id, bool(delete_files)))

    async def get_server_stats(self) -> dict[str, Any]:
        client = self.get_client()
        try:
            raw = await asyncio.to_thread(client.server_stats)
        except Exception as exc:  # noqa: BLE001, classified
            return {"ok": False, "error": classify(exc).to_dict()}

        def sums(entry: Any) -> dict[str, int]:
            entry = entry if isinstance(entry, dict) else {}
            return {k: int(num(entry.get(k))) for k in ("day", "week", "month", "total")}

        servers = raw.get("servers") if isinstance(raw.get("servers"), dict) else {}
        return {
            "ok": True,
            "totals": sums(raw),
            "servers": sorted(
                ({"name": str(name), **sums(entry)} for name, entry in servers.items()),
                key=lambda s: -s["total"],
            ),
        }

    # Game-time pause or speed limit (opt-in)

    def game_changed_blocking(self, running: bool) -> None:
        client = self.get_client()
        if not running:
            self._undo_game_change(client)
            return
        action = self.settings.get("game_action")
        with self._game_mutex:
            if action == GAME_OFF or self.game_change():
                return
            queue = client.queue(limit=1)
            if action == GAME_PAUSE:
                if queue.get("paused"):
                    # Already paused, so the user chose it. Leave it alone afterwards too.
                    return
                client.pause()
                self.remember_game_change({"paused": True})
                self.log.info("game started, downloads paused")
                return
            target = GAME_LIMITS.get(action)
            current = int(num(queue.get("speedlimit"), 100)) or 100
            if target is None or current <= target:
                # Already as slow or slower. Nothing to do.
                return
            client.set_speed_limit(target)
            self.remember_game_change({"limit": target, "previous": current})
            self.log.info("game started, speed limit %d%%", target)

    def _undo_game_change(self, client: SabClient, from_poll: bool = False) -> None:
        # The game-end task and a poll can both get here. The mutex stops a double undo.
        with self._game_mutex:
            if from_poll and not self.game_ended_undo_due():
                # A game started while this poll ran.
                return
            record = self.game_change()
            if not record:
                return
            queue = client.queue(limit=1)
            if record.get("paused"):
                # A timed pause set during the game is the user's choice. Leave it.
                if queue.get("paused") and pause_seconds(queue.get("pause_int")) is None:
                    client.resume()
                    self.log.info("game ended, downloads resumed")
            elif "limit" in record:
                current = int(num(queue.get("speedlimit"), 100)) or 100
                previous = int(num(record.get("previous"), 100))
                if current == record["limit"] and 1 <= previous <= 100:
                    try:
                        client.set_speed_limit(previous)
                    except PluginError as err:
                        # A config lock will not clear by itself. Stop retrying on every poll.
                        if err.kind not in UNREACHABLE:
                            self.game_memory.clear()
                        raise
                    self.log.info("game ended, speed limit back to %d%%", previous)
            # Cleared even when the user changed it during the game.
            self.game_memory.clear()

    async def get_warnings(self) -> dict[str, Any]:
        client = self.get_client()
        try:
            items = await asyncio.to_thread(client.warnings)
        except Exception as exc:  # noqa: BLE001, classified
            return {"ok": False, "error": classify(exc).to_dict()}
        return {
            "ok": True,
            "warnings": [
                {"type": str(w.get("type") or ""), "text": str(w.get("text") or "")[:300], "time": w.get("time")}
                for w in items[-20:]
            ],
        }

    # Connection test

    async def test_connection(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._test_blocking)

    def _test_blocking(self) -> dict[str, Any]:
        report = conntest.Report()
        base = conntest.check_url(report, self.settings.get("base_url"))
        if base is None:
            return report.to_dict()
        client = SabClient(base, self.secrets.get("api_key"), self.tls())
        ok, version = conntest.run_step(report, conntest.VERSION, client.version)
        if not ok:
            return report.to_dict()
        report.server_version = version
        report.passed(conntest.VERSION, f"SABnzbd {version}")
        parsed = parse_version(version)
        if parsed and parsed < SAFE_VERSION:
            report.warnings.append(
                f"SABnzbd {version} has security flaws fixed in 5.1.3, including ways to skip the login. "
                "Update the server to 5.1.3 or newer."
            )
        if not self.secrets.has("api_key"):
            report.failed(conntest.AUTH, "Enter the full API key from SABnzbd Config, General.")
            return report.to_dict()
        ok, _ = conntest.run_step(report, conntest.AUTH, lambda: client.queue(limit=1))
        if not ok:
            return report.to_dict()
        report.auth_path = "api_key"
        report.passed(conntest.AUTH, "Signed in with the API key")
        report.ok = True
        return report.to_dict()
