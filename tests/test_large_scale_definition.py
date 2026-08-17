"""Tests for defensive large-scale backup-definition validation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "large_scale_definition.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "large_scale_definition", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load definition helper from {MODULE_PATH}")
DEFINITION_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(DEFINITION_MODULE)


def test_resolve_slice_size_valid_fallback_returns_explicit_unit() -> None:
    """A valid fallback is selected when the definition omits slicing."""
    source, value = DEFINITION_MODULE.resolve_slice_size("-R /data", "10G")

    assert source == "fallback"
    assert value == "10G"


@pytest.mark.parametrize(
    "value",
    ("1k", "2M", "3G", "4T", "5E", "6Z", "7Y"),
)
def test_validate_slice_size_accepts_documented_dar_units(value: str) -> None:
    """Every documented DAR size unit is accepted explicitly.

    Args:
        value: Valid slice size using one documented suffix.
    """
    assert DEFINITION_MODULE.validate_slice_size(value) == value


@pytest.mark.parametrize(
    "declaration",
    ("-s 20G", "-s20G", "--slice 20G", "--slice=20G"),
)
def test_resolve_slice_size_definition_forms_override_fallback(
    declaration: str,
) -> None:
    """Every supported definition syntax supplies the effective slice size.

    Args:
        declaration: Short or long DAR slice declaration.
    """
    source, value = DEFINITION_MODULE.resolve_slice_size(
        f"-R /data\n{declaration}", "invalid-ignored-fallback"
    )

    assert source == "definition"
    assert value == "20G"


@pytest.mark.parametrize(
    "invalid_value",
    ("10", "0G", "10g", "10GB", "1P", "-1G", ""),
)
def test_resolve_slice_size_invalid_value_raises_value_error(
    invalid_value: str,
) -> None:
    """Unitless and malformed slice sizes are rejected before a backup starts.

    Args:
        invalid_value: Slice-size value that violates the harness contract.
    """
    with pytest.raises(ValueError, match="explicit DAR unit"):
        DEFINITION_MODULE.resolve_slice_size("-R /data", invalid_value)


def test_resolve_slice_size_unitless_definition_value_raises_value_error() -> None:
    """A custom definition cannot bypass explicit-unit validation."""
    with pytest.raises(ValueError, match="explicit DAR unit"):
        DEFINITION_MODULE.resolve_slice_size("-R /data\n-s 10", "10G")


def test_resolve_slice_size_duplicate_definition_options_raise_value_error() -> None:
    """Conflicting short and long slice declarations fail fast."""
    definition = "-R /data\n-s 10G\n--slice 20G"

    with pytest.raises(ValueError, match="at most one slice option"):
        DEFINITION_MODULE.resolve_slice_size(definition, "30G")


def test_resolve_slice_size_missing_definition_value_raises_value_error() -> None:
    """A slice option without its required value fails clearly."""
    with pytest.raises(ValueError, match="exactly one value"):
        DEFINITION_MODULE.resolve_slice_size("-R /data\n-s", "10G")
