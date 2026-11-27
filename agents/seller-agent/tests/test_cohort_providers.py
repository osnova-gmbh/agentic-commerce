"""Deployment preparation binds selected code without importing providers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cohort_providers import provider_wheels, selected_provider_names  # noqa: E402


def manifest(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "agent.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_selected_browser_binds_local_dependency_closure_without_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Entry:
        name = "browser"
        dist = SimpleNamespace(name="cogit-tool-browser")

        def load(self) -> object:
            raise AssertionError("Deployment preparation must not import code")

    monkeypatch.setattr("cohort_providers.entry_points", lambda **kwargs: [Entry()])
    path = manifest(
        tmp_path,
        {
            "metadata": {
                "cogit_tools": {
                    "providers": [{"provider": "browser"}],
                }
            }
        },
    )
    wheels = ROOT / "vendor/wheels"
    sources = {
        "cogit-tool-browser": wheels / "cogit_tool_browser-0.1.2-py3-none-any.whl",
        "cogit-tool-core": wheels / "cogit_tool_core-0.1.1-py3-none-any.whl",
        "cogit-tool-shell": wheels / "cogit_tool_shell-0.1.2-py3-none-any.whl",
        "cogit-transport-browser-session": wheels
        / "cogit_transport_browser_session-0.1.0-py3-none-any.whl",
    }
    selected = provider_wheels(
        path, sources, (), {"cogit-tool-core": sources["cogit-tool-core"]}
    )
    assert {p.name for p in selected} == {
        "cogit_tool_browser-0.1.2-py3-none-any.whl",
        "cogit_transport_browser_session-0.1.0-py3-none-any.whl",
    }


def test_selected_distribution_requires_explicit_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = SimpleNamespace(name="remote", dist=SimpleNamespace(name="custom-api"))
    monkeypatch.setattr("cohort_providers.entry_points", lambda **kwargs: [entry])
    path = manifest(
        tmp_path,
        {
            "metadata": {
                "cogit_tools": {
                    "providers": [{"provider": "remote"}],
                }
            }
        },
    )
    with pytest.raises(ValueError, match="no explicit local wheel"):
        provider_wheels(path, {}, (), {})


@pytest.mark.parametrize(
    "payload",
    [
        {"metadata": False},
        {"metadata": {"cogit_tools": False}},
        {"metadata": {"cogit_tools": {"providers": False}}},
    ],
)
def test_false_values_cannot_hide_invalid_selection(
    tmp_path: Path, payload: object
) -> None:
    with pytest.raises(ValueError):
        selected_provider_names(manifest(tmp_path, payload))


def test_oversized_metadata_is_rejected_before_decompression(tmp_path: Path) -> None:
    wheel = tmp_path / "large.whl"
    with ZipFile(wheel, "w", ZIP_DEFLATED) as archive:
        archive.writestr("large.dist-info/METADATA", "A" * (256 * 1024 + 1))
    with pytest.raises(ValueError, match="metadata exceeds"):
        provider_wheels(manifest(tmp_path, {}), {}, (wheel,), {})
