"""Docker hardening checks."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_pins_base_image_digest() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.11.16-slim-bookworm@sha256:" in dockerfile
    digest = "528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84"
    assert digest in dockerfile


def test_dockerfile_installs_verified_complete_closure() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "PIP_NO_CACHE_DIR=1" in dockerfile
    assert "scripts/verify_framework_wheels.py" in dockerfile
    assert "scripts/verify_installed_packages.py" in dockerfile
    assert "uv lock --check" in dockerfile
    assert "uv sync --frozen --no-dev --no-editable" in dockerfile
    assert "uv pip check" in dockerfile
    assert "find /app/src -type f -exec chmod 0644 {} +" in dockerfile
    assert "ghcr.io/astral-sh/uv:0.11.28@sha256:" in dockerfile
    assert "USER agent" in dockerfile
    assert "PYTHONPATH=/app/src" not in dockerfile
    assert "COPY --from=builder /app/.venv /app/.venv" in dockerfile
    assert "COPY cogit.yaml /app/cogit.yaml" in dockerfile
    assert "COPY evals /app/evals" in dockerfile
    assert "COPY . /app" not in dockerfile.split(" AS runtime", 1)[1]
    reinstall = (
        "uv pip install --python /app/.venv/bin/python --reinstall --no-deps "
        "/app/.agent-wheel/*.whl"
    )
    assert dockerfile.count("--no-deps") == 1
    sync = dockerfile.index("uv sync --frozen --no-dev --no-editable")
    build = dockerfile.index("uv build --wheel --out-dir /app/.agent-wheel")
    install = dockerfile.index(reinstall)
    check = dockerfile.rindex("uv pip check")
    verify = dockerfile.index(
        ".venv/bin/python -I -B scripts/verify_installed_packages.py"
    )
    assert sync < build < install < check < verify
    for producer in (
        "Dockerfile",
        "scripts/build_image.sh",
        "scripts/build_image.ps1",
        ".github/workflows/ci.yml",
    ):
        content = (ROOT / producer).read_text(encoding="utf-8")
        assert ".build-deps" not in content
        assert ".ci-deps" not in content
        assert "COGIT_REPOSITORY_TOKEN" not in content
        assert "COGIT_AGENT_SDK_SPEC" not in content
        if producer != "Dockerfile":
            assert "--no-deps" not in content


def test_production_runtime_entrypoints_use_isolated_installed_module() -> None:
    launcher = (ROOT / "scripts/start_database_worker.sh").read_text(encoding="utf-8")
    assert "exec python -I -B -m cogit_runtime work" in launcher
    assert "/app/worker-cohort/cogit.yaml" in launcher
    assert '--manifest "$manifest"' in launcher
    assert "--agent " not in launcher
    for required in (
        "COGIT_AGENTDB_COHORT_RECEIPT",
        "COGIT_AGENTDB_INSTALLATION_ID",
        "COGIT_AGENTDB_POOL_ID",
        "COGIT_AGENTDB_URL",
        "COGIT_AGENTDB_API_VERSION",
        "COGIT_AGENTDB_WORKER_TOKEN",
    ):
        assert f"${{{required}:?" in launcher

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert (
        "--manifest /app/cogit.yaml --agent-wheel-dir /app/.agent-wheel" in dockerfile
    )
    assert 'CMD ["sh", "/app/scripts/start_database_worker.sh"]' in dockerfile


def test_compose_worker_uses_published_agentdb_receipt() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"worker"}
    worker = compose["services"]["worker"]
    assert set(worker["environment"]) == {
        "COGIT_AGENTDB_URL",
        "COGIT_AGENTDB_API_VERSION",
        "COGIT_AGENTDB_INSTALLATION_ID",
        "COGIT_AGENTDB_POOL_ID",
        "COGIT_AGENTDB_WORKER_TOKEN",
        "COGIT_AGENTDB_APPROVAL_DECIDER_ID",
        "COGIT_AGENTDB_COHORT_RECEIPT",
    }
    (receipt,) = worker["volumes"]
    assert receipt["read_only"]
    assert receipt["target"] == worker["environment"]["COGIT_AGENTDB_COHORT_RECEIPT"]
