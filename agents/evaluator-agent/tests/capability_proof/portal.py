"""Authenticated, structurally varied local portal with a private independent oracle.

The agent receives the origin and objective, never these routes or fixture source.
Only the first-login URL is provided to the host that seeds a dedicated profile.
"""

from __future__ import annotations

import hashlib
import html
import secrets
import threading
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .documents import Invoice, invoices


@dataclass(frozen=True)
class Scenario:
    variant: int
    records: tuple[Invoice, ...]
    account_route: str
    catalog_route: str
    document_prefix: str

    @classmethod
    def create(cls, seed: int) -> Scenario:
        return cls(
            seed % 3,
            invoices(seed),
            "/" + secrets.token_hex(8),
            "/" + secrets.token_hex(8),
            "/" + secrets.token_hex(8) + "/",
        )


class Portal:
    def __init__(
        self, scenario: Scenario, *, partial_first_download: bool = True
    ) -> None:
        self.scenario = scenario
        self._login_code = secrets.token_urlsafe(24)
        self._session = secrets.token_urlsafe(32)
        self._partial = partial_first_download
        self._mutex = threading.Lock()
        self.events: list[dict[str, object]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.respond(self)

            def log_message(self, fmt: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/"

    @property
    def login_url(self) -> str:
        return self.url + "login?code=" + self._login_code

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("Owned fixture did not stop")

    def _event(self, kind: str, **fields: object) -> None:
        with self._mutex:
            self.events.append({"kind": kind, **fields})

    def _send(
        self,
        handler: BaseHTTPRequestHandler,
        body: str | bytes,
        *,
        status: int = 200,
        mime: str = "text/html; charset=utf-8",
        filename: str | None = None,
    ) -> None:
        data = body.encode() if isinstance(body, str) else body
        handler.send_response(status)
        handler.send_header("Content-Type", mime)
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        if filename:
            handler.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        handler.end_headers()
        handler.wfile.write(data)

    def _authenticated(self, handler: BaseHTTPRequestHandler) -> bool:
        cookie = SimpleCookie()
        try:
            cookie.load(handler.headers.get("Cookie", ""))
        except CookieError:
            return False
        value = cookie.get("fixture-session")
        return value is not None and secrets.compare_digest(value.value, self._session)

    def respond(self, handler: BaseHTTPRequestHandler) -> None:
        request = urlsplit(handler.path)
        if request.path == "/login":
            code = parse_qs(request.query).get("code", [""])[0]
            if not secrets.compare_digest(code, self._login_code):
                self._send(handler, "<h1>Sign in required</h1>", status=401)
                return
            handler.send_response(303)
            handler.send_header("Location", "/")
            handler.send_header(
                "Set-Cookie",
                f"fixture-session={self._session}; Path=/; HttpOnly; "
                "SameSite=Lax; Max-Age=86400",
            )
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            self._event("login")
            return
        if not self._authenticated(handler):
            self._event("unauthenticated", path=request.path)
            self._send(
                handler, "<h1>Dedicated account sign-in required</h1>", status=401
            )
            return
        self._event("page", path=request.path)
        scenario = self.scenario
        if request.path.startswith(scenario.document_prefix):
            number = request.path.removeprefix(scenario.document_prefix)
            item = next(
                (item for item in scenario.records if item.number == number), None
            )
            if item is None:
                self._send(handler, "Unknown document", status=404)
                return
            with self._mutex:
                partial, self._partial = self._partial, False
            content = (
                b"%PDF-1.4\n% interrupted transfer\n" if partial else item.document
            )
            self._event(
                "document",
                number=number,
                partial=partial,
                sha256=hashlib.sha256(content).hexdigest(),
            )
            self._send(
                handler, content, mime="application/pdf", filename=number + ".pdf"
            )
            return
        if request.path == "/":
            body = self._home()
        elif request.path == scenario.account_route:
            body = self._account()
        elif request.path == scenario.catalog_route:
            body = self._catalog()
        else:
            self._send(handler, "Not found", status=404)
            return
        self._send(
            handler,
            "<!doctype html><html><head><title>Cedar account</title></head><body>"
            + body
            + "</body></html>",
        )

    def _home(self) -> str:
        route = self.scenario.account_route
        entries = (
            f'<a href="{route}">Workspace settings</a>',
            f"<button onclick=\"location.href='{route}'\">Manage organization</button>",
            f'<form action="{route}"><label>Area <select name="area">'
            "<option>Overview</option><option>Finance</option></select></label>"
            "<button>Open area</button></form>",
        )
        return (
            "<h1>Cedar Services</h1><p>Signed in as billing@example.test</p>"
            + entries[self.scenario.variant]
        )

    def _account(self) -> str:
        route = self.scenario.catalog_route
        entries = (
            f'<nav><a href="{route}">Billing history</a><a href="/help">Help</a></nav>',
            "<details><summary>Payments and subscriptions</summary>"
            f'<a href="{route}">Statements</a></details>',
            f'<h2>Finance</h2><form action="{route}"><label>Documents '
            '<select name="kind"><option>Usage reports</option>'
            "<option>Paid invoices</option></select></label>"
            "<button>View documents</button></form>",
        )
        return "<h1>Account administration</h1>" + entries[self.scenario.variant]

    def _catalog(self) -> str:
        rows = []
        for item in reversed(self.scenario.records):
            link = (
                f'<a href="{self.scenario.document_prefix}{item.number}" download>'
                "Download invoice PDF</a>"
            )
            fields = (
                f"Invoice {item.number}; period {item.period}; EUR {item.total}; paid"
            )
            escaped = html.escape(fields)
            if self.scenario.variant == 0:
                rows.append(f"<tr><td>{escaped}</td><td>{link}</td></tr>")
            elif self.scenario.variant == 1:
                rows.append(f"<article><h2>{escaped}</h2>{link}</article>")
            else:
                rows.append(f"<details><summary>{escaped}</summary>{link}</details>")
        content = "".join(rows)
        if self.scenario.variant == 0:
            content = (
                "<table><caption>Paid subscriptions</caption><tbody>"
                + content
                + "</tbody></table>"
            )
        return (
            "<h1>Invoice documents</h1>"
            "<p>Official originals for your accounting records.</p>" + content
        )

    def expected_hashes(self) -> dict[str, str]:
        return {
            item.number: hashlib.sha256(item.document).hexdigest()
            for item in self.scenario.records
        }
