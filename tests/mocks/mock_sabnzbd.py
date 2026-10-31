"""Mock SABnzbd API for tests and local UI work.

Run standalone: python tools/mock_sabnzbd.py --port 8091 --api-key KEY
Use from tests: MockSab(api_key=..., nzb_key=...).start() returns the base URL.

Models what the plugin relies on:
- GET /api?output=json&apikey=...&mode=...
- mode=version needs no key. Everything else needs the full API key. The NZB
  key is refused for queue and history.
- A missing or wrong key gets HTTP 403 with a plain-text body, "API Key Required"
  or "API Key Incorrect". The body is empty when api_warnings is off.
  "Configuration locked" is a JSON error with HTTP 200.
- Numbers as strings, as SABnzbd sends them.
- history with last_history_update returns false when nothing changed.
- nzo_id values are opaque. 5.0.1 and later use GUIDs.
- switch takes a numeric position in value2, 0 for the top, as in nzbqueue.py.
- retry, retry_all, history delete (ids or "failed"), failed_only, get_cats,
  change_cat ("*" is the default), warnings clear and server_stats (bytes).
"""

from __future__ import annotations

import argparse
import json
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

NZB_KEY_MODES = {"addfile", "addurl", "addlocalfile", "version", "auth"}


def _slot(name: str, status: str, pct: int, priority: str = "Normal", cat: str = "*") -> dict[str, Any]:
    return {"nzo_id": f"SABnzbd_nzo_{uuid.uuid4()}", "filename": name, "status": status, "percentage": str(pct),
            "timeleft": "0:10:00", "sizeleft": "1.2 GB", "mb": "2000.0", "mbleft": "1200.0",
            "priority": priority, "cat": cat}


class MockState:
    def __init__(self, api_key: str = "", nzb_key: str = "", version: str = "5.1.3", config_locked: bool = False,
                 api_warnings: bool = True, url_base: str = ""):
        self.api_warnings = api_warnings
        self.url_base = url_base.rstrip("/")
        self.api_key = api_key
        self.nzb_key = nzb_key
        self.version = version
        self.config_locked = config_locked
        self.paused = False
        self.pause_int = "0"
        self.speedlimit = "100"
        self.have_warnings = "0"
        self.queue = [_slot("Example.Linux.ISO", "Downloading", 40), _slot("Public.Domain.Film", "Queued", 0)]
        self.history: list[dict[str, Any]] = [
            {"nzo_id": f"SABnzbd_nzo_{uuid.uuid4()}", "name": "Open.Dataset", "status": "Completed",
             "fail_message": "", "size": "3.1 GB", "completed": 1_760_000_000, "loaded": False, "action_line": ""},
        ]
        self.last_history_update = 1
        self.categories = ["*", "movies", "software"]
        self.calls: list[dict[str, str]] = []
        self.lock = threading.Lock()

    def touch_history(self) -> None:
        self.last_history_update += 1

    def finish_first(self, failed: bool = False) -> None:
        with self.lock:
            slot = self.queue.pop(0)
            stage_log = [{"name": "Repair", "actions": ["Repair failed, not enough repair blocks <br/>(need 12)"]}]
            self.history.insert(0, {
                "nzo_id": slot["nzo_id"], "name": slot["filename"], "status": "Failed" if failed else "Completed",
                "fail_message": "Repair failed, not enough repair blocks" if failed else "", "size": "2.0 GB",
                "completed": 1_760_000_100, "loaded": False, "action_line": "", "category": slot["cat"],
                "stage_log": stage_log if failed else []})
            self.touch_history()

    def start_post_processing(self, stage: str = "Extracting") -> None:
        with self.lock:
            slot = self.queue.pop(0)
            self.history.insert(0, {"nzo_id": slot["nzo_id"], "name": slot["filename"], "status": stage,
                                    "fail_message": "", "size": "2.0 GB", "completed": 0, "loaded": True,
                                    "action_line": "Unpacking 1/3"})
            self.touch_history()


