"""Boris MCP protocol unit tests using a transport double, not vendor claims."""

import io
import json

import pytest

from cogit_messaging_shim.affinidi.boris import (
    BorisAgentIdentity, BorisMCPClient, BorisMCPError, MCPHTTPResponse, _read_http_body,
)

ENDPOINT = "https://gateway.example/agents/test"


class MCPTransport:
    def __init__(self, *, sse=False):
        self.calls, self.sse = [], sse

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, body, headers))
        if body["method"] == "notifications/initialized":
            return MCPHTTPResponse(202, {}, "")
        if body["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {}, "serverInfo": {"name": "test", "version": "1"}}
        elif body["method"] == "tools/list":
            result = {"tools": [{"name": "get_quote", "inputSchema": {"type": "object"}}]}
        else:
            result = {"content": [{"type": "text", "text": "quote-result"}], "isError": False}
        encoded = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result})
        if self.sse:
            encoded = ": keepalive\n\nevent: message\ndata: " + encoded + "\n\n"
        return MCPHTTPResponse(200, {"Content-Type": "text/event-stream" if self.sse else "application/json",
                                     "Mcp-Session-Id": "secret-mcp-session"}, encoded)


@pytest.mark.parametrize("sse", [False, True])
@pytest.mark.parametrize("role", ["buyer-agent", "seller-agent", "cogit-finance"])
def test_each_role_attaches_identity_to_every_mcp_request(role, sse):
    transport = MCPTransport(sse=sse)
    client = BorisMCPClient(ENDPOINT, BorisAgentIdentity(role), transport=transport)
    assert client.list_tools()[0]["name"] == "get_quote"
    assert client.call_tool("get_quote", {"sku": "course"})["isError"] is False
    assert [call[2]["method"] for call in transport.calls] == [
        "initialize", "notifications/initialized", "tools/list", "tools/call",
    ]
    for _, url, body, _ in transport.calls:
        assert url == ENDPOINT
        assert body["params"]["_meta"]["agentIdentity"]["applicationInfo"]["name"] == role
    assert "Mcp-Session-Id" not in transport.calls[0][3]
    assert transport.calls[1][3]["Mcp-Session-Id"] == "secret-mcp-session"
    assert transport.calls[2][3]["MCP-Protocol-Version"] == "2025-03-26"
    assert "secret-mcp-session" not in repr(client)


def test_call_cannot_override_the_configured_identity_or_mutate_inputs():
    transport = MCPTransport()
    client = BorisMCPClient(ENDPOINT, BorisAgentIdentity("buyer-agent"), transport=transport)
    params = {"_meta": {"trace": "keep", "agentIdentity": {"applicationInfo": {"name": "impostor"}}}}
    client.request("ping", params)
    sent = transport.calls[-1][2]["params"]["_meta"]
    assert sent["trace"] == "keep"
    assert sent["agentIdentity"]["applicationInfo"]["name"] == "buyer-agent"
    assert params["_meta"]["agentIdentity"]["applicationInfo"]["name"] == "impostor"


def test_initialization_is_sent_only_once_and_optional_auth_is_explicit():
    transport = MCPTransport()
    client = BorisMCPClient(ENDPOINT, BorisAgentIdentity("seller-agent"),
                           headers={"Authorization": "Bearer supplied-by-user"}, transport=transport)
    client.initialize()
    client.initialize()
    assert len(transport.calls) == 2
    assert all(call[3]["Authorization"] == "Bearer supplied-by-user" for call in transport.calls)


@pytest.mark.parametrize("body", [
    '{"jsonrpc":"2.0","id":99,"result":{}}',
    '{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"sensitive-token"}}',
    '{"jsonrpc":"2.0","id":1,"result":[]}', "invalid-json", b"\xffsecret",
])
def test_protocol_errors_are_refused_without_exposing_error_body(body):
    client = BorisMCPClient(ENDPOINT, BorisAgentIdentity("buyer-agent"),
                           transport=lambda *args: MCPHTTPResponse(200, {}, body))
    with pytest.raises(BorisMCPError) as error:
        client.initialize()
    assert "sensitive-token" not in str(error.value)
    assert "secret" not in str(error.value)


def test_post_sse_stops_reading_at_response_without_waiting_for_eof():
    class OpenStream:
        headers = {"Content-Type": "text/event-stream"}
        def __init__(self):
            self.lines = iter([b": heartbeat\n", b"\n", b"event: message\n",
                               b'data: {"jsonrpc":"2.0","id":7,"result":{}}\n', b"\n"])
        def readline(self, limit):
            try:
                return next(self.lines)
            except StopIteration:
                raise AssertionError("must not wait for the open stream's EOF")
    body = _read_http_body(OpenStream(), 7)
    assert b'"id":7' in body


@pytest.mark.parametrize("endpoint", ["http://remote.example/mcp", "https://u:p@example.com/mcp",
                                      "https://example.com/mcp?token=secret", "https://example.com/mcp#x"])
def test_insecure_or_credential_bearing_endpoint_is_rejected(endpoint):
    with pytest.raises(ValueError):
        BorisMCPClient(endpoint, BorisAgentIdentity("buyer-agent"))


def test_caller_cannot_replace_mcp_session_or_inject_headers():
    for headers in ({"Mcp-Session-Id": "other"}, {"X-Key": "secret\r\nHost: evil"}):
        with pytest.raises(ValueError):
            BorisMCPClient(ENDPOINT, BorisAgentIdentity("buyer-agent"), headers=headers)
