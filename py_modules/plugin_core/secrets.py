"""Secret storage and import from file.

Secret values stay in the backend. The frontend only sees whether a secret is set
and a short masked suffix.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable, Mapping

from .settings import atomic_write_json, read_json

MAX_SECRET_LENGTH = 4096
MAX_IMPORT_BYTES = 64 * 1024
SUFFIX_MIN_LENGTH = 12


def mask(value: str) -> str:
    """Show the last four characters only when the secret is long enough that
    four characters give nothing useful away."""
    if not value:
        return ""
    if len(value) < SUFFIX_MIN_LENGTH:
        return "set"
    return f"****{value[-4:]}"


class SecretStore:
    def __init__(self, path: str, names: Iterable[str]):
        self.path = path
        self.names = tuple(names)
        self._values: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        raw = read_json(self.path)
        values: dict[str, str] = {}
        if isinstance(raw, dict):
            for name in self.names:
                value = raw.get(name)
                if isinstance(value, str) and value:
                    values[name] = value
        self._values = values

    def save(self) -> None:
        atomic_write_json(self.path, self._values)

    def get(self, name: str) -> str:
        return self._values.get(name, "")

    def has(self, name: str) -> bool:
        return bool(self._values.get(name))

    def set(self, name: str, value: str) -> None:
        if name not in self.names:
            raise ValueError(f"unknown secret: {name}")
        if not isinstance(value, str):
            raise ValueError("secret must be text")
        value = value.strip()
        if len(value) > MAX_SECRET_LENGTH:
            raise ValueError("secret is too long")
        if value:
            self._values[name] = value
        else:
            self._values.pop(name, None)
        self.save()

    def clear(self, name: str | None = None) -> None:
        if name is None:
            self._values = {}
        else:
            self._values.pop(name, None)
        self.save()

    def public_view(self) -> dict[str, dict[str, Any]]:
        return {name: {"set": self.has(name), "masked": mask(self.get(name))} for name in self.names}

    def delete_file(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


def import_path(user_home: str, plugin_id: str) -> str:
    return os.path.join(user_home, "Documents", "decky-import", f"{plugin_id}.json")


def read_import_file(path: str, setting_keys: Iterable[str], secret_keys: Iterable[str]) -> tuple[dict[str, Any], dict[str, str]]:
    """Read and validate an import file. Returns (settings, secrets).

    Raises ValueError with a plain reason. The reason never contains file content.
    """
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        raise ValueError(f"No import file found. Create {path} and try again") from None
    if size > MAX_IMPORT_BYTES:
        raise ValueError("The import file is too large")
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, UnicodeDecodeError, ValueError):
        raise ValueError("The import file is not valid JSON") from None
    if not isinstance(raw, dict):
        raise ValueError("The import file must hold one JSON object")
    allowed_settings = set(setting_keys)
    allowed_secrets = set(secret_keys)
    unknown = sorted(k for k in raw if k not in allowed_settings and k not in allowed_secrets)
    if unknown:
        raise ValueError("Unknown keys in the import file: " + ", ".join(unknown))
    settings: dict[str, Any] = {}
    secrets: dict[str, str] = {}
    for key, value in raw.items():
        if key in allowed_secrets:
            if not isinstance(value, str):
                raise ValueError(f"{key} must be text")
            secrets[key] = value
        else:
            settings[key] = value
    if not settings and not secrets:
        raise ValueError("The import file is empty")
    return settings, secrets


def apply_import(store: SecretStore, secrets: Mapping[str, str]) -> None:
    for key, value in secrets.items():
        store.set(key, value)
