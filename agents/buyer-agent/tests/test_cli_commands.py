"""Offline tests for the reference agent's declared custom CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from cogit_agent_sdk import CliCommand, CliCommandGroup, CogitAgent
from cogit_runtime.cli import main

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "cogit.yaml"


def test_reference_report_emit_writes_summary(tmp_path: Path) -> None:
    output = tmp_path / "report.json"

    result = main(
        [
            "reference-report",
            "emit",
            "--manifest",
            str(MANIFEST),
            "--output",
            str(output),
        ],
    )

    assert result == 0
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["agent"] == "buyer-agent"
    record_ids = {record["record_id"] for record in payload["records"]}
    assert "record-open" in record_ids


class _ReservedNameAgent(CogitAgent):
    def commands(self) -> list[CliCommandGroup]:
        return [
            CliCommandGroup(
                name="serve",
                commands=[
                    CliCommand(
                        name="status",
                        arguments=[],
                        handler=lambda services, args: 0,
                    ),
                ],
            ),
        ]


def test_reserved_command_name_is_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # This fixture deliberately selects a different test class. Legacy manifests
    # without an authored selector retain explicit --agent compatibility.
    payload = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    payload["metadata"].pop("entrypoint")
    manifest = tmp_path / "cogit.yaml"
    manifest.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = main(
        [
            "bogus",
            "--manifest",
            str(manifest),
            "--agent",
            f"{__name__}:_ReservedNameAgent",
        ],
    )

    assert result != 0
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "serve" in combined
    assert "reservednameagent" in combined
