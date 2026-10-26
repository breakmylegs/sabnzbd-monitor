"""SABnzbd state cache, the compact projection sent to the UI, and toasts."""

from __future__ import annotations

from typing import Any

from . import states
from .states import num, pause_seconds, seconds

QUEUE_TOP = 8
RECENT = 5
HISTORY_LIMIT = 10
KIB = 1024


class SabState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.queue: dict[str, Any] = {}
        self.history_slots: list[dict[str, Any]] = []
        self.last_history_update: int | None = None

    def apply(self, queue: dict[str, Any], history: dict[str, Any] | None) -> None:
        self.queue = queue
        if history is None:
            return
        slots = history.get("slots")
        self.history_slots = [s for s in slots if isinstance(s, dict)] if isinstance(slots, list) else []
        stamp = history.get("last_history_update")
        if stamp is not None and str(stamp).lstrip("-").isdigit():
            self.last_history_update = int(stamp)


def project_queue_slot(slot: dict[str, Any]) -> dict[str, Any]:
    priority = states.priority_value(slot.get("priority"))
    return {
        "id": str(slot.get("nzo_id") or ""),
        "name": str(slot.get("filename") or ""),
        "status": str(slot.get("status") or ""),
        "label": states.queue_label(slot.get("status")),
        "percent": max(0, min(100, int(num(slot.get("percentage"))))),
        "timeleft": seconds(slot.get("timeleft")),
        "sizeleft": str(slot.get("sizeleft") or ""),
        "priority": priority,
        "priority_label": states.PRIORITY_NAMES.get(priority, str(slot.get("priority") or "")) if priority is not None else str(slot.get("priority") or ""),
        "category": "" if slot.get("cat") in (None, "*") else str(slot.get("cat")),
        "paused": slot.get("status") == "Paused",
    }


def project_history_slot(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(slot.get("nzo_id") or ""),
        "name": str(slot.get("name") or ""),
        "status": str(slot.get("status") or ""),
        "label": states.history_label(slot.get("status")),
        "fail_message": str(slot.get("fail_message") or ""),
        "size": str(slot.get("size") or ""),
        "completed": int(num(slot.get("completed"))) or None,
        "action_line": str(slot.get("action_line") or ""),
    }


def project(state: SabState) -> dict[str, Any]:
    q = state.queue
    slots = [s for s in q.get("slots") or [] if isinstance(s, dict)]
    history = state.history_slots
    post = [project_history_slot(s) for s in history if s.get("loaded") is True or s.get("loaded") == "true"]
    recent = [project_history_slot(s) for s in history if s.get("status") in states.FINAL][:RECENT]
    return {
        "server": {
            "status": str(q.get("status") or ""),
            "paused": bool(q.get("paused")),
            "speed": int(num(q.get("kbpersec")) * KIB),
            "timeleft": seconds(q.get("timeleft")),
            "sizeleft": str(q.get("sizeleft") or ""),
            "mbleft": num(q.get("mbleft")),
            "jobs": int(num(q.get("noofslots_total"))),
            "speedlimit": int(num(q.get("speedlimit"), 100)) or 100,
            "warnings": int(num(q.get("have_warnings"))),
            "pause_left": pause_seconds(q.get("pause_int")),
        },
        "queue": [project_queue_slot(s) for s in slots[:QUEUE_TOP]],
        "post_processing": post,
        "recent": recent,
    }


class TransitionTracker:
    """Toast once per job when it reaches Completed or Failed in history.

    The first call records the jobs already finished, so nothing toasts on start.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.seen: set[str] | None = None

    def changes(self, state: SabState) -> list[dict[str, str]]:
        finished = {
            str(s.get("nzo_id")): s for s in state.history_slots if s.get("status") in states.FINAL and s.get("nzo_id")
        }
        if self.seen is None:
            self.seen = set(finished)
            return []
        toasts = []
        for nzo_id, slot in finished.items():
            if nzo_id in self.seen:
                continue
            self.seen.add(nzo_id)
            name = str(slot.get("name") or "Download")
            if slot.get("status") == "Completed":
                toasts.append({"kind": "completed", "key": f"completed:{nzo_id}", "title": "Download complete", "body": name})
            else:
                reason = str(slot.get("fail_message") or "").strip()
                body = f"{name}. {reason}" if reason else name
                toasts.append({"kind": "failed", "key": f"failed:{nzo_id}", "title": "Download failed", "body": body})
        return toasts
