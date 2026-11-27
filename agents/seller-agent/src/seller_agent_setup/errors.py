"""Setup diagnostics never include provider settings, validator inputs or causes."""

from pydantic import ValidationError


class SetupError(ValueError):
    """A deliberately safe operator-facing setup diagnostic."""


def diagnostic(error: Exception) -> str:
    if isinstance(error, SetupError):
        return str(error)
    current: BaseException | None = error
    for _ in range(8):
        if isinstance(current, ValidationError):
            details = current.errors(
                include_input=False, include_context=False, include_url=False
            )
            kinds = sorted({str(item["type"]) for item in details})
            return "Configuration validation failed (" + ", ".join(kinds)[:300] + ")"
        current = current.__cause__ if current is not None else None
    return f"Configuration rejected ({type(error).__name__}); manifest was not changed"
