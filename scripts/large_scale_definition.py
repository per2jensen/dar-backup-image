#!/usr/bin/env python3
"""Validate effective options used by the large-scale backup definition."""

from __future__ import annotations

import argparse
import logging
import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Sequence


LOGGER = logging.getLogger(__name__)
SLICE_SIZE_PATTERN = re.compile(r"^[1-9][0-9]*[kMGTEZY]$")
SLICE_UNIT_MULTIPLIERS = {
    "k": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
    "E": 1024**6,
    "Z": 1024**7,
    "Y": 1024**8,
}
SLICE_OPTIONS = {"-s", "--slice"}
ROOT_OPTIONS = {"-R", "--fs-root"}
INCLUDE_PATH_OPTIONS = {"-g", "--go-into"}
PRUNE_PATH_OPTIONS = {"-P", "--prune"}
ORDERED_MASK_OPTIONS = {"-am", "--alter=mask"}
CACHE_TAGGING_OPTION = "--cache-directory-tagging"
UNSUPPORTED_SELECTION_OPTIONS = {
    "-I",
    "--include",
    "-X",
    "--exclude",
    "-[",
    "--include-from-file",
    "-]",
    "--exclude-from-file",
    "-ar",
    "--alter=regex",
    "-ag",
    "--alter=glob",
    "-an",
    "--alter=no-case",
    "-acase",
    "--alter=case",
    "-M",
    "--mount-points",
    "--no-mount-points",
}
UNSUPPORTED_SELECTION_PREFIXES = (
    "--include=",
    "--exclude=",
    "--include-from-file=",
    "--exclude-from-file=",
    "--mount-points=",
)
GLOB_CHARACTERS = frozenset("*?[")


@dataclass(frozen=True)
class DefinitionSelection:
    """Constrained path-selection contract for the large-scale harness.

    Args:
        root: Absolute DAR filesystem root from the single ``-R`` option.
        include_paths: Literal relative directory or file paths supplied by ``-g``.
        prune_paths: Literal relative subtrees or files supplied by ``-P``.
        ordered_masks: Whether the definition enables simple ``-am`` ordering.
        cache_directory_tagging: Whether valid cache-tagged directories are excluded.
    """

    root: str
    include_paths: tuple[str, ...]
    prune_paths: tuple[str, ...]
    ordered_masks: bool
    cache_directory_tagging: bool


def _definition_lines(definition: str) -> list[tuple[int, list[str]]]:
    """Tokenize non-empty definition lines with shell-compatible quoting.

    Args:
        definition: Complete line-oriented DAR backup definition.

    Returns:
        Line numbers and token lists for non-empty, non-comment lines.

    Raises:
        ValueError: If the definition is not text or contains malformed quoting.
    """
    if not isinstance(definition, str):
        raise ValueError("definition must be a string")

    parsed_lines: list[tuple[int, list[str]]] = []
    for line_number, line in enumerate(definition.splitlines(), start=1):
        try:
            tokens = shlex.split(line, comments=True, posix=True)
        except ValueError as error:
            raise ValueError(
                f"backup definition line {line_number} is malformed: {error}"
            ) from error
        if tokens:
            parsed_lines.append((line_number, tokens))
    return parsed_lines


def _literal_relative_path(value: str, option: str, line_number: int) -> str:
    """Validate and normalize one literal path under the DAR root.

    Args:
        value: Path argument supplied by the definition.
        option: Definition option that introduced the path.
        line_number: One-based definition line number for diagnostics.

    Returns:
        Normalized POSIX relative path.

    Raises:
        ValueError: If the path is empty, absolute, escaping, or contains a glob.
    """
    if not value or "\x00" in value:
        raise ValueError(
            f"backup definition line {line_number} has an empty {option} path"
        )
    if any(character in value for character in GLOB_CHARACTERS):
        raise ValueError(
            f"backup definition line {line_number} uses a wildcard in {option}; "
            "the large-scale harness accepts literal -g/-P paths only"
        )

    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError(
            f"backup definition line {line_number} requires a relative {option} "
            f"path beneath -R, got {value!r}"
        )
    if ".." in path.parts:
        raise ValueError(
            f"backup definition line {line_number} must not escape -R with '..': "
            f"{value!r}"
        )
    normalized = str(path)
    if normalized in {"", "."} and option in PRUNE_PATH_OPTIONS:
        raise ValueError(
            f"backup definition line {line_number} must not prune the complete -R root"
        )
    return normalized


def _is_unsupported_selection_option(option: str) -> bool:
    """Return whether an option exceeds the harness selection contract.

    Args:
        option: First token from a definition line.

    Returns:
        ``True`` for unsupported selection modes or attached selection values.
    """
    if option in UNSUPPORTED_SELECTION_OPTIONS:
        return True
    if option.startswith(UNSUPPORTED_SELECTION_PREFIXES):
        return True
    if option.startswith(("--go-into=", "--prune=", "--fs-root=")):
        return True
    if option.startswith(("-g", "-P", "-R")) and option not in {
        "-g",
        "-P",
        "-R",
    }:
        return True
    if option.startswith(("-I", "-X", "-M")) and option not in {
        "-I",
        "-X",
        "-M",
    }:
        return True
    return False


