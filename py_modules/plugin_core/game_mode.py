"""Remember what a plugin changed on the server when a game started.

The plugin undoes only its own change, and only while the server still shows
the value the plugin set. If the user changed it in the meantime, the record is
dropped and nothing is touched. The record lives in the runtime folder, so a
Decky restart in the middle of a game still restores the server afterwards.
"""

from __future__ import annotations

import os
from typing import Any

from .settings import atomic_write_json, read_json


class GameModeMemory:
    def __init__(self, runtime_dir: str):
        self.path = os.path.join(runtime_dir, "game_mode.json")

    def get(self) -> dict[str, Any] | None:
        data = read_json(self.path)
        return data if isinstance(data, dict) and data else None

    def set(self, record: dict[str, Any]) -> None:
        atomic_write_json(self.path, record)

    def clear(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
