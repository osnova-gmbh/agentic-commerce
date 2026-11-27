"""Contract of the delivery loop (SPEC §7 steps 1, 2 and 5). Uses only the ``env`` fixture."""


def send_note(env, sender, recipient, text="hello"):
    return sender.messaging.send("test.note", 1, recipient.did, "conv-1", {"text": text})


def test_a_message_is_claimed_admitted_and_acknowledged_exactly_once(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent", "seller")
    message_id = send_note(env, alice, bob)
    assert bob.loop.run_once() == 1
    assert [envelope["message_id"] for envelope in bob.handler.seen] == [message_id]
    assert bob.handler.seen[0] == env.message(message_id)["envelope"]
    row = env.message(message_id)
    assert (row["status"], row["attempts"], row["reason"]) == ("processed", 1, None)
    assert row["run_id"] and row["acked_at"]
    env.advance(env.redeliver_after_s + 1)
    assert bob.loop.run_once() == 0
    assert alice.loop.run_once() == 0
    assert len(bob.handler.seen) == 1


def test_messages_are_delivered_oldest_first(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    sent = [send_note(env, alice, bob, text) for text in ("one", "two", "three")]
    assert bob.loop.run_once() == 3
    assert [envelope["message_id"] for envelope in bob.handler.seen] == sent


def test_a_loop_that_dies_before_acknowledging_leads_to_redelivery_and_one_run(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    message_id = send_note(env, alice, bob)
    (claimed,) = env.claim(bob)
    run_id = env.admit(bob, claimed["envelope"])  # the loop dies here: admitted, never acknowledged
    assert len(bob.handler.seen) == 1
    assert bob.loop.run_once() == 0  # still claimed by the dead loop
    assert env.message(message_id)["status"] == "claimed"
    env.advance(env.redeliver_after_s + 1)
    assert bob.loop.run_once() == 1
    assert len(bob.handler.seen) == 1  # the same run answered; the handler did not run again
    row = env.message(message_id)
    assert (row["status"], row["attempts"], row["run_id"]) == ("processed", 2, run_id)
    assert bob.loop.run_once() == 0


def test_a_loop_that_dies_between_claim_and_admission_leads_to_redelivery(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    message_id = send_note(env, alice, bob)
    assert len(env.claim(bob)) == 1  # the loop dies here: claimed, never admitted
    env.advance(env.redeliver_after_s + 1)
    assert bob.loop.run_once() == 1
    assert len(bob.handler.seen) == 1
    assert env.message(message_id)["status"] == "processed"


def test_a_handler_that_raises_is_released_and_retried(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    bob.handler.script = ["raise"]
    message_id = send_note(env, alice, bob)
    assert bob.loop.run_once() == 1
    row = env.message(message_id)
    assert (row["status"], row["attempts"]) == ("queued", 1)
    assert bob.loop.run_once() == 0  # released with a delay, not due yet
    env.advance(2)
    assert bob.loop.run_once() == 1
    row = env.message(message_id)
    assert (row["status"], row["attempts"], row["reason"]) == ("processed", 2, None)
    assert len(bob.handler.seen) == 2
    assert bob.loop.run_once() == 0


def test_a_handler_that_fails_twice_is_released_twice(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    bob.handler.script = ["raise", "raise"]
    message_id = send_note(env, alice, bob)
    for attempt in (1, 2):
        assert bob.loop.run_once() == 1
        assert (env.message(message_id)["status"], env.message(message_id)["attempts"]) == ("queued", attempt)
        env.advance(2)
    assert bob.loop.run_once() == 1
    assert (env.message(message_id)["status"], env.message(message_id)["attempts"]) == ("processed", 3)


def test_a_handler_returning_rejected_is_acknowledged_as_rejected(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    bob.handler.script = ["rejected"]
    message_id = send_note(env, alice, bob)
    assert bob.loop.run_once() == 1
    row = env.message(message_id)
    assert (row["status"], row["reason"], row["attempts"]) == ("rejected", "not_wanted", 1)
    assert row["run_id"]
    env.advance(env.redeliver_after_s + 1)
    assert bob.loop.run_once() == 0
    assert len(bob.handler.seen) == 1


def test_a_tampered_envelope_is_rejected_with_bad_signature_and_never_admitted(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    envelope = env.sign(alice, "test.note", 1, bob.did, "conv-1", {"text": "pay 10"})
    envelope["body"]["text"] = "pay 1000"
    assert env.send_raw(alice, envelope) == "queued"  # the queue checks no signature
    good = send_note(env, alice, bob)
    assert bob.loop.run_once() == 2
    assert [seen["message_id"] for seen in bob.handler.seen] == [good]
    row = env.message(envelope["message_id"])
    assert (row["status"], row["reason"], row["run_id"]) == ("rejected", "bad_signature", None)
    assert env.message(good)["status"] == "processed"
    env.advance(env.redeliver_after_s + 1)
    assert bob.loop.run_once() == 0


def test_an_envelope_signed_with_another_key_is_rejected(env):
    alice, bob, mallory = env.agent("alice-agent"), env.agent("bob-agent"), env.agent("mallory-agent")
    forged = env.sign(mallory, "test.note", 1, bob.did, "conv-1", {"text": "from alice, honestly"})
    forged["sender_did"] = alice.did
    assert env.send_raw(alice, forged) == "queued"
    assert bob.loop.run_once() == 1
    assert bob.handler.seen == []
    assert env.message(forged["message_id"])["reason"] == "bad_signature"


def test_an_installation_claims_only_messages_for_its_own_dids(env):
    alice, bob, carol = env.agent("alice-agent"), env.agent("bob-agent"), env.agent("carol-agent", "seller")
    to_bob = send_note(env, alice, bob)
    to_carol = send_note(env, alice, carol)
    assert env.claim(alice) == []
    assert [message["message_id"] for message in env.claim(carol)] == [to_carol]
    assert bob.loop.run_once() == 1
    assert [envelope["message_id"] for envelope in bob.handler.seen] == [to_bob]
    assert carol.handler.seen == []


def test_a_handler_can_reply_through_its_messaging_seam(env):
    alice, bob = env.agent("alice-agent"), env.agent("bob-agent")
    replies = []

    def reply(envelope):
        body = {"text": "re: " + envelope["body"]["text"]}
        replies.append(
            bob.messaging.send("test.note", 1, envelope["sender_did"], "conv-1", body, envelope["message_id"])
        )

    bob.handler.on_message = reply
    request = send_note(env, alice, bob, "ping")
    assert bob.loop.run_once() == 1
    assert alice.loop.run_once() == 1
    (reply_envelope,) = alice.handler.seen
    assert reply_envelope["message_id"] == replies[0] and reply_envelope["causation_id"] == request
    assert reply_envelope["body"] == {"text": "re: ping"}
    assert [row["status"] for row in env.conversation("conv-1")] == ["processed", "processed"]
