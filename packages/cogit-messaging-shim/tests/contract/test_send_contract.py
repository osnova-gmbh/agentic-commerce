"""Contract of ``MessagingSeams.send`` and the queue behind it. Uses only the ``env`` fixture."""

CAUSE = "3f0c9f0e-55d5-4c6b-9c0a-6f1f1c1d2e3f"


def test_send_signs_and_queues_one_message(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent", "seller")
    message_id = alice.messaging.send("test.note", 1, bob.did, "conv-1", {"text": "hello"}, CAUSE)
    row = env.message(message_id)
    assert (row["status"], row["attempts"], row["sender_did"], row["recipient_did"]) == (
        "queued",
        0,
        alice.did,
        bob.did,
    )
    assert (row["type_key"], row["type_version"], row["causation_id"]) == ("test.note", 1, CAUSE)
    envelope = row["envelope"]
    assert envelope["message_id"] == message_id and envelope["body"] == {"text": "hello"}
    assert envelope["envelope_version"] == 1 and envelope["conversation_id"] == "conv-1" and envelope["signature"]


def test_sending_with_another_installations_did_is_refused(env):
    alice, bob, mallory = env.agent("alice-agent"), env.agent("bob-agent"), env.agent("mallory-agent")
    envelope = env.sign(alice, "test.note", 1, bob.did, "conv-1", {"text": "pay mallory"})
    with env.refused("not_your_did"):
        env.send_raw(mallory, envelope)
    assert env.conversation("conv-1") == []
    assert bob.loop.run_once() == 0


def test_a_duplicate_message_id_is_reported_and_delivered_once(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    envelope = env.sign(alice, "test.note", 1, bob.did, "conv-1", {"text": "hello"})
    assert env.send_raw(alice, envelope) == "queued"
    assert env.send_raw(alice, envelope) == "duplicate"
    assert len(env.conversation("conv-1")) == 1
    assert bob.loop.run_once() == 1
    assert env.send_raw(alice, envelope) == "duplicate"
    assert bob.loop.run_once() == 0
    assert len(bob.handler.seen) == 1


def test_a_reply_sent_twice_is_one_message(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    first = alice.messaging.send("test.note", 1, bob.did, "conv-1", {"text": "reply"}, CAUSE)
    again = alice.messaging.send("test.note", 1, bob.did, "conv-1", {"text": "reply"}, CAUSE)
    assert first == again
    assert bob.loop.run_once() == 1
    assert [envelope["message_id"] for envelope in bob.handler.seen] == [first]


def test_an_unregistered_type_is_refused(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    with env.refused("unknown_type"):
        alice.messaging.send("test.unregistered", 1, bob.did, "conv-1", {"text": "hello"})
    with env.refused("unknown_type"):
        alice.messaging.send("test.note", 2, bob.did, "conv-1", {"text": "hello"})
    assert env.conversation("conv-1") == []


def test_a_body_that_does_not_match_the_schema_is_refused(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    for body in ({"text": 5}, {}, {"text": "hello", "extra": True}, {"text": ""}):
        with env.refused("invalid_body"):
            alice.messaging.send("test.note", 1, bob.did, "conv-1", body)
    assert env.conversation("conv-1") == []


def test_an_unknown_recipient_is_refused(env):
    alice = env.agent("alice-agent")
    with env.refused("unknown_recipient"):
        alice.messaging.send(
            "test.note", 1, "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp", "conv-1", {"text": "x"}
        )


def test_type_register_is_immutable(env):
    schema = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 0}}, "required": ["n"]}
    assert env.register_type("test.count", 1, schema) == "created"
    assert env.register_type("test.count", 1, dict(reversed(list(schema.items())))) == "unchanged"
    with env.refused("type_conflict"):
        env.register_type("test.count", 1, {**schema, "required": []})
    assert env.register_type("test.count", 2, {**schema, "required": []}) == "created"


def test_type_register_refuses_keywords_outside_the_dialect(env):
    for schema in (
        {"$ref": "#/definitions/note"},
        {"type": "object", "properties": {"text": {"type": "string", "pattern": "^a"}}},
        {"type": "object", "additionalProperties": True},
    ):
        with env.refused("unsupported_schema"):
            env.register_type("test.bad", 1, schema)
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    with env.refused("unknown_type"):
        alice.messaging.send("test.bad", 1, bob.did, "conv-1", {})
