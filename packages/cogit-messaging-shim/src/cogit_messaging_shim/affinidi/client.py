"""Native Affinidi Gateway DID Auth client, with no local authentication substitute.

Protocol: agent-gateway v1.0.10 src/didauth/handlers.rs. Sessions are never
sent outside the configured surface, persisted, or included in error messages.
"""

from __future__ import annotations

import json as json_module
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..keys import AgentKey
from .jws import sign_jws


class DidAuthError(RuntimeError):
    """Authentication or gateway transport failure with a secret-free message."""


@dataclass(frozen=True)
class DidAuthConfig:
    surface_url: str
    audience: str
    session_header: str
    session_prefix: str = ""
    timeout_seconds: float = 10
    proof_ttl_seconds: int = 60

    def __post_init__(self):
        url = urlsplit(self.surface_url)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if not url.hostname or url.scheme not in {"https", "http"} or (url.scheme == "http" and not local):
            raise ValueError("Gateway URL requires HTTPS, except for a loopback development gateway")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Gateway URL cannot contain credentials, a query or a fragment")
        if not self.audience or not isinstance(self.audience, str):
            raise ValueError("A gateway audience is required")
        if not isinstance(self.session_header, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", self.session_header):
            raise ValueError("A valid configured session header is required")
        if self.session_prefix != "":
            raise ValueError("Native DID Auth requires the raw session token without a header prefix")
        if not 0 < self.timeout_seconds <= 60 or type(self.proof_ttl_seconds) is not int or not 1 <= self.proof_ttl_seconds <= 120:
            raise ValueError("Invalid gateway timeout or proof lifetime")


@dataclass(frozen=True)
class DidSession:
    did: str
    expires_at: str
    expires_in: int
    session_id: str = field(repr=False)
    session_header: str = field(repr=False)
    session_prefix: str = field(default="", repr=False)
    deadline: float = field(default=0, repr=False)

    def headers(self) -> dict[str, str]:
        return {self.session_header: self.session_prefix + self.session_id}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DidAuthError("Gateway redirects are refused")


class DidAuthClient:
    def __init__(self, key: AgentKey, config: DidAuthConfig, *, transport=None, now=time.time):
        self.key, self.config, self._transport, self._now = key, config, transport, now
        self._session: DidSession | None = None

    def _url(self, relative_path: str) -> str:
        parsed = urlsplit(relative_path)
        path = unquote(parsed.path)
        if parsed.scheme or parsed.netloc or parsed.fragment or "\\" in path or any(p in {".", ".."} for p in path.split("/")):
            raise DidAuthError("Gateway requests must stay on the configured surface")
        suffix = relative_path.lstrip("/")
        return self.config.surface_url.rstrip("/") + ("/" + suffix if suffix else "")

    def _call(self, method: str, path: str, payload: dict | None, headers: dict) -> dict:
        try:
            url = self._url(path)
            if self._transport is not None:
                result = self._transport(method, url, payload, headers)
            else:
                data = None if payload is None else json_module.dumps(payload, separators=(",", ":")).encode()
                request = Request(url, data=data, headers={"Accept": "application/json", "Content-Type": "application/json", **headers}, method=method)
                with build_opener(_NoRedirect).open(request, timeout=self.config.timeout_seconds) as response:
                    result = json_module.loads(response.read(1024 * 1024 + 1))
            if not isinstance(result, dict):
                raise DidAuthError("Gateway response must be a JSON object")
            return result
        except HTTPError as error:
            raise DidAuthError(f"Gateway request refused (HTTP {error.code})") from None
        except DidAuthError:
            raise
        except (URLError, TimeoutError, OSError, ValueError, TypeError):
            raise DidAuthError("Gateway request failed") from None

    def authenticate(self) -> DidSession:
        self._session = None
        challenge = self._call("POST", "authenticate/challenge", {"did": self.key.did}, {})
        value, ttl = challenge.get("challenge"), challenge.get("expires_in")
        if not isinstance(value, str) or not value or len(value) > 8192 or type(ttl) is not int or ttl <= 0:
            raise DidAuthError("Invalid gateway challenge response")
        issued = int(self._now())
        proof = sign_jws(self.key, {"challenge": value, "iat": issued,
                                   "exp": issued + min(ttl, self.config.proof_ttl_seconds), "aud": self.config.audience})
        response = self._call("POST", "authenticate", {"did": self.key.did, "challenge_response": proof}, {})
        token, expires_at, expires_in = (response.get(k) for k in ("session_id", "expires_at", "expires_in"))
        if not isinstance(token, str) or not token or "\r" in token or "\n" in token or len(token) > 8192:
            raise DidAuthError("Invalid gateway session response")
        if type(expires_in) is not int or expires_in <= 0 or not isinstance(expires_at, str):
            raise DidAuthError("Invalid gateway session expiry")
        try:
            stamp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("Timezone is required")
            deadline = min(stamp.timestamp(), self._now() + expires_in)
        except ValueError:
            raise DidAuthError("Invalid gateway session expiry") from None
        if deadline <= self._now():
            raise DidAuthError("Gateway returned an expired session")
        self._session = DidSession(self.key.did, expires_at, expires_in, token,
                                   self.config.session_header, self.config.session_prefix, deadline)
        return self._session

    def request(self, method: str, relative_path: str = "", *, json: dict | None = None) -> dict:
        """Call one surface with its session; never silently replay failed mutations."""
        self._url(relative_path)  # reject unsafe target before authenticating
        session = self._session
        if session is None or session.deadline <= self._now() + 5:
            session = self.authenticate()
        try:
            return self._call(method, relative_path, json, session.headers())
        except DidAuthError:
            self._session = None
            raise
