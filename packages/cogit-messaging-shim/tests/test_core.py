import copy

import pytest

from cogit_messaging_shim import (
    ZERO_HASH,
    AgentKey,
    build_envelope,
    canonical_bytes,
    canonical_hash,
    event_hash,
    public_key_from_did,
    reply_message_id,
    verify_envelope,
)
from cogit_messaging_shim.testing import RecordingMessaging


def test_canonical_bytes_are_sorted_compact_utf8():
    assert canonical_bytes({"b": 1, "a": {"z": None, "y": "é"}}) == '{"a":{"y":"é","z":null},"b":1}'.encode()
    assert len(canonical_hash({"a": 1})) == 64


def test_canonical_bytes_reject_floats():
    with pytest.raises(TypeError):
        canonical_bytes({"amount": 1.5})


def test_did_key_round_trip(tmp_path):
    key = AgentKey.generate()
    assert key.did.startswith("did:key:z6Mk")
    assert len(public_key_from_did(key.did)) == 32
    stored = AgentKey.load_or_create(tmp_path / "keys" / "a.key")
    assert AgentKey.load_or_create(tmp_path / "keys" / "a.key").did == stored.did
    assert AgentKey.from_seed(key.seed).did == key.did


def test_known_did_key_vector():
    # Ed25519 seed of 32 zero bytes: a fixed vector that other implementations can check.
    assert AgentKey.from_seed(bytes(32)).did == "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp"


def test_envelope_signature_detects_tampering():
    alice, bob = AgentKey.generate(), AgentKey.generate()
    envelope = build_envelope(alice, alice.did, "finance.accept_terms", 1, bob.did, "deal-1", {"terms_hash": "0" * 64})
    assert verify_envelope(envelope)
    tampered = copy.deepcopy(envelope)
    tampered["body"]["terms_hash"] = "1" * 64
    assert not verify_envelope(tampered)
    forged = dict(envelope, sender_did=bob.did)
    assert not verify_envelope(forged)
    assert not verify_envelope({**envelope, "extra": 1})
    assert not verify_envelope({k: v for k, v in envelope.items() if k != "signature"})


def test_replies_get_a_stable_message_id():
    alice, bob = AgentKey.generate(), AgentKey.generate()
    cause = "3f0c9f0e-55d5-4c6b-9c0a-6f1f1c1d2e3f"
    first = build_envelope(alice, alice.did, "finance.quote", 1, bob.did, "deal-1", {}, cause)
    again = build_envelope(alice, alice.did, "finance.quote", 1, bob.did, "deal-1", {}, cause)
    assert first["message_id"] == again["message_id"] == reply_message_id(cause, "finance.quote", bob.did)
    fresh = build_envelope(alice, alice.did, "finance.quote", 1, bob.did, "deal-1", {})
    assert fresh["message_id"] != first["message_id"]


def test_event_hash_chains_on_prev_hash():
    event = {
        "deal_id": "d",
        "seq": 1,
        "prev_hash": ZERO_HASH,
        "event_type": "service_request",
        "source_message_id": "m",
        "actor_did": "did:key:zA",
        "body": {},
        "state_after": "REQUESTED",
    }
    first = event_hash(event)
    assert len(first) == 64
    assert event_hash({**event, "prev_hash": first}) != first
    assert event_hash({**event, "hash": "ignored", "recorded_at": "ignored"}) == first


def test_recording_messaging_keeps_signed_envelopes():
    messaging = RecordingMessaging()
    message_id = messaging.send("finance.cancel", 1, "did:key:zB", "deal-1", {})
    assert messaging.sent[0]["message_id"] == message_id
    assert verify_envelope(messaging.sent[0])
    assert messaging.of_type("finance.cancel") == messaging.sent
