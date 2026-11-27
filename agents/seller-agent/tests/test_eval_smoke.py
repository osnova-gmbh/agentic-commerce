"""Run the checked-in eval suite through the black-box HTTP runner."""

from pathlib import Path

import httpx
import pytest
from cogit_runtime import CogitRuntimeApp
from cogit_runtime.eval_runner import EvalRunner

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_smoke_eval_passes(runtime: CogitRuntimeApp) -> None:
    transport = httpx.ASGITransport(app=runtime.build())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://reference.test",
    ) as client:
        runner = EvalRunner.from_manifest(
            manifest_path=str(ROOT / "cogit.yaml"),
            endpoint="http://reference.test",
            suite_name="smoke",
            store=runtime.state.store,
            client=client,
        )
        result = await runner.run()

    assert result.status == "completed"
    assert result.items_passed == result.items_total == 6
    assert result.score == 1.0
