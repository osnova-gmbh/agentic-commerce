"""The packaged seller must deliver the advertised training service."""

import io
import zipfile

import pytest

from world import BUYER, EVALUATOR, ESCROW, SELLER, DemoWorld


@pytest.mark.parametrize("mode", ["ok", "broken"])
def test_packaged_training_completes_through_agent_inboxes(tmp_path, mode):
    world = DemoWorld(tmp_path, mode)
    try:
        world._setenv("BUYER_MAX_PRICE_MINOR", "200000")
        world.tick()
        world.act(SELLER, "publish_catalog")
        selected = world.act(BUYER, "start_purchase", {
            "category": "training", "max_price_minor": 200000,
        })
        assert selected["offer_id"] == "ai-training"
        deal_id = selected["deal_id"]
        for _ in range(40):
            for role in (BUYER, SELLER, EVALUATOR, ESCROW):
                result = world.act(role, "drain_inbox")
                assert result["released"] == 0
            world.tick()
            if world.deal(deal_id)["deal"]["state"] == "SETTLED":
                break
        read = world.deal(deal_id)
        assert read["deal"]["state"] == "SETTLED"
        assert read["deal"]["terms"]["offer_id"] == "ai-training"
        delivery = max(read["deliveries"], key=lambda row: row["attempt"])
        assert delivery["attempt"] == (2 if mode == "broken" else 1)
        with zipfile.ZipFile(io.BytesIO(world.bus.artifacts.get(delivery["artifact_id"]))) as bundle:
            assert set(bundle.namelist()) == {"course.md", "exercises.md", "summary.json"}
            assert b"Agentic commerce" in bundle.read("course.md")
        assert world.balances(deal_id)["seller"] == 118800
        assert world.balances(deal_id)["fee"] == 1200
        assert world.balances(deal_id)["held"] == 0
    finally:
        world.close()
