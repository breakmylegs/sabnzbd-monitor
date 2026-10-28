"""Small HTTP client on top of urllib.

Every call is blocking. Call it through `asyncio.to_thread` so the shared
Decky event loop never waits on the network.
"""

from __future__ import annotations

import http.cookiejar
import ipaddress
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping

from .errors import BAD_RESPONSE, TLS, PluginError, classify, from_status

DEFAULT_TIMEOUT = 5.0
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DECKY_RESERVED_PORT = 8080

# Sent on every request. Cloudflare in front of Deck Verified answers 403 to
# Python's default "Python-urllib/3.x", so each plugin names itself instead.
# Services call set_user_agent at startup with build_info.json.
USER_AGENT = "decky-plugin"


def set_user_agent(build_info: Mapping[str, str], version: str) -> str:
    global USER_AGENT
    name = build_info.get("plugin") or "decky-plugin"
    where = build_info.get("monorepo")
    USER_AGENT = f"{name}/{version}" + (f" (+https://github.com/{where})" if where else "")
    return USER_AGENT


@dataclass(frozen=True)
class BaseUrl:
    scheme: str
    host: str
    port: int
    prefix: str

    @property
    def is_local(self) -> bool:
        return self.host.lower() in LOCAL_HOSTS

    @property
    def origin(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}:{self.port}"

    def join(self, path: str) -> str:
        return f"{self.origin}{self.prefix}/{path.lstrip('/')}"

    def __str__(self) -> str:
        return f"{self.origin}{self.prefix}"


def parse_base_url(value: str) -> BaseUrl:
    """Parse `http(s)://host[:port][/path-prefix]`. Raises ValueError with a plain reason."""
    text = (value or "").strip()
    if not text:
        raise ValueError("Enter the server address, for example http://192.168.x.x:8090")
    if "://" not in text:
        raise ValueError("Start the address with http:// or https://")
    parts = urllib.parse.urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("Use http:// or https://")
    if parts.username or parts.password:
        raise ValueError("Do not put credentials in the address. Use the fields below")
    if parts.query or parts.fragment:
        raise ValueError("Remove the ? or # part from the address")
    host = parts.hostname or ""
    if not host:
        raise ValueError("The address has no host name")
    if not _valid_host(host):
        raise ValueError("The host name is not valid")
    try:
        port = parts.port
    except ValueError:
        raise ValueError("The port must be a number from 1 to 65535") from None
    if port is None:
        port = 443 if scheme == "https" else 80
    prefix = parts.path.rstrip("/")
    return BaseUrl(scheme, host, port, prefix)


def _valid_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if len(host) > 253:
        return False
    labels = host.rstrip(".").split(".")
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not all(ch.isalnum() or ch == "-" for ch in label):
            return False
    return True


def port_warning(base: BaseUrl) -> str | None:
    if base.is_local and base.port == DECKY_RESERVED_PORT:
        return (
            "Port 8080 on this device is used by Steam and Decky. "
            "Move the server to another port, such as 8090."
        )
    return None


# Decky's bundled Python looks for CA certificates where its build machine kept
# them, which SteamOS does not have, so every HTTPS call fails verification.
# Decky's own downloads use certifi for this reason. Use the system bundle when
# the default paths are missing, then certifi, which Decky ships.
SYSTEM_CA_FILES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ca-certificates/extracted/tls-ca-bundle.pem",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
)


def default_ca_file(candidates: tuple[str, ...] = SYSTEM_CA_FILES) -> str | None:
    """The CA file to load when the default paths have none, or None to use the defaults."""
    paths = ssl.get_default_verify_paths()
    if (paths.cafile and os.path.isfile(paths.cafile)) or (paths.capath and os.path.isdir(paths.capath)):
        return None
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    try:
        import certifi
    except ImportError:
        return None
    return certifi.where()


@dataclass
class TlsOptions:
    verify: bool = True
    ca_file: str = ""

    def context(self) -> ssl.SSLContext:
        if not self.verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        if self.ca_file:
            return ssl.create_default_context(cafile=self.ca_file)
        return ssl.create_default_context(cafile=default_ca_file())

    def describe(self) -> str:
        """Where certificates come from, for TLS error details."""
        if not self.verify:
            return "verification off"
        if self.ca_file:
            return f"CA file {self.ca_file}"
        chosen = default_ca_file()
        if chosen:
            return f"CA file {chosen}"
        paths = ssl.get_default_verify_paths()
        return f"OpenSSL defaults {paths.cafile or '-'} and {paths.capath or '-'}"


@dataclass
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes = b""

    def json(self) -> Any:
        if not self.body:
            raise PluginError(BAD_RESPONSE, "empty reply", self.status)
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise PluginError(BAD_RESPONSE, "reply is not JSON", self.status) from None

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class HttpClient:
    base: BaseUrl
    timeout: float = DEFAULT_TIMEOUT
    tls: TlsOptions = field(default_factory=TlsOptions)
    use_cookies: bool = False
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cookies = http.cookiejar.CookieJar()
        handlers: list[urllib.request.BaseHandler] = [
            # LAN servers must not go through a proxy picked up from the environment.
            urllib.request.ProxyHandler({}),
        ]
        # Loading certificates can fail too. Keep that error for the first request,
        # where it is classified like any other.
        self._tls_error: BaseException | None = None
        if self.base.scheme == "https":
            try:
                handlers.append(urllib.request.HTTPSHandler(context=self.tls.context()))
            except (ssl.SSLError, OSError) as exc:
                self._tls_error = exc
        if self.use_cookies:
            handlers.append(urllib.request.HTTPCookieProcessor(self.cookies))
        self._opener = urllib.request.build_opener(*handlers)

    def clear_cookies(self) -> None:
        self.cookies.clear()

    def request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        form: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        json_body: Any = None,
    ) -> Response:
        """Send one request. Returns any HTTP status as a Response. Raises PluginError
        only when no HTTP reply arrived."""
        url = self.base.join(path)
        if params:
            url = f"{url}?{urllib.parse.urlencode(_clean(params))}"
        data = None
        merged = {"Accept": "application/json", "User-Agent": USER_AGENT, **self.headers, **(headers or {})}
        if form is not None:
            data = urllib.parse.urlencode(_clean(form)).encode("ascii")
            merged["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            merged["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method.upper(), headers=merged)
        try:
            if self._tls_error is not None:
                raise urllib.error.URLError(ssl.SSLError(f"could not load certificates: {self._tls_error}"))
            with self._opener.open(req, timeout=timeout or self.timeout) as res:
                return Response(res.status, dict(res.headers.items()), res.read())
        except urllib.error.HTTPError as err:
            try:
                body = err.read()
            except OSError:
                body = b""
            return Response(err.code, dict(err.headers.items()) if err.headers else {}, body)
        except Exception as exc:  # noqa: BLE001, classified below
            err = classify(exc)
            if err.kind == TLS:
                err.detail = f"{err.detail}. {self.tls.describe()}"
            raise err from None

    def get(self, path: str, **kwargs: Any) -> Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Response:
        return self.request("POST", path, **kwargs)


def _clean(values: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = str(value)
    return out


def fetch_json(url: str, headers: Mapping[str, str] | None = None, timeout: float = 10.0) -> Any:
    """GET a public JSON document such as the GitHub releases API."""
    base = parse_base_url(_origin_of(url))
    path = url[len(_origin_of(url)):]
    client = HttpClient(base, timeout=timeout, headers=dict(headers or {}))
    res = client.get(path)
    if res.status != 200:
        raise from_status(res.status)
    return res.json()


def _origin_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
