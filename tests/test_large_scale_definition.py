# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for defensive large-scale backup-definition validation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "large_scale_definition.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "large_scale_definition", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load definition helper from {MODULE_PATH}")
DEFINITION_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = DEFINITION_MODULE
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


def test_slice_size_to_bytes_converts_binary_unit_exactly() -> None:
    """A dashboard slice dimension uses exact binary bytes."""
    assert DEFINITION_MODULE.slice_size_to_bytes("10G") == 10 * 1024**3


def test_slice_size_to_bytes_rejects_unitless_value() -> None:
    """A malformed slice value cannot produce misleading telemetry."""
    with pytest.raises(ValueError, match="explicit DAR unit"):
        DEFINITION_MODULE.slice_size_to_bytes("10")


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


def test_parse_selection_contract_literal_prunes_with_spaces_are_preserved() -> None:
    """Quoted literal Steam paths are parsed without shell quote characters."""
    definition = """\
-R /data
-am
--cache-directory-tagging
-g SteamLibrary
-P 'SteamLibrary/steamapps/common/Metro Exodus'
-P "SteamLibrary/steamapps/common/The Witcher 3"
"""

    selection = DEFINITION_MODULE.parse_selection_contract(definition)

    assert selection.root == "/data"
    assert selection.include_paths == ("SteamLibrary",)
    assert selection.prune_paths == (
        "SteamLibrary/steamapps/common/Metro Exodus",
        "SteamLibrary/steamapps/common/The Witcher 3",
    )
    assert selection.ordered_masks is True
    assert selection.cache_directory_tagging is True


def test_parse_selection_contract_duplicate_literal_paths_are_deduplicated() -> None:
    """Repeated identical include and prune paths do not duplicate measurement."""
    definition = """\
-R /data
-g photos
--go-into photos
-P photos/private
--prune photos/private
"""

    selection = DEFINITION_MODULE.parse_selection_contract(definition)

    assert selection.include_paths == ("photos",)
    assert selection.prune_paths == ("photos/private",)


@pytest.mark.parametrize(
    "definition,error_pattern",
    (
        ("-R /data\n-g SteamLibrary\n-P", "exactly one value"),
        ("-R /data\n-g SteamLibrary\n-P /etc", "relative"),
        ("-R /data\n-g SteamLibrary\n-P ../private", "must not escape"),
        ("-R /data\n-g SteamLibrary\n-P 'games/*'", "wildcard"),
        ("-R /data\n-gSteamLibrary", "unsupported selection"),
        ("-R /data\n-g SteamLibrary\n-X '*.tmp'", "unsupported selection"),
        ("-R /data\n-g SteamLibrary\n-ar", "unsupported selection"),
        ("-R /data\n-g SteamLibrary\n-M", "unsupported selection"),
        ("-R /data\n-P SteamLibrary/private", "at least one literal -g"),
        ("-g SteamLibrary", "exactly one -R"),
        ("-R /data\n-R /mnt\n-g SteamLibrary", "exactly one -R"),
    ),
)
def test_parse_selection_contract_invalid_definition_raises_value_error(
    definition: str, error_pattern: str
) -> None:
    """Malformed or unsupported selection definitions fail before traversal.

    Args:
        definition: Invalid constrained backup definition.
        error_pattern: Expected diagnostic fragment.
    """
    with pytest.raises(ValueError, match=error_pattern):
        DEFINITION_MODULE.parse_selection_contract(definition)


def test_parse_selection_contract_ordered_reinclude_raises_value_error() -> None:
    """A user -g after -P cannot introduce unsupported ordered re-inclusion."""
    definition = """\
-R /data
-am
-g SteamLibrary
-P SteamLibrary/private
-g SteamLibrary/private/keep
"""

    with pytest.raises(ValueError, match="ordered re-inclusion"):
        DEFINITION_MODULE.parse_selection_contract(definition)


def test_parse_selection_contract_am_after_path_rule_raises_value_error() -> None:
    """Ordered mode must be declared before path rules to remain unambiguous."""
    definition = "-R /data\n-g SteamLibrary\n-am"

    with pytest.raises(ValueError, match="must appear before"):
        DEFINITION_MODULE.parse_selection_contract(definition)
