from conftest import DIDS, Bench, code_of


def test_send_stores_the_envelope_verbatim_and_queues_it(bench):
    envelope = bench.envelope(causation_id="00000000-0000-4000-8000-00000000cafe")
    assert bench.command("alice-agent", "message.send", {"envelope": envelope}) == {
        "message_id": envelope["message_id"],
        "status": "queued",
    }
    assert bench.query("carol-agent", "conversation.read", {"conversation_id": "conv-1"})["messages"] == [
        {
            "message_id": envelope["message_id"],
            "type_key": "test.note",
            "type_version": 1,
            "sender_did": DIDS["alice-agent"],
            "recipient_did": DIDS["bob-agent"],
            "causation_id": "00000000-0000-4000-8000-00000000cafe",
            "status": "queued",
            "reason": None,
            "attempts": 0,
            "run_id": None,
            "created_at": "2026-11-27T12:00:00Z",
            "acked_at": None,
            "envelope": envelope,
        }
    ]


def test_send_is_idempotent_on_message_id(bench):
    envelope = bench.send()
    changed = {**envelope, "body": {"text": "another text under the same id"}}
    result = bench.command("alice-agent", "message.send", {"envelope": changed})
    assert result == {"message_id": envelope["message_id"], "status": "duplicate"}
    assert bench.row(envelope["message_id"])["envelope"] == envelope
    assert len(bench.claim()) == 1


def test_send_refuses_a_did_of_another_installation(bench):
    send = lambda caller, envelope: bench.command(caller, "message.send", {"envelope": envelope})  # noqa: E731
    assert code_of(send, "carol-agent", bench.envelope(sender="alice-agent")) == "not_your_did"
    assert code_of(send, "alice-agent", bench.envelope(sender_did="did:key:zNobody")) == "not_your_did"
    assert (
        code_of(bench.command, "alice-agent", "message.send", {"envelope": bench.envelope()}, "operator")
        == "not_your_did"
    )
    assert bench.query("alice-agent", "conversation.read", {"conversation_id": "conv-1"}) == {"messages": []}


def test_send_refuses_unknown_recipient_unknown_type_and_invalid_body(bench):
    send = lambda **overrides: bench.command("alice-agent", "message.send", {"envelope": bench.envelope(**overrides)})  # noqa: E731
    assert code_of(send, recipient_did="did:key:zNobody") == "unknown_recipient"
    assert code_of(send, type_key="test.unregistered") == "unknown_type"
    assert code_of(send, type_version=2) == "unknown_type"
    assert code_of(send, body={"text": 5}) == "invalid_body"
    assert code_of(send, body={}) == "invalid_body"
    assert code_of(send, body={"text": "ok", "extra": 1}) == "invalid_body"


def test_send_refuses_a_malformed_envelope(bench):
    send = lambda envelope: bench.command("alice-agent", "message.send", {"envelope": envelope})  # noqa: E731
    good = bench.envelope()
    assert code_of(send, None) == "invalid_envelope"
    assert code_of(send, {k: v for k, v in good.items() if k != "signature"}) == "invalid_envelope"
    assert code_of(send, {**good, "extra": 1}) == "invalid_envelope"
    assert code_of(send, {**good, "envelope_version": 2}) == "invalid_envelope"
    assert code_of(send, {**good, "created_at": "2026-11-27 12:00"}) == "invalid_envelope"
    assert code_of(send, {**good, "body": {"text": "x", "amount": 1.5}}) == "invalid_envelope"
    assert code_of(send, {**good, "body": "text"}) == "invalid_envelope"


def test_claim_returns_only_messages_for_the_callers_dids(bench):
    to_bob, to_carol = bench.send(recipient="bob-agent"), bench.send(recipient="carol-agent")
    assert bench.claim("alice-agent") == []
    assert bench.claim("operator") == []
    assert bench.claim("bob-agent") == [{"message_id": to_bob["message_id"], "envelope": to_bob, "attempts": 1}]
    assert [m["message_id"] for m in bench.claim("carol-agent")] == [to_carol["message_id"]]
    row = bench.host.db.execute("SELECT * FROM msg_messages WHERE message_id = ?", (to_bob["message_id"],)).fetchone()
    assert (row["status"], row["claimed_at"], row["admission_key"]) == (
        "claimed",
        "2026-11-27T12:00:00Z",
        f"msg:{to_bob['message_id']}",
    )


def test_claim_is_oldest_first_and_honours_the_limit(bench):
    sent = [bench.send()["message_id"] for _ in range(3)]
    assert [m["message_id"] for m in bench.claim(limit=2)] == sent[:2]
    assert [m["message_id"] for m in bench.claim()] == sent[2:]
    assert bench.claim() == []
    assert code_of(bench.claim, limit=0) == "invalid_argument"


