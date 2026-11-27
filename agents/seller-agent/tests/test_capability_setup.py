"""Host setup must reject unusable declarations without exposing input values."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from cogit_runtime.manifest import load_manifest

from seller_agent_setup import main, read_manifest

ROOT = Path(__file__).resolve().parents[1]


def original() -> dict[str, Any]:
    return read_manifest(ROOT / "cogit.yaml")


def save(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "agent.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_literal_invalid_secret_never_appears_in_setup_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = original()
    payload["metadata"]["cogit_tools"] = {
        "unexpected_credential": "fixture-sensitive-input"
    }
    path = save(tmp_path, payload)
    before = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        main(["--manifest", str(path)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "fixture-sensitive-input" not in output.err + output.out
    assert "input_value" not in output.err
    assert "extra_forbidden" in output.err
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", [ValueError, RuntimeError, OSError])
def test_arbitrary_provider_error_is_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: type[Exception],
) -> None:
    path = save(tmp_path, original())
    before = path.read_bytes()

    def rejected(payload: dict[str, Any]) -> dict[str, Any]:
        raise failure("fixture-sensitive-provider-error")

    package_name = "seller_agent_setup"
    monkeypatch.setattr(f"{package_name}.cli.resolved_manifest", rejected)
    with pytest.raises(SystemExit):
        main(["--manifest", str(path)])
    assert "fixture-sensitive-provider-error" not in capsys.readouterr().err
    assert path.read_bytes() == before


def test_invalid_runtime_configuration_is_rejected_without_rewrite(
    tmp_path: Path,
) -> None:
    payload = original()
    payload["runtime"]["worker"]["concurrency"] = "invalid-integer"
    path = save(tmp_path, payload)
    before = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        main(["--manifest", str(path)])
    assert error.value.code == 1 and path.read_bytes() == before


def test_setup_accepts_runtime_supported_sdk_aliases(tmp_path: Path) -> None:
    payload = original()
    payload["evalSuites"] = payload.pop("eval_suites")
    path = save(tmp_path, payload)
    assert main(["--manifest", str(path)]) == 0
    assert load_manifest(path).descriptor.eval_suites == payload["evalSuites"]


def test_model_selection_declares_sdk_profile_and_preserves_runtime_settings(
    tmp_path: Path,
) -> None:
    payload = original()
    payload["runtime"]["trace"] = {"persist_messages": False}
    path = save(tmp_path, payload)
    assert (
        main(
            [
                "--manifest",
                str(path),
                "--model",
                "fixture-model",
                "--context-window",
                "32000",
                "--max-output-tokens",
                "1024",
            ]
        )
        == 0
    )
    result = load_manifest(path)
    assert result.config.model.profile == "sdk"
    assert result.config.trace.persist_messages is False
    assert result.descriptor.model is not None
    assert result.descriptor.model.provider == "openai"
    assert result.descriptor.model.context_window == 32000
    assert result.descriptor.model.max_output_tokens == 1024


@pytest.mark.parametrize("provider", ["runtime", "unknown-provider"])
def test_setup_rejects_unsupported_model_capabilities(
    tmp_path: Path, provider: str
) -> None:
    path = save(tmp_path, original())
    before = path.read_bytes()
    with pytest.raises(SystemExit):
        main(
            [
                "--manifest",
                str(path),
                "--model",
                "echo",
                "--model-provider",
                provider,
                "--context-window",
                "32000",
                "--max-output-tokens",
                "1024",
            ]
        )
    assert path.read_bytes() == before


def test_reference_configuration_preserves_existing_policy_marker(
    tmp_path: Path,
) -> None:
    payload = original()
    policy = {"authority": "agentdb", "contract": "runtime.checkpoint.v1"}
    payload["metadata"]["cogit_policy"] = policy
    path = save(tmp_path, payload)
    assert main(["--manifest", str(path)]) == 0
    assert read_manifest(path)["metadata"]["cogit_policy"] == policy


@pytest.mark.parametrize(
    "arguments",
    [
        ["--model", "fixture"],
        ["--model", "fixture", "--context-window", "32000"],
        ["--model", "fixture", "--max-output-tokens", "1024"],
        ["--context-window", "32000"],
    ],
)
def test_model_selection_requires_explicit_bounds_without_rewrite(
    tmp_path: Path, arguments: list[str]
) -> None:
    path = save(tmp_path, original())
    before = path.read_bytes()
    with pytest.raises(SystemExit):
        main(["--manifest", str(path), *arguments])
    assert path.read_bytes() == before


@pytest.mark.parametrize("level", [None, "none", "low"])
def test_setup_preserves_explicit_reasoning_configuration(
    tmp_path: Path, level: str | None
) -> None:
    path = save(tmp_path, original())
    args = [
        "--manifest",
        str(path),
        "--model",
        "fixture-model",
        "--context-window",
        "32000",
        "--max-output-tokens",
        "1024",
    ]
    if level is not None:
        args.extend(["--thinking-level", level])
    assert main(args) == 0
    descriptor = load_manifest(path).descriptor.model
    assert descriptor is not None
    if level is None:
        assert descriptor.defaults is None
    else:
        assert descriptor.defaults is not None
        assert descriptor.defaults.thinking_level == level


def test_reasoning_option_without_model_never_rewrites(tmp_path: Path) -> None:
    path = save(tmp_path, original())
    before = path.read_bytes()
    with pytest.raises(SystemExit):
        main(["--manifest", str(path), "--thinking-level", "none"])
    assert path.read_bytes() == before
