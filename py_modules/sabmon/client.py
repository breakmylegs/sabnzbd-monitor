"""SABnzbd API client.

Every call is GET <base>/api?output=json&apikey=<key>&mode=<mode>.

How SABnzbd 5.1 and the 5.2 betas report failures:
- Missing or wrong key: HTTP 403 with a text/plain body, "API Key Required" or
  "API Key Incorrect". The body is empty when the server has api_warnings off,
  so the status code decides, and the text only refines the message.
- Host name not whitelisted: HTTP 403 "Access denied - Hostname verification failed".
- Configuration locked: HTTP 200 JSON {"status": false, "error": "Configuration locked"}.
- The NZB key works only for adding jobs. Queue and history need the full API key.

nzo_id values are opaque. From 5.0.1 they are GUIDs.
"""

from __future__ import annotations

from typing import Any, Iterable

from plugin_core.errors import AUTH, BAD_RESPONSE, FORBIDDEN, HTTP_ERROR, PluginError, from_status
from plugin_core.http import BaseUrl, HttpClient, TlsOptions

from .states import PRIORITY_NAMES, num

CONFIG_LOCKED = "Configuration locked"

HINT_KEY_REQUIRED = "No API key stored. Enter the full API key from SABnzbd Config, General."
HINT_KEY_INCORRECT = (
    "SABnzbd rejected the API key. Use the full API key from Config, General, not the NZB key."
)
HINT_KEY_REJECTED = (
    "SABnzbd refused access. Check the API key is the full key, not the NZB key, "
    "and that this device is allowed in Config, General."
)
HINT_HOSTNAME = (
    "SABnzbd rejected the host name. Add it to host_whitelist in Config, Special, then restart SABnzbd."
)
HINT_CONFIG_LOCKED = "Configuration locked. Turn off the config lock in SABnzbd to change this setting."


def _join_ids(ids: Iterable[str] | str) -> str:
    if isinstance(ids, str):
        ids = [ids]
    clean = [i for i in ids if isinstance(i, str) and i and "," not in i]
    if not clean:
        raise ValueError("no jobs selected")
    return ",".join(clean)


