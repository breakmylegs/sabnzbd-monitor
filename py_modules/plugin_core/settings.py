"""JSON file storage with atomic writes and owner-only permissions."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from typing import Any, Mapping


def atomic_write_json(path: str, data: Any) -> None:
    """Write to a temp file in the same folder, replace the target, then chmod 600."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None


class JsonStore:
    """A dict persisted to one JSON file. Unknown keys from disk are dropped and
    missing keys take their default, so old files survive schema changes."""

    def __init__(self, path: str, defaults: Mapping[str, Any]):
        self.path = path
        self.defaults = copy.deepcopy(dict(defaults))
        self.data: dict[str, Any] = copy.deepcopy(self.defaults)
        self.load()

    def load(self) -> None:
        raw = read_json(self.path)
        data = copy.deepcopy(self.defaults)
        if isinstance(raw, dict):
            for key in data:
                if key in raw and _same_shape(data[key], raw[key]):
                    data[key] = raw[key]
        self.data = data

    def save(self) -> None:
        atomic_write_json(self.path, self.data)

    def get(self, key: str) -> Any:
        return self.data[key]

    def update(self, values: Mapping[str, Any]) -> list[str]:
        """Apply known keys with matching types. Returns the keys that changed."""
        changed = []
        for key, value in values.items():
            if key not in self.defaults:
                continue
            if not _same_shape(self.defaults[key], value):
                raise ValueError(f"invalid value for {key}")
            if self.data.get(key) != value:
                self.data[key] = value
                changed.append(key)
        if changed:
            self.save()
        return changed

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)

    def delete_file(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


def _same_shape(default: Any, value: Any) -> bool:
    if default is None:
        return True
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type(default))