def parse_selection_contract(definition: str) -> DefinitionSelection:
    """Parse the deliberately narrow large-scale selection contract.

    Args:
        definition: Complete user-supplied backup definition before primer injection.

    Returns:
        Validated literal root, inclusion, pruning, and cache-tag settings.

    Raises:
        ValueError: If required paths are missing, selection syntax is malformed,
            or the definition requests unsupported DAR selection behavior.
    """
    roots: list[str] = []
    include_paths: list[str] = []
    prune_paths: list[str] = []
    ordered_masks = False
    cache_directory_tagging = False
    selection_started = False
    prune_started = False

    for line_number, tokens in _definition_lines(definition):
        option = tokens[0]
        if option in ROOT_OPTIONS:
            if len(tokens) != 2:
                raise ValueError(
                    f"backup definition line {line_number} must provide exactly "
                    f"one value after {option}"
                )
            roots.append(tokens[1])
            continue
        if option in ORDERED_MASK_OPTIONS:
            if len(tokens) != 1:
                raise ValueError(
                    f"backup definition line {line_number} contains unexpected "
                    f"text after {option}"
                )
            if ordered_masks:
                raise ValueError("backup definition may enable -am at most once")
            if selection_started:
                raise ValueError(
                    "-am must appear before every -g and -P option in the "
                    "large-scale harness contract"
                )
            ordered_masks = True
            continue
        if option == CACHE_TAGGING_OPTION:
            if len(tokens) != 1:
                raise ValueError(
                    f"backup definition line {line_number} contains unexpected "
                    f"text after {CACHE_TAGGING_OPTION}"
                )
            if cache_directory_tagging:
                raise ValueError(
                    f"backup definition may specify {CACHE_TAGGING_OPTION} at most once"
                )
            cache_directory_tagging = True
            continue
        if option in INCLUDE_PATH_OPTIONS:
            if len(tokens) != 2:
                raise ValueError(
                    f"backup definition line {line_number} must provide exactly "
                    f"one value after {option}"
                )
            if ordered_masks and prune_started:
                raise ValueError(
                    "ordered -am definitions must place every user -g before every "
                    "user -P; ordered re-inclusion is outside the harness contract"
                )
            selection_started = True
            include_paths.append(
                _literal_relative_path(tokens[1], option, line_number)
            )
            continue
        if option in PRUNE_PATH_OPTIONS:
            if len(tokens) != 2:
                raise ValueError(
                    f"backup definition line {line_number} must provide exactly "
                    f"one value after {option}"
                )
            selection_started = True
            prune_started = True
            prune_paths.append(_literal_relative_path(tokens[1], option, line_number))
            continue
        if _is_unsupported_selection_option(option):
            raise ValueError(
                f"backup definition line {line_number} uses unsupported selection "
                f"option {option!r}; the large-scale harness accepts only literal "
                "-g/-P paths"
            )

    if len(roots) != 1:
        raise ValueError(
            f"backup definition must contain exactly one -R/--fs-root option, found {len(roots)}"
        )
    root = roots[0]
    if not PurePosixPath(root).is_absolute():
        raise ValueError(f"backup definition -R path must be absolute, got {root!r}")
    if not include_paths:
        raise ValueError(
            "backup definition must contain at least one literal -g/--go-into path"
        )

    return DefinitionSelection(
        root=root,
        include_paths=tuple(dict.fromkeys(include_paths)),
        prune_paths=tuple(dict.fromkeys(prune_paths)),
        ordered_masks=ordered_masks,
        cache_directory_tagging=cache_directory_tagging,
    )


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


def slice_size_to_bytes(value: str) -> int:
    """Convert one validated DAR slice size to an exact byte count.

    Args:
        value: Slice size with an explicit DAR binary unit.

    Returns:
        Exact number of bytes represented by the value.

    Raises:
        ValueError: If the value is empty, unitless, or malformed.
    """
    validated = validate_slice_size(value)
    magnitude = int(validated[:-1])
    unit = validated[-1]
    return magnitude * SLICE_UNIT_MULTIPLIERS[unit]


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
    parser.add_argument("--fallback")
    parser.add_argument(
        "--slice-bytes",
        action="store_true",
        help="validate --fallback as a slice size and print exact bytes",
    )
    parser.add_argument(
        "--selection-root",
        action="store_true",
        help="validate the harness selection contract and print its -R root",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Validate one definition contract and print its requested result.

    Args:
        arguments: Optional command-line arguments, excluding the program name.

    Returns:
        Zero for a valid configuration or two for invalid input.
    """
    parsed = _build_parser().parse_args(arguments)
    if parsed.slice_bytes:
        if parsed.fallback is None:
            LOGGER.error("Invalid large-scale slice configuration: --fallback is required")
            return 2
        try:
            print(slice_size_to_bytes(parsed.fallback))
        except ValueError as error:
            LOGGER.error("Invalid large-scale slice configuration: %s", error)
            return 2
        return 0
    if parsed.selection_root:
        try:
            selection = parse_selection_contract(parsed.definition)
        except ValueError as error:
            LOGGER.error("Invalid large-scale selection configuration: %s", error)
            return 2
        print(selection.root)
        return 0
    if parsed.fallback is None:
        LOGGER.error("Invalid large-scale slice configuration: --fallback is required")
        return 2
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
