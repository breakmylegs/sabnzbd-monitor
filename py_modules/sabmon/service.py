"""SABnzbd monitor backend."""

from __future__ import annotations

import asyncio
from typing import Any

from plugin_core import conntest
from plugin_core.errors import BAD_RESPONSE, PluginError, classify
from plugin_core.http import TlsOptions, parse_base_url
from plugin_core.service import MonitorService

from .client import HINT_CONFIG_LOCKED, SabClient
from .sync import HISTORY_LIMIT, QUEUE_TOP, SabState, TransitionTracker, project

JOB_ACTIONS = ("pause", "resume")
TIMED_PAUSES = (15, 30, 60)
SPEED_LIMITS = (25, 50, 75, 100)


class SabService(MonitorService):
    plugin_id = "sabnzbd-monitor"
    secret_names = ("api_key",)

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.client: SabClient | None = None
        self.state = SabState()
        self.tracker = TransitionTracker()
        self.config_locked = False

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

    # Poll

    def _poll_blocking(self) -> SabState:
        client = self.get_client()
        queue = client.queue(limit=QUEUE_TOP)
        history = client.history(limit=HISTORY_LIMIT, last_update=self.state.last_history_update)
        self.state.apply(queue, history)
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
