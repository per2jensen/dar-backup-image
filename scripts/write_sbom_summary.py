#!/usr/bin/env python3
"""Write a resilient CI summary from CycloneDX and Grype JSON files."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


LOGGER = logging.getLogger("sbom-summary")
SEVERITIES = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")


def _load_json_object(path: Path, description: str) -> dict[str, Any]:
    """Load a required regular JSON object.

    Args:
        path: JSON file to read.
        description: Human-readable artifact name for errors.

    Returns:
        Parsed JSON object.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the file is absent, unsafe, malformed, or not an object.
    """
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{description} is missing or unsafe: {path}")
    try:
        content: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{description} is not valid JSON: {path}") from error
    if not isinstance(content, dict):
        raise ValueError(f"{description} must contain a JSON object: {path}")
    return content


def build_summary(image: str, sbom_path: Path, grype_path: Path) -> dict[str, Any]:
    """Build a complete or explicitly unavailable scan summary.

    Args:
        image: Exact scanned image reference.
        sbom_path: CycloneDX JSON path.
        grype_path: Grype JSON results path.

    Returns:
        Stable CI summary object that records success or the missing prerequisite.

    Raises:
        ValueError: If the image reference is empty.
    """
    if not image.strip():
        raise ValueError("Image reference cannot be empty")
    try:
        sbom = _load_json_object(sbom_path, "CycloneDX SBOM")
        grype = _load_json_object(grype_path, "Grype results")
        components = sbom.get("components")
        matches = grype.get("matches")
        if not isinstance(components, list):
            raise ValueError("CycloneDX SBOM is missing its components list")
        if not isinstance(matches, list):
            raise ValueError("Grype results are missing their matches list")
    except (OSError, ValueError) as error:
        LOGGER.warning("SBOM vulnerability summary unavailable: %s", error)
        return {
            "sbom_vuln_scan": {
                "image": image,
                "status": "unavailable",
                "reason": str(error),
                "components": None,
                "vulnerabilities": None,
            }
        }

    severity_counts = {severity.lower(): 0 for severity in SEVERITIES}
    for match in matches:
        vulnerability = match.get("vulnerability") if isinstance(match, dict) else None
        severity = (
            vulnerability.get("severity")
            if isinstance(vulnerability, dict)
            else None
        )
        key = severity.lower() if isinstance(severity, str) else "unknown"
        if key not in severity_counts:
            key = "unknown"
        severity_counts[key] += 1
    return {
        "sbom_vuln_scan": {
            "image": image,
            "status": "complete",
            "reason": None,
            "components": len(components),
            "vulnerabilities": {
                "total": len(matches),
                "by_severity": severity_counts,
            },
        }
    }


def write_json_atomic(path: Path, content: dict[str, Any]) -> None:
    """Atomically write a formatted JSON object.

    Args:
        path: Destination file.
        content: Serializable JSON object.

    Raises:
        OSError: If the destination cannot be created or replaced.
        TypeError: If content is not JSON serializable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, raw_temporary_path = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        temporary_path = Path(raw_temporary_path)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(content, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def render_markdown(summary: dict[str, Any]) -> str:
    """Render a concise GitHub job summary.

    Args:
        summary: Object returned by :func:`build_summary`.

    Returns:
        Markdown summary text.

    Raises:
        ValueError: If the summary has an unexpected structure.
    """
    scan = summary.get("sbom_vuln_scan")
    if not isinstance(scan, dict):
        raise ValueError("SBOM scan summary is malformed")
    lines = ["### SBOM / Vulnerabilities", f"- Image: {scan.get('image', 'unknown')}"]
    if scan.get("status") != "complete":
        lines.append("- Status: unavailable")
        lines.append(f"- Reason: {scan.get('reason', 'unknown')}")
        return "\n".join(lines)
    vulnerabilities = scan.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise ValueError("Completed SBOM scan lacks vulnerability results")
    lines.append(f"- Components: {scan.get('components')}")
    lines.append(f"- Vulnerabilities (all severities): {vulnerabilities.get('total')}")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--grype-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Write JSON and optional Markdown summaries without masking prior failures.

    Args:
        arguments: Optional command arguments excluding the executable name.

    Returns:
        Zero after writing a complete or explicitly unavailable summary.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parsed = _parser().parse_args(arguments)
    try:
        summary = build_summary(parsed.image, parsed.sbom, parsed.grype_results)
        write_json_atomic(parsed.output, summary)
        if parsed.markdown_output is not None:
            markdown = render_markdown(summary)
            with parsed.markdown_output.open("a", encoding="utf-8") as handle:
                handle.write(markdown)
                handle.write("\n")
        return 0
    except (OSError, TypeError, ValueError) as error:
        LOGGER.error("Could not write SBOM summary: %s", error)
        return 2


if __name__ == "__main__":
    sys.exit(main())
