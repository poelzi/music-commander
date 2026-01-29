"""Jinja2 template rendering for view path generation."""

from __future__ import annotations

import math

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError


def _round_to(value: float | int | str | None, n: int | float) -> float:
    """Round a value to the nearest multiple of n.

    Example: ``{{ bpm | round_to(5) }}`` rounds 143 → 145.
    """
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (ValueError, TypeError):
        return 0.0
    if n == 0:
        return v
    return round(v / n) * n


def _make_env() -> Environment:
    """Create a sandboxed Jinja2 environment for path templates."""
    env = Environment(
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=False,
    )
    env.filters["round_to"] = _round_to
    return env


_env = _make_env()


class TemplateRenderError(Exception):
    """Raised when a path template cannot be rendered."""

    pass


def render_path(template_str: str, metadata: dict[str, str | None]) -> str:
    """Render a Jinja2 path template with track metadata.

    Missing metadata values are replaced with "Unknown".

    Args:
        template_str: Jinja2 template string, e.g. ``{{ genre }}/{{ artist }} - {{ title }}``.
        metadata: Dict of metadata field names to values.

    Returns:
        Rendered path string.

    Raises:
        TemplateRenderError: If the template has syntax errors.
    """
    try:
        template = _env.from_string(template_str)
    except TemplateSyntaxError as e:
        raise TemplateRenderError(f"Invalid template syntax: {e}") from e

    # Fill missing values with "Unknown"
    safe_metadata = {
        k: (v if v is not None and v != "" else "Unknown") for k, v in metadata.items()
    }

    try:
        return template.render(**safe_metadata)
    except UndefinedError as e:
        # Extract variable name from the error and retry with it set to "Unknown"
        # This handles fields not present in metadata dict at all
        var_name = str(e).split("'")[1] if "'" in str(e) else str(e)
        safe_metadata[var_name] = "Unknown"
        try:
            return template.render(**safe_metadata)
        except UndefinedError:
            raise TemplateRenderError(f"Template references unknown variable: {e}") from e


def get_template_variables(template_str: str) -> set[str]:
    """Extract variable names from a Jinja2 template string.

    Args:
        template_str: Jinja2 template string.

    Returns:
        Set of variable names used in the template.
    """
    from jinja2 import meta

    try:
        ast = _env.parse(template_str)
        return meta.find_undeclared_variables(ast)
    except TemplateSyntaxError:
        return set()