def test_an_unacknowledged_claim_is_redelivered_after_redeliver_after_s(bench):
    message_id = bench.send()["message_id"]
    assert bench.claim()[0]["attempts"] == 1
    bench.clock.advance(29)
    assert bench.claim() == []
    bench.clock.advance(1)
    assert bench.claim() == [{"message_id": message_id, "envelope": bench.row(message_id)["envelope"], "attempts": 2}]


def test_ack_records_outcome_reason_and_run_and_can_be_repeated(bench):
    first, second = bench.send()["message_id"], bench.send()["message_id"]
    bench.claim()
    bench.clock.advance(3)
    assert (
        bench.command("bob-agent", "message.ack", {"message_id": first, "outcome": "processed", "run_id": "run_1"})
        == {}
    )
    bench.command("bob-agent", "message.ack", {"message_id": second, "outcome": "rejected", "reason": "bad_signature"})
    bench.clock.advance(60)
    bench.command("bob-agent", "message.ack", {"message_id": first, "outcome": "rejected", "reason": "late"})
    row = bench.row(first)
    assert (row["status"], row["reason"], row["run_id"], row["acked_at"]) == (
        "processed",
        None,
        "run_1",
        "2026-11-27T12:00:03Z",
    )
    row = bench.row(second)
    assert (row["status"], row["reason"], row["run_id"]) == ("rejected", "bad_signature", None)
    assert bench.claim() == []


def test_ack_and_release_are_for_the_recipients_installation_only(bench):
    message_id = bench.send()["message_id"]
    bench.claim()
    for export, args in (("message.ack", {"outcome": "processed"}), ("message.release", {})):
        assert code_of(bench.command, "alice-agent", export, {"message_id": message_id, **args}) == "not_your_message"
        assert code_of(bench.command, "bob-agent", export, {"message_id": "missing", **args}) == "unknown_message"
    assert (
        code_of(bench.command, "bob-agent", "message.ack", {"message_id": message_id, "outcome": "done"})
        == "invalid_argument"
    )
    assert bench.row(message_id)["status"] == "claimed"


def test_release_returns_a_claimed_message_to_the_queue_after_the_delay(bench):
    now, later = bench.send()["message_id"], bench.send()["message_id"]
    bench.claim()
    assert bench.command("bob-agent", "message.release", {"message_id": now}) == {}
    bench.command("bob-agent", "message.release", {"message_id": later, "delay_s": 10})
    assert bench.row(later)["status"] == "queued"
    assert [m["message_id"] for m in bench.claim()] == [now]
    bench.clock.advance(9)
    assert bench.claim() == []
    bench.clock.advance(1)
    assert bench.claim() == [{"message_id": later, "envelope": bench.row(later)["envelope"], "attempts": 2}]


def test_release_of_a_message_that_is_not_claimed_changes_nothing(bench):
    message_id = bench.send()["message_id"]
    bench.command("bob-agent", "message.release", {"message_id": message_id, "delay_s": 600})
    assert bench.claim()[0]["message_id"] == message_id
    bench.command("bob-agent", "message.ack", {"message_id": message_id, "outcome": "processed"})
    bench.command("bob-agent", "message.release", {"message_id": message_id})
    assert bench.row(message_id)["status"] == "processed"


def test_a_message_is_dead_after_max_delivery_attempts():
    bench = Bench({"max_delivery_attempts": 2, "redeliver_after_s": 5})
    for installation_id in ("alice-agent", "bob-agent"):
        bench.register(installation_id, DIDS[installation_id])
    schema = {"type": "object"}
    bench.command("cogit-finance", "type.register", {"type_key": "test.note", "type_version": 1, "json_schema": schema})
    released, abandoned = bench.send()["message_id"], bench.send()["message_id"]
    assert len(bench.claim()) == 2
    bench.command("bob-agent", "message.release", {"message_id": released})
    bench.clock.advance(5)
    assert [m["attempts"] for m in bench.claim()] == [2, 2]
    bench.command("bob-agent", "message.release", {"message_id": released})
    assert (bench.row(released)["status"], bench.row(released)["reason"]) == ("dead", "max_delivery_attempts")
    bench.clock.advance(5)
    assert bench.claim() == []
    assert (bench.row(abandoned)["status"], bench.row(abandoned)["attempts"]) == ("dead", 2)


def test_conversation_read_lists_one_conversation_in_insertion_order(bench):
    first = bench.send(conversation_id="conv-a")["message_id"]
    bench.send(conversation_id="conv-b")
    second = bench.send(sender="bob-agent", recipient="alice-agent", conversation_id="conv-a")["message_id"]
    messages = bench.query("operator", "conversation.read", {"conversation_id": "conv-a"})["messages"]
    assert [m["message_id"] for m in messages] == [first, second]
    assert bench.query("operator", "conversation.read", {"conversation_id": "conv-none"}) == {"messages": []}