class SabClient:
    def __init__(self, base: BaseUrl, api_key: str, tls: TlsOptions | None = None, timeout: float = 5.0):
        self.base = base
        self.api_key = api_key
        self.http = HttpClient(base, timeout=timeout, tls=tls or TlsOptions())

    def _get(self, mode: str, with_key: bool = True, **params: Any) -> Any:
        query: dict[str, Any] = {"mode": mode, "output": "json", **params}
        if with_key:
            if not self.api_key:
                raise PluginError(AUTH, "no key", hint=HINT_KEY_REQUIRED)
            query["apikey"] = self.api_key
        res = self.http.get("api", params=query)
        if res.status == 403:
            text = res.text().strip()
            if "Hostname verification" in text:
                raise PluginError(FORBIDDEN, "hostname", 403, hint=HINT_HOSTNAME)
            if text == "API Key Required":
                raise PluginError(AUTH, "key required", 403, hint=HINT_KEY_REQUIRED)
            if text == "API Key Incorrect":
                raise PluginError(AUTH, "key incorrect", 403, hint=HINT_KEY_INCORRECT)
            raise PluginError(FORBIDDEN, "access denied", 403, hint=HINT_KEY_REJECTED)
        if res.status == 401:
            raise PluginError(AUTH, "unauthorised", 401, hint=HINT_KEY_REJECTED)
        if res.status == 404:
            raise PluginError(BAD_RESPONSE, "no api", 404, hint="No SABnzbd API at this address. Check the port and path.")
        if res.status >= 400:
            raise from_status(res.status)
        data = res.json()
        if isinstance(data, dict) and data.get("status") is False and "error" in data:
            error = str(data.get("error") or "")
            if CONFIG_LOCKED in error:
                raise PluginError(FORBIDDEN, "config locked", 200, hint=HINT_CONFIG_LOCKED)
            # Other in-band errors carry a short server message with no secrets.
            raise PluginError(HTTP_ERROR, "api error", 200, hint=f"SABnzbd said: {error[:120]}")
        return data

    # Reads

    def version(self) -> str:
        data = self._get("version", with_key=False)
        version = data.get("version") if isinstance(data, dict) else None
        if not isinstance(version, str):
            raise PluginError(BAD_RESPONSE, "no version")
        return version

    def queue(self, limit: int = 8) -> dict[str, Any]:
        data = self._get("queue", start=0, limit=limit)
        queue = data.get("queue") if isinstance(data, dict) else None
        if not isinstance(queue, dict):
            raise PluginError(BAD_RESPONSE, "queue shape")
        return queue

    def history(self, limit: int = 10, last_update: int | None = None) -> dict[str, Any] | None:
        """None means nothing changed since `last_update`."""
        params: dict[str, Any] = {"limit": limit}
        if last_update is not None:
            params["last_history_update"] = last_update
        data = self._get("history", **params)
        history = data.get("history") if isinstance(data, dict) else None
        if history is False:
            return None
        if not isinstance(history, dict):
            raise PluginError(BAD_RESPONSE, "history shape")
        return history

    def warnings(self) -> list[dict[str, Any]]:
        data = self._get("warnings")
        items = data.get("warnings") if isinstance(data, dict) else None
        return [w for w in items if isinstance(w, dict)] if isinstance(items, list) else []

    # Changes

    def pause(self) -> None:
        self._get("pause")

    def resume(self) -> None:
        self._get("resume")

    def pause_for(self, minutes: int) -> None:
        if minutes <= 0 or minutes > 24 * 60:
            raise ValueError("pause must be 1 to 1440 minutes")
        self._get("config", name="set_pause", value=int(minutes))

    def pause_job(self, nzo_id: str) -> None:
        self._get("queue", name="pause", value=_join_ids(nzo_id))

    def resume_job(self, nzo_id: str) -> None:
        self._get("queue", name="resume", value=_join_ids(nzo_id))

    def delete_jobs(self, nzo_ids: Iterable[str] | str, delete_files: bool) -> None:
        params: dict[str, Any] = {"name": "delete", "value": _join_ids(nzo_ids)}
        if delete_files:
            params["del_files"] = 1
        self._get("queue", **params)

    def set_priority(self, nzo_id: str, priority: int) -> None:
        if priority not in PRIORITY_NAMES:
            raise ValueError("priority must be -1, 0, 1 or 2")
        self._get("queue", name="priority", value=_join_ids(nzo_id), value2=priority)

    def set_speed_limit(self, percent: int) -> None:
        if not 1 <= percent <= 100:
            raise ValueError("speed limit must be 1 to 100 percent")
        self._get("config", name="speedlimit", value=int(percent))

    def move_job(self, nzo_id: str, position: int) -> None:
        """0 is the top. SABnzbd may give the job the priority of the job it passes."""
        if isinstance(position, bool) or not isinstance(position, int) or position < 0:
            raise ValueError("position must be 0 or more")
        data = self._get("switch", value=_join_ids(nzo_id), value2=position)
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, dict) and num(result.get("position"), 0) < 0:
            # -1 means SABnzbd did not move it, for example a job that just finished.
            raise PluginError(HTTP_ERROR, "not moved", 200, hint="SABnzbd did not move the job. Refresh and try again.")

    def categories(self) -> list[str]:
        """Category names. "*" is the default category."""
        data = self._get("get_cats")
        cats = data.get("categories") if isinstance(data, dict) else None
        return [c for c in cats if isinstance(c, str) and c] if isinstance(cats, list) else []

    def change_category(self, nzo_id: str, category: str) -> None:
        if not isinstance(category, str) or not category:
            raise ValueError("pick a category")
        self._get("change_cat", value=_join_ids(nzo_id), value2=category)

    def clear_warnings(self) -> None:
        self._get("warnings", name="clear")

    # History

    def history_page(self, limit: int, failed_only: bool = False) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": int(limit)}
        if failed_only:
            params["failed_only"] = 1
        data = self._get("history", **params)
        history = data.get("history") if isinstance(data, dict) else None
        if not isinstance(history, dict):
            raise PluginError(BAD_RESPONSE, "history shape")
        return history

    def retry(self, nzo_id: str) -> None:
        self._get("retry", value=_join_ids(nzo_id))

    def retry_all(self) -> None:
        self._get("retry_all")

    def delete_history(self, nzo_ids: Iterable[str] | str, delete_files: bool = False) -> None:
        """Archived by default, as in SABnzbd's own interface. `nzo_ids` may be "failed"."""
        value = "failed" if nzo_ids == "failed" else _join_ids(nzo_ids)
        params: dict[str, Any] = {"name": "delete", "value": value}
        if delete_files:
            params["del_files"] = 1
        self._get("history", **params)

    def server_stats(self) -> dict[str, Any]:
        """Bytes downloaded per day, week, month and in total, overall and per server."""
        data = self._get("server_stats")
        if not isinstance(data, dict):
            raise PluginError(BAD_RESPONSE, "server stats shape")
        return data
