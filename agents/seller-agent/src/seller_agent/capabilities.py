"""Typed capability composition; authority remains with the Runtime and AgentDB."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from cogit_agent_sdk.types import AgentDescriptor
from cogit_tool_core.providers import (
    HostContext,
    ProviderBundle,
    ProviderSelection,
    prepare_providers,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkBudget(BaseModel):
    """Execution bounds; these limits never grant execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    turns: int = Field(default=60, ge=1, le=500)
    tools: int = Field(default=160, ge=1, le=2000)
    seconds: int = Field(default=900, ge=1, le=7200)


class CapabilityConfiguration(BaseModel):
    """Versioned selection of installed providers, separate from policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1] = 1
    profile: Literal["reference", "workspace"] = "reference"
    workspace_root: str = ""
    workspace_environment: str = "COGIT_WORKSPACE_ROOT"
    tenant_environment: str = "COGIT_TENANT_ID"
    automation_environment: str = "COGIT_BROWSER_ROOT"
    environment_names: list[str] = Field(default_factory=list, max_length=32)
    providers: list[ProviderSelection] = Field(
        default_factory=lambda: list[ProviderSelection](), max_length=32
    )
    budget: WorkBudget = Field(default_factory=WorkBudget)

    @field_validator("version", mode="before")
    @classmethod
    def schema_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("Unsupported capability configuration version")
        return value

    @field_validator("environment_names")
    @classmethod
    def environment_keys(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Duplicate environment reference")
        for value in values:
            cls.environment_key(value)
        return values

    @field_validator(
        "workspace_environment", "tenant_environment", "automation_environment"
    )
    @classmethod
    def environment_key(cls, value: str) -> str:
        if not value.isidentifier() or len(value) > 128:
            raise ValueError("Host environment reference must be an identifier")
        return value


def configuration(descriptor: AgentDescriptor) -> CapabilityConfiguration:
    raw = (descriptor.metadata or {}).get("cogit_tools", {})
    return CapabilityConfiguration.model_validate(raw)


def prepare_capabilities(
    descriptor: AgentDescriptor, settings: CapabilityConfiguration
) -> ProviderBundle | None:
    """Prepare bindings without starting resources or evaluating policy."""
    if not settings.providers:
        return None
    if not descriptor.id:
        raise ValueError("Configured tools require a stable agent id")
    if descriptor.model is None or not descriptor.model.supports_tools:
        raise ValueError("Configured tools require a tool-capable model")
    workspace = os.environ.get(settings.workspace_environment, settings.workspace_root)
    tenant = os.environ.get(settings.tenant_environment, "")
    if not workspace or not Path(workspace).is_absolute():
        raise ValueError("Configured tools require an absolute host workspace")
    if not tenant:
        raise ValueError("Configured tools require a host tenant identity")
    automation = os.environ.get(settings.automation_environment)
    if automation and not Path(automation).is_absolute():
        raise ValueError("Automation root must be absolute")
    environment = {
        name: os.environ[name]
        for name in settings.environment_names
        if name in os.environ
    }
    return prepare_providers(
        settings.providers,
        HostContext(
            workspace=Path(workspace),
            tenant_id=tenant,
            agent_id=descriptor.id,
            automation_root=Path(automation) if automation else None,
            environment=environment,
        ),
    )
