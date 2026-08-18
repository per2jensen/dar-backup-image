"""Regression tests for critical CI workflow ordering and guards."""

from __future__ import annotations

from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).parents[1] / ".github" / "workflows" / "build-test-scan.yml"
)


def test_sbom_scan_checkout_precedes_runner_tool_verification() -> None:
    """The SBOM job checks out helper scripts before any runner-tool check."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    sbom_job = workflow.split("  sbom_vuln_scan:\n", maxsplit=1)[1].split(
        "  summarize:\n", maxsplit=1
    )[0]

    checkout_position = sbom_job.index("- uses: actions/checkout@v7")
    summary_directory_position = sbom_job.index("- name: Prepare summary directory")
    tool_check_position = sbom_job.index("- name: Verify jq is available")

    assert checkout_position < summary_directory_position < tool_check_position


def test_ci_workflow_avoids_network_installation_for_runner_jq() -> None:
    """CI cannot hang on apt while installing a runner-provided command."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "apt-get install -y jq" not in workflow
    assert workflow.count("- name: Verify jq is available") == 2


def test_sbom_summary_requires_checked_out_helper() -> None:
    """The always-run summary is skipped when checkout did not provide its script."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    expected_guard = (
        "if: ${{ always() && "
        "hashFiles('scripts/write_sbom_summary.py') != '' }}"
    )

    assert expected_guard in workflow