def make_handler(state: MockState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _json(self, data: Any, status: int = 200):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, message: str):
            self._json({"status": False, "error": message})

        def _forbidden(self, message: str):
            body = (message if state.api_warnings else "").encode()
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parts = urllib.parse.urlsplit(self.path)
            if parts.path.rstrip("/") != f"{state.url_base}/api":
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            q = dict(urllib.parse.parse_qsl(parts.query))
            state.calls.append(q)
            mode = q.get("mode", "")
            if mode == "version":
                return self._json({"version": state.version})
            key = q.get("apikey", "")
            if not key:
                return self._forbidden("API Key Required")
            if key == state.nzb_key and state.nzb_key and mode not in NZB_KEY_MODES:
                return self._forbidden("API Key Incorrect")
            if key != state.api_key and key != state.nzb_key:
                return self._forbidden("API Key Incorrect")
            with state.lock:
                return self._route(mode, q)

        def _route(self, mode: str, q: dict[str, str]):
            name = q.get("name", "")
            if mode == "queue" and name == "":
                start, limit = int(q.get("start", 0)), int(q.get("limit", 0) or 1000)
                slots = state.queue[start:start + limit]
                return self._json({"queue": {
                    "status": "Paused" if state.paused else ("Downloading" if state.queue else "Idle"),
                    "paused": state.paused, "speed": "0 " if state.paused else "5.2 M", "kbpersec": "0.00" if state.paused else "5324.80",
                    "timeleft": "0:12:00", "mbleft": "3200.00", "sizeleft": "3.1 GB", "noofslots_total": len(state.queue),
                    "speedlimit": state.speedlimit, "have_warnings": state.have_warnings, "pause_int": state.pause_int,
                    "diskspace1": "120.50", "diskspace2": "1450.25", "diskspacetotal1": "500.00",
                    "diskspacetotal2": "4000.00", "have_quota": False, "quota": "0 ", "left_quota": "0 ",
                    "slots": [dict(s, index=i) for i, s in enumerate(slots, start)]}})
            if mode == "queue" and name in ("pause", "resume"):
                for slot in state.queue:
                    if slot["nzo_id"] == q.get("value"):
                        slot["status"] = "Paused" if name == "pause" else "Queued"
                return self._json({"status": True, "nzo_ids": [q.get("value")]})
            if mode == "queue" and name == "delete":
                ids = q.get("value", "").split(",")
                state.queue = [s for s in state.queue if s["nzo_id"] not in ids]
                return self._json({"status": True, "nzo_ids": ids})
            if mode == "queue" and name == "priority":
                for slot in state.queue:
                    if slot["nzo_id"] == q.get("value"):
                        slot["priority"] = {"-1": "Low", "0": "Normal", "1": "High", "2": "Force"}.get(q.get("value2", ""), "Normal")
                return self._json({"position": 0})
            if mode == "history" and name == "delete":
                value = q.get("value", "")
                if value.lower() == "failed":
                    state.history = [h for h in state.history if h["status"] != "Failed"]
                else:
                    ids = value.split(",")
                    state.history = [h for h in state.history if h["nzo_id"] not in ids]
                state.touch_history()
                return self._json({"status": True})
            if mode == "history":
                since = q.get("last_history_update")
                if since is not None and int(since) == state.last_history_update:
                    return self._json({"history": False})
                limit = int(q.get("limit", 0) or 1000)
                items = [h for h in state.history if h["status"] == "Failed"] if q.get("failed_only") == "1" else state.history
                return self._json({"history": {"slots": items[:limit], "noofslots": len(items),
                                               "last_history_update": state.last_history_update}})
            if mode in ("retry", "retry_all"):
                targets = [h for h in state.history if h["status"] == "Failed"
                           and (mode == "retry_all" or h["nzo_id"] == q.get("value"))]
                if mode == "retry" and not targets:
                    return self._error("item does not exist")
                for h in targets:
                    state.history.remove(h)
                    state.queue.append(_slot(h["name"], "Queued", 0))
                state.touch_history()
                if mode == "retry":
                    return self._json({"status": True, "nzo_id": state.queue[-1]["nzo_id"]})
                return self._json({"status": [s["nzo_id"] for s in state.queue[-len(targets):]] if targets else []})
            if mode == "switch":
                ids = [s["nzo_id"] for s in state.queue]
                if q.get("value") not in ids:
                    return self._json({"result": {"position": -1, "priority": 0}})
                position = int(q.get("value2", "0"))
                if not 0 <= position < len(state.queue):
                    # SABnzbd treats an index past the end as an unknown job id and moves nothing.
                    return self._json({"result": {"position": -1, "priority": 0}})
                slot = state.queue.pop(ids.index(q["value"]))
                state.queue.insert(position, slot)
                return self._json({"result": {"position": position, "priority": 0}})
            if mode == "get_cats":
                return self._json({"categories": list(state.categories)})
            if mode == "change_cat":
                for slot in state.queue:
                    if slot["nzo_id"] == q.get("value"):
                        slot["cat"] = q.get("value2", "*")
                return self._json({"status": True})
            if mode == "server_stats":
                return self._json({"day": 2_000_000_000, "week": 9_000_000_000, "month": 40_000_000_000,
                                   "total": 900_000_000_000,
                                   "servers": {"news.example.com": {"day": 2_000_000_000, "week": 9_000_000_000,
                                                                    "month": 40_000_000_000, "total": 800_000_000_000,
                                                                    "daily": {}, "articles_tried": {},
                                                                    "articles_success": {}},
                                               "backup.example.net": {"day": 0, "week": 0, "month": 0,
                                                                      "total": 100_000_000_000}}})
            if mode == "pause":
                state.paused = True
                return self._json({"status": True})
            if mode == "resume":
                state.paused = False
                state.pause_int = "0"
                return self._json({"status": True})
            if mode == "config":
                if state.config_locked:
                    return self._error("Configuration locked")
                if name == "set_pause":
                    state.paused = True
                    state.pause_int = f"{int(q.get('value', 0))}:00"
                    return self._json({"status": True})
                if name == "speedlimit":
                    state.speedlimit = q.get("value", "100")
                    return self._json({"status": True})
                return self._error("not implemented")
            if mode == "warnings" and name == "clear":
                state.have_warnings = "0"
                return self._json({"status": True})
            if mode == "warnings":
                return self._json({"warnings": [] if state.have_warnings == "0" else [
                    {"text": "Example warning", "type": "WARNING", "time": 1_760_000_000}]})
            return self._error("not implemented")

    return Handler


class MockSab:
    def __init__(self, port: int = 0, **kwargs: Any):
        self.state = MockState(**kwargs)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self.state))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def start(self) -> str:
        self.thread.start()
        return self.url

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--nzb-key", default="")
    args = parser.parse_args()
    mock = MockSab(args.port, api_key=args.api_key, nzb_key=args.nzb_key)
    print(f"Mock SABnzbd on {mock.url}")
    mock.httpd.serve_forever()


if __name__ == "__main__":
    main()
