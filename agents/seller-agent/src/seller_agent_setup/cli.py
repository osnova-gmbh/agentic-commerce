"""Installed host composition command for provider selection and validation."""

from __future__ import annotations

import argparse
import json
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from cogit_tool_core.providers import ENTRY_POINT_GROUP

from .errors import SetupError, diagnostic
from .manifest import read_manifest, resolved_manifest, write_manifest


def _select(payload: dict[str, Any], args: argparse.Namespace) -> None:
    metadata = dict(payload.get("metadata") or {})
    settings = dict(metadata.get("cogit_tools") or {})
    if args.providers is not None:
        try:
            if args.providers.stat().st_size > 65536:
                raise SetupError("Provider selection exceeds 64 KiB")
            selection: object = json.loads(args.providers.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SetupError("Cannot read the provider selection JSON") from exc
        if not isinstance(selection, list):
            raise SetupError("Provider selection must be a JSON array")
        settings["providers"] = selection
    if args.workspace is not None:
        settings["workspace_root"] = str(args.workspace.absolute())
    if args.profile is not None:
        settings["profile"] = args.profile
    if settings:
        metadata["cogit_tools"] = settings
        payload["metadata"] = metadata
    if args.model is None and (
        args.context_window is not None
        or args.max_output_tokens is not None
        or args.thinking_level is not None
    ):
        raise SetupError("Model options require an explicit --model selection")
    if args.model is not None:
        if args.context_window is None or args.max_output_tokens is None:
            raise SetupError(
                "Model selection requires --context-window and --max-output-tokens "
                "for canonical spending reservations"
            )
        payload["model"] = {
            "provider": args.model_provider,
            "model": args.model,
            "supports_tools": True,
            "supports_streaming": False,
            "context_window": args.context_window,
            "max_output_tokens": args.max_output_tokens,
        }
        if args.thinking_level is not None:
            payload["model"]["defaults"] = {"thinking_level": args.thinking_level}
        runtime = dict(payload.get("runtime") or {})
        runtime_model = dict(runtime.get("model") or {})
        runtime_model["profile"] = "sdk"
        runtime["model"] = runtime_model
        payload["runtime"] = runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("cogit.yaml"))
    parser.add_argument("--providers", type=Path, help="JSON provider selections")
    parser.add_argument("--workspace", type=Path, help="Host-owned working directory")
    parser.add_argument("--profile", choices=("reference", "workspace"))
    parser.add_argument("--model", help="Tool-capable Runtime model name")
    parser.add_argument("--model-provider", default="openai")
    parser.add_argument(
        "--context-window", type=int, help="Host-reviewed input token bound"
    )
    parser.add_argument(
        "--max-output-tokens", type=int, help="Provider output token limit"
    )
    parser.add_argument(
        "--thinking-level",
        help="Explicit model-supported reasoning level; omitted by default",
    )
    parser.add_argument("--check", action="store_true", help="Check without rewriting")
    parser.add_argument("--list-providers", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.list_providers:
            names = sorted(item.name for item in entry_points(group=ENTRY_POINT_GROUP))
            print(json.dumps(names))
            return 0
        payload = read_manifest(args.manifest)
        _select(payload, args)
        updated = resolved_manifest(payload)
        if args.check:
            if updated != read_manifest(args.manifest):
                raise SetupError("Manifest inventory is stale; run cogit-agent-setup")
        else:
            write_manifest(args.manifest, updated)
        print(
            f"Validated {len(updated['tools'])} tools; "
            "resources and model connections were not started."
        )
        return 0
    except Exception as exc:
        # Third-party prepare/settings errors can contain literal credentials that
        # do not exist in the process environment. Never interpolate those values.
        parser.exit(1, f"Setup failed: {diagnostic(exc)}\n")
