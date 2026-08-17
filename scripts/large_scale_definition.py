#!/usr/bin/env python3
"""Validate effective options used by the large-scale backup definition."""

from __future__ import annotations

import argparse
import logging
import re
import shlex
from typing import Sequence


LOGGER = logging.getLogger(__name__)
SLICE_SIZE_PATTERN = re.compile(r"^[1-9][0-9]*[kMGTEZY]$")
SLICE_OPTIONS = {"-s", "--slice"}


def validate_slice_size(value: str) -> str:
    """Validate a large-scale slice size with an explicit DAR unit.

    Args:
        value: Candidate slice size such as ``10G``.

    Returns:
        The unchanged validated slice size.

    Raises:
        ValueError: If the value is empty, unitless, or malformed.
    """
    if not isinstance(value, str) or not SLICE_SIZE_PATTERN.fullmatch(value):
        raise ValueError(
            f"slice size {value!r} must be a positive integer with an explicit "
            "DAR unit (k, M, G, T, E, Z, or Y), for example '10G'"
        )
    return value


def _definition_slice_sizes(definition: str) -> list[str]:
    """Extract slice sizes declared in a DAR backup definition.

    Args:
        definition: Complete line-oriented backup-definition content.

    Returns:
        Slice-size values in declaration order.

    Raises:
        ValueError: If the definition or a slice declaration is malformed.
    """
    if not isinstance(definition, str):
        raise ValueError("definition must be a string")

    values: list[str] = []
    for line_number, line in enumerate(definition.splitlines(), start=1):
        try:
            tokens = shlex.split(line, comments=True, posix=True)
        except ValueError as error:
            raise ValueError(
                f"backup definition line {line_number} is malformed: {error}"
            ) from error
        if not tokens:
            continue
        option = tokens[0]
        if option in SLICE_OPTIONS:
            if len(tokens) != 2:
                raise ValueError(
                    f"backup definition line {line_number} must provide exactly "
                    f"one value after {option}"
                )
            values.append(tokens[1])
            continue
        if option.startswith("--slice="):
            if len(tokens) != 1:
                raise ValueError(
                    f"backup definition line {line_number} contains unexpected "
                    "text after --slice=VALUE"
                )
            values.append(option.removeprefix("--slice="))
            continue
        if option.startswith("-s") and not option.startswith("--"):
            if len(tokens) != 1:
                raise ValueError(
                    f"backup definition line {line_number} contains unexpected "
                    "text after -sVALUE"
                )
            values.append(option.removeprefix("-s"))
    return values


def resolve_slice_size(definition: str, fallback: str) -> tuple[str, str]:
    """Resolve and validate the effective large-scale slice size.

    Args:
        definition: Complete backup-definition content.
        fallback: Value supplied through ``--slice`` when the definition omits it.

    Returns:
        A ``(source, value)`` tuple where source is ``definition`` or ``fallback``.

    Raises:
        ValueError: If slice declarations are missing values, duplicated, or invalid.
    """
    values = _definition_slice_sizes(definition)
    if len(values) > 1:
        raise ValueError("backup definition must contain at most one slice option")
    if values:
        return "definition", validate_slice_size(values[0])
    return "fallback", validate_slice_size(fallback)


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--fallback", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Validate the effective slice size and print its source and value.

    Args:
        arguments: Optional command-line arguments, excluding the program name.

    Returns:
        Zero for a valid configuration or two for invalid input.
    """
    parsed = _build_parser().parse_args(arguments)
    try:
        source, value = resolve_slice_size(parsed.definition, parsed.fallback)
    except ValueError as error:
        LOGGER.error("Invalid large-scale slice configuration: %s", error)
        return 2
    print(f"{source}\t{value}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
