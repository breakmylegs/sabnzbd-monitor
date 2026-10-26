"""Step-by-step connection test report.

Steps run in order: validate the URL, check the port, call the unauthenticated
version endpoint, call an authenticated endpoint. The report says which step
failed or which auth path worked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import PluginError, classify
from .http import BaseUrl, parse_base_url, port_warning

URL = "url"
PORT = "port"
VERSION = "version"
AUTH = "auth"


@dataclass
class Report:
    ok: bool = False
    steps: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failed_step: str | None = None
    auth_path: str | None = None
    server_version: str | None = None

    def passed(self, step: str, detail: str = "") -> None:
        self.steps.append({"step": step, "ok": True, "detail": detail})

    def failed(self, step: str, err: PluginError | str) -> None:
        if isinstance(err, PluginError):
            self.steps.append({"step": step, "ok": False, "detail": err.message, "kind": err.kind})
        else:
            self.steps.append({"step": step, "ok": False, "detail": err})
        self.failed_step = step
        self.ok = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "steps": self.steps,
            "warnings": self.warnings,
            "failed_step": self.failed_step,
            "auth_path": self.auth_path,
            "server_version": self.server_version,
        }


def check_url(report: Report, raw: str) -> BaseUrl | None:
    try:
        base = parse_base_url(raw)
    except ValueError as err:
        report.failed(URL, str(err))
        return None
    report.passed(URL, str(base))
    warning = port_warning(base)
    if warning:
        report.warnings.append(warning)
        report.passed(PORT, warning)
    else:
        report.passed(PORT)
    return base


def run_step(report: Report, step: str, fn, *args: Any) -> tuple[bool, Any]:
    try:
        value = fn(*args)
    except Exception as exc:  # noqa: BLE001, classified
        report.failed(step, classify(exc))
        return False, None
    return True, value
