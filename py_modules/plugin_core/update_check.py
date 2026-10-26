"""Daily check of the mirror's latest GitHub release.

The mirror repo and asset name come from `build_info.json`, which the build
writes into the plugin folder. Nothing here names an owner.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Callable

from .settings import atomic_write_json, read_json

CHECK_EVERY = 24 * 60 * 60
VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.search(text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def load_build_info(plugin_dir: str) -> dict[str, str]:
    raw = read_json(os.path.join(plugin_dir, "build_info.json"))
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, str)}


def install_url(repo: str, asset: str) -> str:
    return f"https://github.com/{repo}/releases/latest/download/{asset}"


class UpdateChecker:
    def __init__(
        self,
        build_info: dict[str, str],
        current_version: str,
        cache_path: str,
        fetch_json: Callable[[str], Any],
        now: Callable[[], float] = time.time,
    ):
        self.repo = build_info.get("repo", "")
        self.asset = build_info.get("asset", "")
        self.current = current_version
        self.cache_path = cache_path
        self._fetch_json = fetch_json
        self._now = now

    @property
    def configured(self) -> bool:
        return bool(self.repo and self.asset)

    def cached(self) -> dict[str, Any]:
        raw = read_json(self.cache_path)
        return raw if isinstance(raw, dict) else {}

    def due(self) -> bool:
        checked = self.cached().get("checked_at")
        return not isinstance(checked, (int, float)) or self._now() - checked >= CHECK_EVERY

    def check(self, force: bool = False) -> dict[str, Any]:
        """Blocking. Call through asyncio.to_thread. Never raises."""
        if not self.configured:
            return self.result(None)
        cache = self.cached()
        latest = cache.get("latest") if isinstance(cache.get("latest"), str) else None
        if force or self.due():
            try:
                data = self._fetch_json(f"https://api.github.com/repos/{self.repo}/releases/latest")
                tag = data.get("tag_name") if isinstance(data, dict) else None
                if isinstance(tag, str):
                    latest = tag
            except Exception:  # noqa: BLE001, an update check must never break the plugin
                pass
            atomic_write_json(self.cache_path, {"checked_at": self._now(), "latest": latest})
        return self.result(latest)

    def result(self, latest: str | None) -> dict[str, Any]:
        current = parse_version(self.current)
        newest = parse_version(latest or "")
        available = bool(current and newest and newest > current)
        return {
            "current": self.current,
            "latest": ".".join(map(str, newest)) if newest else None,
            "available": available,
            "install_url": install_url(self.repo, self.asset) if self.configured else None,
        }
