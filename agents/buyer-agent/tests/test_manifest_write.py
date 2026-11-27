"""Public manifest promotion keeps directory access without touching secrets."""

from __future__ import annotations

import ctypes
import os
import stat
from pathlib import Path

import pytest
import yaml

from buyer_agent_setup import write_manifest
from buyer_agent_setup.errors import SetupError


def test_manifest_replacement_keeps_content_and_cleans_staging(tmp_path: Path) -> None:
    path = tmp_path / "cogit.yaml"
    path.write_text("id: before\n", encoding="utf-8")
    secret = tmp_path / ".env"
    secret.write_bytes(b"fixture-only-secret")
    mode = stat.S_IMODE(secret.stat().st_mode)
    write_manifest(path, {"id": "after"})
    assert yaml.safe_load(path.read_bytes()) == {"id": "after"}
    assert sorted(item.name for item in tmp_path.iterdir()) == [".env", "cogit.yaml"]
    assert secret.read_bytes() == b"fixture-only-secret"
    assert stat.S_IMODE(secret.stat().st_mode) == mode


def test_failed_promotion_preserves_prior_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cogit.yaml"
    path.write_bytes(b"id: before\n")

    def fail(source: Path, target: Path) -> None:
        raise PermissionError("fixture failure")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(SetupError, match="Could not write"):
        write_manifest(path, {"id": "after"})
    assert path.read_bytes() == b"id: before\n"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode semantics")
def test_posix_manifest_permissions_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "cogit.yaml"
    path.write_bytes(b"id: before\n")
    path.chmod(0o640)
    write_manifest(path, {"id": "after"})
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL inheritance")
def test_windows_manifest_replacement_inherits_directory_acl(tmp_path: Path) -> None:
    path = tmp_path / "cogit.yaml"
    write_manifest(path, {"id": "after"})
    size = ctypes.c_ulong()
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.GetFileSecurityW(str(path), 4, None, 0, ctypes.byref(size))
    descriptor = ctypes.create_string_buffer(size.value)
    assert api.GetFileSecurityW(str(path), 4, descriptor, size, ctypes.byref(size))
    control = ctypes.c_ushort()
    revision = ctypes.c_ulong()
    assert api.GetSecurityDescriptorControl(
        descriptor, ctypes.byref(control), ctypes.byref(revision)
    )
    assert not control.value & 0x1000  # SE_DACL_PROTECTED
