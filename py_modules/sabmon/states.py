"""SABnzbd status labels and value coercion.

Status strings come from sabnzbd/constants.py class Status. Queue and history
reuse some strings with different meanings, so each has its own table.
"""

from __future__ import annotations

import re
from typing import Any

QUEUE_LABELS = {
    "Downloading": "Downloading",
    "Queued": "Queued",
    "Paused": "Paused",
    "Propagating": "Waiting for propagation",
    "Fetching": "Fetching extra par2",
    "Checking": "Pre-checking",
    "Grabbing": "Fetching NZB",
    "Idle": "Idle",
}

HISTORY_LABELS = {
    "Queued": "Waiting for post-processing",
    "QuickCheck": "Verifying",
    "Verifying": "Verifying",
    "Repairing": "Repairing",
    "Extracting": "Extracting",
    "Moving": "Moving",
    "Running": "Running script",
    "Fetching": "Fetching extra par2",
    "Completed": "Completed",
    "Failed": "Failed",
    "Deleted": "Deleted",
}

FINAL = frozenset({"Completed", "Failed"})

PRIORITY_NAMES = {-1: "Low", 0: "Normal", 1: "High", 2: "Force"}
PRIORITY_VALUES = {name.lower(): value for value, name in PRIORITY_NAMES.items()}


def queue_label(status: Any) -> str:
    return QUEUE_LABELS.get(status, str(status or "Unknown"))


def history_label(status: Any) -> str:
    return HISTORY_LABELS.get(status, str(status or "Unknown"))


def priority_value(raw: Any) -> int | None:
    """SABnzbd sends priority as a name ("Normal") or a number, sometimes as text."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = int(raw)
        return value if value in PRIORITY_NAMES else None
    text = str(raw or "").strip()
    if text.lstrip("-").isdigit():
        return priority_value(int(text))
    return PRIORITY_VALUES.get(text.lower())


def num(raw: Any, default: float = 0.0) -> float:
    """Numbers often arrive as strings, for example "5324.80" or "42"."""
    if isinstance(raw, bool):
        return default
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def truthy(raw: Any) -> bool:
    """Booleans sometimes arrive as text or numbers, for example "True" or 1."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    return str(raw or "").strip().lower() in ("true", "1", "yes")


TIME_RE = re.compile(r"^(?:(\d+):)?(\d+):(\d{1,2}):(\d{1,2})$")


def seconds(timeleft: Any) -> int | None:
    """Parse SABnzbd's "H:MM:SS" or "D:HH:MM:SS". 0:00:00 means unknown or done."""
    match = TIME_RE.match(str(timeleft or "").strip())
    if not match:
        return None
    days, hours, minutes, secs = (int(g) if g else 0 for g in match.groups())
    total = ((days * 24 + hours) * 60 + minutes) * 60 + secs
    return total or None


PAUSE_RE = re.compile(r"^(-?)(\d+):(\d{1,2})$")


def pause_seconds(pause_int: Any) -> int | None:
    """Parse Scheduler.pause_int(): "0" when no timed pause, else "M:SS". A
    negative value means the pause is overdue, so treat it as ending now."""
    match = PAUSE_RE.match(str(pause_int or "").strip())
    if not match:
        return None
    sign, minutes, secs = match.groups()
    total = int(minutes) * 60 + int(secs)
    if sign or total == 0:
        return None
    return total
