"""Verify the acceptance fixture's independent oracle and authentication gate."""

from __future__ import annotations

import hashlib

import httpx
import pytest
from capability_proof.portal import Portal, Scenario


@pytest.mark.parametrize("seed", [18, 19, 20])
def test_portal_requires_login_and_serves_private_originals(seed: int) -> None:
    scenario = Scenario.create(seed)
    portal = Portal(scenario)
    portal.start()
    try:
        with httpx.Client(follow_redirects=True, trust_env=False) as client:
            assert client.get(portal.url).status_code == 401
            assert client.get(portal.login_url).status_code == 200
            assert len(client.cookies) == 1
            account = client.get(portal.url + scenario.account_route.lstrip("/"))
            assert account.status_code == 200
            catalog = client.get(portal.url + scenario.catalog_route.lstrip("/"))
            assert all(record.number in catalog.text for record in scenario.records)
            first = scenario.records[0]
            url = portal.url.rstrip("/") + scenario.document_prefix + first.number
            partial = client.get(url)
            assert partial.content.startswith(b"%PDF-")
            assert b"%%EOF" not in partial.content
            assert (
                hashlib.sha256(partial.content).hexdigest()
                != (portal.expected_hashes()[first.number])
            )
            for record in scenario.records:
                url = portal.url.rstrip("/") + scenario.document_prefix + record.number
                complete = client.get(url)
                assert complete.headers["content-type"] == "application/pdf"
                assert complete.content == record.document
                assert any(byte >= 128 for byte in complete.content)
                assert (
                    complete.content.decode("utf-8", errors="replace").encode("utf-8")
                    != complete.content
                )
                assert (
                    hashlib.sha256(complete.content).hexdigest()
                    == (portal.expected_hashes()[record.number])
                )
            with httpx.Client(cookies=client.cookies, trust_env=False) as restarted:
                assert restarted.get(portal.url).status_code == 200
        documents = [event for event in portal.events if event["kind"] == "document"]
        assert [event["partial"] for event in documents] == [True, False, False, False]
        assert [event["kind"] for event in portal.events].count("login") == 1
        assert all("code=" not in str(event) for event in portal.events)
    finally:
        portal.close()


def test_same_records_have_fresh_routes_and_login_each_time() -> None:
    first, second = Scenario.create(18), Scenario.create(18)
    assert first.records == second.records
    assert first.account_route != second.account_route
    assert first.catalog_route != second.catalog_route
    assert first.document_prefix != second.document_prefix
