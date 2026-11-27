"""Protocol/crypto unit tests; these do not claim a real Affinidi gateway run."""

import base64
import json
from datetime import datetime, timezone
from urllib.error import HTTPError

import pytest

from cogit_messaging_shim import AgentKey
from cogit_messaging_shim.affinidi import (
    DidAuthClient, DidAuthConfig, DidAuthError, IdentityError,
    sign_jws, sign_quote, verification_method, verify_jws, verify_quote,
)

NOW = 1_800_000_000


def claims(token):
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def quote(key=None, **kwargs):
    return sign_quote(key or AgentKey.generate(), sku="course", quantity=2,
                      amount_minor=180000, currency="EUR", nonce="request-7", now=NOW, **kwargs)


def test_quote_pins_every_purchase_field():
    key = AgentKey.generate()
    payload = verify_quote(quote(key), key.did, sku="course", quantity=2,
                           amount_minor=180000, currency="EUR", nonce="request-7", now=NOW + 2)
    assert payload["seller_did"] == key.did
    assert payload["exp"] == NOW + 300
    for changes in ({"sku": "other"}, {"quantity": 1}, {"amount_minor": 3},
                    {"currency": "USD"}, {"nonce": "replayed"}):
        expected = dict(sku="course", quantity=2, amount_minor=180000, currency="EUR", nonce="request-7")
        expected.update(changes)
        with pytest.raises(IdentityError):
            verify_quote(quote(key), key.did, now=NOW, **expected)


def test_quote_refuses_wrong_signer_tampering_and_expiry():
    key = AgentKey.generate()
    token = quote(key)
    for bad, expected, current in (
        (token, AgentKey.generate().did, NOW),
        (token, key.did, NOW + 300),
        (token, key.did, NOW - 60),
        (token[:-10] + "AAAAAAAAAA", key.did, NOW),
    ):
        with pytest.raises(IdentityError):
            verify_quote(bad, expected, sku="course", quantity=2, nonce="request-7", now=current)


@pytest.mark.parametrize("field,value", [("quantity", True), ("quantity", 0),
                                         ("amount_minor", 1.5), ("amount_minor", -1),
                                         ("currency", "eur"), ("nonce", "")])
def test_quote_refuses_invalid_money_and_request_inputs(field, value):
    values = dict(sku="course", quantity=2, amount_minor=180000, currency="EUR", nonce="request-7")
    values[field] = value
    with pytest.raises(IdentityError):
        sign_quote(AgentKey.generate(), now=NOW, **values)


def test_jws_rejects_unsafe_header_extensions_even_when_signed():
    key = AgentKey.generate()
    header = {"alg": "EdDSA", "kid": verification_method(key.did), "crit": ["foo"]}
    payload = {"iat": NOW, "exp": NOW + 60}
    enc = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    message = enc(header) + "." + enc(payload)
    token = message + "." + base64.urlsafe_b64encode(key.sign(message.encode())).decode().rstrip("=")
    with pytest.raises(IdentityError, match="header extension"):
        verify_jws(token, key.did, now=NOW)


class GatewayTransport:
    """An explicit HTTP protocol test double, not a gateway implementation."""

    def __init__(self, key, now):
        self.key, self.now, self.calls, self.auth_count = key, now, [], 0

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, body, headers))
        if url.endswith("/authenticate/challenge"):
            assert body == {"did": self.key.did}
            assert headers == {}
            return {"challenge": "fresh-challenge", "expires_in": 90}
        if url.endswith("/authenticate"):
            assert headers == {}
            verify_jws(body["challenge_response"], self.key.did, now=self.now[0],
                       expected_claims={"challenge": "fresh-challenge", "aud": "urn:commerce:seller"})
            self.auth_count += 1
            expiry = datetime.fromtimestamp(self.now[0] + 300, timezone.utc).isoformat()
            return {"session_id": f"private-session-{self.auth_count}", "expires_at": expiry, "expires_in": 300}
        assert headers == {"X-Agent-Session": f"private-session-{self.auth_count}"}
        return {"ok": True}


def make_client():
    key, now = AgentKey.generate(), [NOW]
    transport = GatewayTransport(key, now)
    config = DidAuthConfig("https://gateway.example/agents/seller", "urn:commerce:seller", "X-Agent-Session")
    return DidAuthClient(key, config, transport=transport, now=lambda: now[0]), transport, now


def test_native_ceremony_and_session_are_bound_to_exact_surface():
    client, transport, _ = make_client()
    session = client.authenticate()
    assert session.headers() == {"X-Agent-Session": "private-session-1"}
    assert "private-session" not in repr(session)
    assert claims(transport.calls[1][2]["challenge_response"])["exp"] == NOW + 60
    assert client.request("POST", "mcp", json={"method": "tools/list"}) == {"ok": True}
    assert transport.calls[-1][1] == "https://gateway.example/agents/seller/mcp"
    assert transport.auth_count == 1


def test_expired_session_is_refreshed_before_next_call():
    client, transport, now = make_client()
    client.request("POST", "mcp")
    now[0] += 300
    client.request("POST", "mcp")
    assert transport.auth_count == 2


@pytest.mark.parametrize("path", ["https://other.example/mcp", "//other.example/mcp", "../mcp", "%2e%2e/mcp", "a\\b", "mcp#fragment"])
def test_cross_surface_requests_are_refused_before_any_authentication(path):
    client, transport, _ = make_client()
    with pytest.raises(DidAuthError, match="configured surface"):
        client.request("POST", path)
    assert transport.calls == []


@pytest.mark.parametrize("kwargs", [
    {"surface_url": "http://remote.example/seller"},
    {"surface_url": "https://user:password@gateway.example/seller"},
    {"session_prefix": "Bearer "}, {"session_header": "X-Session\r\nInjected"},
    {"audience": ""}, {"proof_ttl_seconds": 0},
])
def test_invalid_gateway_configuration_fails_closed(kwargs):
    config = dict(surface_url="https://gateway.example/seller", audience="urn:seller", session_header="X-Session")
    config.update(kwargs)
    with pytest.raises(ValueError):
        DidAuthConfig(**config)


def test_gateway_errors_never_include_request_proof_or_response_body():
    client, _, _ = make_client()
    def refused(*args):
        raise HTTPError(args[1], 401, "private-session-secret", {}, None)
    client._transport = refused
    with pytest.raises(DidAuthError, match="HTTP 401") as error:
        client.authenticate()
    assert "private-session" not in str(error.value)


def test_invalid_or_expired_session_response_is_refused():
    client, transport, _ = make_client()
    def bad_expiry(method, url, body, headers):
        response = transport(method, url, body, headers)
        if url.endswith("/authenticate"):
            response["expires_at"] = "2020-01-01T00:00:00Z"
        return response
    client._transport = bad_expiry
    with pytest.raises(DidAuthError, match="expired session"):
        client.authenticate()
    assert client._session is None


def test_invalid_signed_timestamp_types_and_long_lifetime_are_refused():
    key = AgentKey.generate()
    for payload in ({"iat": True, "exp": NOW + 60}, {"iat": NOW},
                    {"iat": NOW, "exp": NOW + 9999}):
        with pytest.raises(IdentityError):
            verify_jws(sign_jws(key, payload), key.did, now=NOW)
