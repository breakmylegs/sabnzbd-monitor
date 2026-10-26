"""Failure classes shared by every plugin.

Every failure the backend reports is one of the kinds below. The UI shows one
plain-language line per kind, so the message never depends on the exception text.
"""

from __future__ import annotations

import errno
import socket
import ssl
import urllib.error

OFFLINE = "offline"
DNS = "dns"
REFUSED = "refused"
TIMEOUT = "timeout"
TLS = "tls"
AUTH = "auth"
FORBIDDEN = "forbidden"
HTTP_ERROR = "http_error"
BAD_RESPONSE = "bad_response"

KINDS = (OFFLINE, DNS, REFUSED, TIMEOUT, TLS, AUTH, FORBIDDEN, HTTP_ERROR, BAD_RESPONSE)

# Kinds that count towards the offline state. Auth and server errors do not,
# because the server answered.
UNREACHABLE = frozenset({OFFLINE, DNS, REFUSED, TIMEOUT})

MESSAGES = {
    OFFLINE: "No network. Check Wi-Fi and try again.",
    DNS: "Host name not found. Check the address or use the IP address.",
    REFUSED: "Connection refused. Check the port and that the server is running.",
    TIMEOUT: "The server did not answer in time. Check the address and network.",
    TLS: "Secure connection failed. Check the certificate or switch to HTTP.",
    AUTH: "Sign-in failed. Check the API key or password.",
    FORBIDDEN: "The server refused access. Check the credentials or IP whitelist.",
    HTTP_ERROR: "The server returned an error. Check the base URL and server logs.",
    BAD_RESPONSE: "Unexpected reply. Check the base URL points at the right server.",
}


class PluginError(Exception):
    """A classified failure. `detail` must never contain a secret."""

    def __init__(self, kind: str, detail: str = "", status: int | None = None, hint: str | None = None):
        """`hint` replaces the standard message when a plugin knows exactly what
        went wrong and what to do. It is shown to the user, so no secrets."""
        if kind not in KINDS:
            raise ValueError(f"unknown error kind: {kind}")
        super().__init__(detail or kind)
        self.kind = kind
        self.detail = detail
        self.status = status
        self.hint = hint

    @property
    def message(self) -> str:
        return self.hint or MESSAGES[self.kind]

    def to_dict(self) -> dict:
        return {"kind": self.kind, "message": self.message, "status": self.status}


def _reason_errno(reason: object) -> int | None:
    return getattr(reason, "errno", None)


def classify(exc: BaseException) -> PluginError:
    """Map any exception raised by a request to a PluginError."""
    if isinstance(exc, PluginError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        return from_status(exc.code)
    reason: object = exc
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
    if isinstance(reason, (ssl.SSLError, ssl.CertificateError)):
        return PluginError(TLS, type(reason).__name__)
    if isinstance(reason, socket.gaierror):
        return PluginError(DNS, "name resolution failed")
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return PluginError(TIMEOUT, "timed out")
    if isinstance(reason, ConnectionRefusedError):
        return PluginError(REFUSED, "connection refused")
    code = _reason_errno(reason)
    if code in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN):
        return PluginError(OFFLINE, "network unreachable")
    if code == errno.ECONNREFUSED:
        return PluginError(REFUSED, "connection refused")
    if isinstance(reason, (ConnectionResetError, ConnectionAbortedError)):
        return PluginError(OFFLINE, "connection reset")
    if isinstance(reason, str) and "timed out" in reason:
        return PluginError(TIMEOUT, "timed out")
    if isinstance(reason, OSError):
        return PluginError(OFFLINE, type(reason).__name__)
    if isinstance(exc, ValueError):
        return PluginError(BAD_RESPONSE, "could not parse the reply")
    return PluginError(BAD_RESPONSE, type(exc).__name__)


def from_status(status: int) -> PluginError:
    if status == 401:
        return PluginError(AUTH, "HTTP 401", status)
    if status == 403:
        return PluginError(FORBIDDEN, "HTTP 403", status)
    return PluginError(HTTP_ERROR, f"HTTP {status}", status)
