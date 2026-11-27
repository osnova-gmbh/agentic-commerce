"""Boris MCP payload identity, distinct from native DID proof of possession.

The enabled AgentIdentityAccess surface derives an identity from values under
params._meta.agentIdentity. Supplying those values is not cryptographic caller
authentication; a gateway session also does not establish DID authentication.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class BorisMCPError(RuntimeError):
    """Protocol error whose message omits response bodies and credentials."""


@dataclass(frozen=True)
class BorisAgentIdentity:
    application_name: str
    application_version: str = "0.1.0"

    def __post_init__(self):
        if not self.application_name or not self.application_version:
            raise ValueError("Application name and version are required")

    def payload(self) -> dict:
        return {"applicationInfo": {"name": self.application_name, "version": self.application_version}}


@dataclass(frozen=True)
class MCPHTTPResponse:
    status: int
    headers: Mapping[str, str]
    body: str | bytes


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BorisMCPError("Gateway redirects are refused")


def _decode_response(response: MCPHTTPResponse, request_id: int | None) -> dict:
    if not 200 <= response.status < 300:
        raise BorisMCPError(f"Gateway request refused (HTTP {response.status})")
    if request_id is None:
        return {}
    if len(response.body) > 4 * 1024 * 1024:
        raise BorisMCPError("Gateway response exceeded the size limit")
    content_type = next((v for k, v in response.headers.items() if k.lower() == "content-type"), "")
    try:
        raw = response.body.decode("utf-8") if isinstance(response.body, bytes) else response.body
        if "text/event-stream" in content_type:
            # SSE data may span several lines; comments/heartbeats carry no data.
            messages, parts = [], []
            for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n") + [""]:
                if line.startswith("data:"):
                    parts.append(line[5:].lstrip(" "))
                elif line == "" and parts:
                    messages.append(json.loads("\n".join(parts)))
                    parts = []
        else:
            messages = [json.loads(raw)]
    except (TypeError, ValueError):
        raise BorisMCPError("Invalid gateway JSON or event-stream response") from None
    matches = [item for item in messages if isinstance(item, dict)
               and type(item.get("id")) is int and item["id"] == request_id]
    if len(matches) != 1 or matches[0].get("jsonrpc") != "2.0":
        raise BorisMCPError("Gateway returned no unique matching JSON-RPC response")
    message = matches[0]
    if "error" in message:
        error = message["error"]
        code = error.get("code") if isinstance(error, dict) else None
        suffix = f" (JSON-RPC {code})" if type(code) is int else ""
        raise BorisMCPError("Gateway rejected the MCP request" + suffix)
    if not isinstance(message.get("result"), dict):
        raise BorisMCPError("Gateway returned an invalid MCP result")
    return message["result"]


def _read_http_body(response, request_id: int | None) -> bytes:
    if request_id is None:
        return b""
    if "text/event-stream" not in response.headers.get("Content-Type", ""):
        return response.read(4 * 1024 * 1024 + 1)
    # POST event streams can remain open: stop at the matching response, not EOF.
    body, event_data = bytearray(), []
    while len(body) <= 4 * 1024 * 1024:
        line = response.readline(4 * 1024 * 1024 + 1 - len(body))
        if not line:
            break
        body.extend(line)
        stripped = line.rstrip(b"\r\n")
        if stripped.startswith(b"data:"):
            event_data.append(stripped[5:].lstrip(b" "))
        elif not stripped and event_data:
            try:
                event = json.loads(b"\n".join(event_data))
            except (ValueError, UnicodeDecodeError):
                raise BorisMCPError("Invalid gateway event-stream response") from None
            if isinstance(event, dict) and type(event.get("id")) is int and event["id"] == request_id:
                return bytes(body)
            event_data = []
    return bytes(body)


class BorisMCPClient:
    """One MCP session, carrying the selected role's payload identity on every call."""

    def __init__(self, endpoint: str, identity: BorisAgentIdentity, *, headers=None,
                 transport=None, timeout_seconds: float = 15):
        url = urlsplit(endpoint)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if not url.hostname or url.scheme not in {"https", "http"} or (url.scheme == "http" and not local):
            raise ValueError("Boris endpoint requires HTTPS, except on loopback")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Boris endpoint cannot contain credentials, query or fragment")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("Invalid Boris request timeout")
        self.endpoint, self.identity = endpoint, identity
        self._headers = dict(headers or {})
        for key, value in self._headers.items():
            if not isinstance(key, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key) or not isinstance(value, str) or "\r" in value or "\n" in value:
                raise ValueError("Invalid configured gateway header")
        reserved = {"accept", "content-type", "mcp-session-id", "mcp-protocol-version"}
        if any(key.lower() in reserved for key in self._headers):
            raise ValueError("MCP transport headers are managed by the client")
        self._transport, self.timeout_seconds = transport, timeout_seconds
        self._next_id, self._session_id, self._protocol_version = 1, None, None
        self._initialized = False

    def _http(self, envelope: dict, headers: dict) -> MCPHTTPResponse:
        try:
            if self._transport is not None:
                return self._transport("POST", self.endpoint, envelope, headers)
            request = Request(self.endpoint, data=json.dumps(envelope, separators=(",", ":")).encode(),
                              headers=headers, method="POST")
            with build_opener(_NoRedirect).open(request, timeout=self.timeout_seconds) as response:
                return MCPHTTPResponse(response.status, dict(response.headers), _read_http_body(response, envelope.get("id")))
        except HTTPError as error:
            raise BorisMCPError(f"Gateway request refused (HTTP {error.code})") from None
        except BorisMCPError:
            raise
        except (URLError, TimeoutError, OSError, ValueError, TypeError):
            raise BorisMCPError("Boris gateway request failed") from None

    def _send(self, method: str, params: Mapping | None = None, *, notification: bool = False) -> dict:
        payload = copy.deepcopy(dict(params or {}))
        metadata = payload.setdefault("_meta", {})
        if not isinstance(metadata, dict):
            raise ValueError("MCP params._meta must be an object")
        metadata["agentIdentity"] = self.identity.payload()
        envelope = {"jsonrpc": "2.0", "method": method, "params": payload}
        request_id = None
        if not notification:
            request_id = self._next_id
            self._next_id += 1
            envelope["id"] = request_id
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", **self._headers}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self._protocol_version:
            headers["MCP-Protocol-Version"] = self._protocol_version
        response = self._http(envelope, headers)
        result = _decode_response(response, request_id)
        session = next((v for k, v in response.headers.items() if k.lower() == "mcp-session-id"), None)
        if session is not None:
            if not isinstance(session, str) or not session or "\r" in session or "\n" in session:
                raise BorisMCPError("Gateway returned an invalid MCP session header")
            if self._session_id is not None and session != self._session_id:
                raise BorisMCPError("Gateway changed the active MCP session unexpectedly")
            self._session_id = session
        return result

    def initialize(self) -> dict:
        if self._initialized:
            return self._initialize_result
        result = self._send("initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": self.identity.application_name, "version": self.identity.application_version},
        })
        version = result.get("protocolVersion")
        if not isinstance(version, str) or not version:
            raise BorisMCPError("Gateway initialization omitted its protocol version")
        self._protocol_version = version
        self._send("notifications/initialized", notification=True)
        self._initialize_result, self._initialized = result, True
        return result

    def request(self, method: str, params: Mapping | None = None) -> dict:
        self.initialize()
        return self._send(method, params)

    def list_tools(self) -> list[dict]:
        tools, cursor, seen = [], None, set()
        for _ in range(100):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            page = result.get("tools")
            if not isinstance(page, list) or not all(isinstance(item, dict) and isinstance(item.get("name"), str) for item in page):
                raise BorisMCPError("Gateway returned an invalid tools list")
            tools.extend(page)
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
            if not isinstance(cursor, str) or cursor in seen:
                raise BorisMCPError("Gateway returned a repeated tools cursor")
            seen.add(cursor)
        raise BorisMCPError("Gateway tools pagination exceeded its limit")

    def call_tool(self, name: str, arguments: Mapping | None = None) -> dict:
        if not isinstance(name, str) or not name or (arguments is not None and not isinstance(arguments, Mapping)):
            raise ValueError("A tool name and object arguments are required")
        return self.request("tools/call", {"name": name, "arguments": dict(arguments or {})})
