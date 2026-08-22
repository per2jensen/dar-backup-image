"""Regression tests for shared release publication and immutable inputs."""

from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
RELEASE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"
REFRESH_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "image-refresh.yml"
PUBLISH_ACTION = REPOSITORY_ROOT / ".github" / "actions" / "publish-image" / "action.yml"
MAKEFILE = REPOSITORY_ROOT / "Makefile"


def _external_action_references(workflow: str) -> tuple[list[str], list[str]]:
    """Extract external action references and their complete YAML lines.

    Args:
        workflow: GitHub Actions workflow text.

    Returns:
        External action references and their corresponding source lines.
    """
    lines = [
        line
        for line in workflow.splitlines()
        if "uses:" in line and "uses: ./" not in line
    ]
    references: list[str] = []
    for line in lines:
        match = re.search(r"uses:\s+([^\s#]+)", line)
        if match is None:
            raise ValueError(f"invalid action reference line: {line!r}")
        references.append(match.group(1))
    return references, lines


def test_release_workflow_uses_shared_publisher_before_housekeeping() -> None:
    """The release delegates its publication transaction before Git writes."""
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    publisher = workflow.index("uses: ./source/.github/actions/publish-image")
    badge = workflow.index("- name: Publish failure badge")
    housekeeping = workflow.index("- name: Housekeeping ")

    assert publisher < badge < housekeeping
    assert "steps.publish_image.outputs.digest" in workflow
    assert "steps.publish_image.outputs.rekor_url" in workflow


def test_publish_action_rolls_back_only_an_unverified_candidate() -> None:
    """Rollback is gated on a pushed candidate that failed remote verification."""
    action = PUBLISH_ACTION.read_text(encoding="utf-8")

    assert "steps.publish.outputs.candidate_push_attempted == 'true'" in action
    assert "steps.publish.outputs.candidate_verified != 'true'" in action
    assert '--tag "${{ inputs.version }}"' in action
    assert '--tag "latest"' not in action


def test_shared_publisher_always_removes_docker_credentials() -> None:
    """Release and refresh inherit an always-run best-effort Docker logout."""
    action = PUBLISH_ACTION.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    refresh = REFRESH_WORKFLOW.read_text(encoding="utf-8")

    cleanup = action.index("- name: Remove Docker Hub credentials")
    report_failure = action.index("- name: Report publication failure")
    assert cleanup < report_failure
    assert "if: always()" in action[cleanup:]
    assert "continue-on-error: true" in action[cleanup:]
    assert "if ! docker logout; then" in action[cleanup:]
    assert "uses: ./source/.github/actions/publish-image" in release
    assert "uses: ./orchestration/.github/actions/publish-image" in refresh


def test_publication_workflows_share_one_concurrency_group() -> None:
    """Release and refresh jobs cannot concurrently mutate Docker Hub latest."""
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    refresh = REFRESH_WORKFLOW.read_text(encoding="utf-8")

    expected = "group: dar-backup-dockerhub-publication"
    assert expected in release
    assert expected in refresh
    assert "cancel-in-progress: false" in release
    assert "cancel-in-progress: false" in refresh


def test_publication_workflows_pin_external_actions_to_full_shas() -> None:
    """Every external action reference is immutable and documents its version."""
    for path in (RELEASE_WORKFLOW, REFRESH_WORKFLOW):
        workflow = path.read_text(encoding="utf-8")
        references, lines = _external_action_references(workflow)

        assert references
        assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref) for ref in references)
        assert all(re.search(r"# v\d+(?:\.\d+)*$", line) for line in lines)


def test_release_workflow_keeps_source_and_housekeeping_checkouts_separate() -> None:
    """Build inputs and generated release records use distinct checkout paths."""
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "ref: ${{ github.sha }}\n          fetch-depth: 0\n          path: source" in workflow
    assert "ref: main\n          fetch-depth: 0\n          path: housekeeping" in workflow
    assert 'git tag -a "v${{ env.FINAL_VERSION }}"' in workflow
    assert '              "${SOURCE_SHA}"' in workflow


def test_refresh_workflow_keeps_revisions_in_separate_checkouts() -> None:
    """Refresh never overlays orchestration onto recorded application source."""
    workflow = REFRESH_WORKFLOW.read_text(encoding="utf-8")

    assert "path: orchestration" in workflow
    assert "ref: ${{ env.APPLICATION_SHA }}" in workflow
    assert "path: source" in workflow
    assert "path: housekeeping" in workflow
    assert "git checkout main -- Makefile" not in workflow
    assert "uses: ./orchestration/.github/actions/publish-image" in workflow
    assert "working-directory: source\n        run: |\n          make" in workflow
    assert "orchestration/scripts/finalize_refresh_image.sh" in workflow


def test_refresh_workflow_selects_version_from_build_history_only() -> None:
    """Refresh derives its base and source from the same latest history record."""
    workflow = REFRESH_WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/select_refresh_source.py" in workflow
    assert "--history doc/build-history.json" in workflow
    assert "APPLICATION_SHA=$(jq -er '.application_sha'" in workflow
    assert "REBUILD_VERSION=$(jq -er '.next_refresh_version'" in workflow
    assert "TAG_MATCHES_SOURCE=$(jq -er '.tag_matches_source | tostring'" in workflow
    assert 'ref: ${{ env.APPLICATION_SHA }}' in workflow
    assert 'ref: v${{ env.BASE_TAG }}' not in workflow
    assert "IMAGE_VERSION" not in workflow


def test_publication_failure_badges_use_retrying_helper() -> None:
    """Both workflows persist a failed publication badge through the safe helper."""
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    refresh = REFRESH_WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/publish_cosign_badge.sh" in release
    assert "cosign badge: publication failed" in release
    assert "scripts/publish_cosign_badge.sh" in refresh
    assert "cosign badge: refresh" in refresh
    assert "if: failure() && steps.publish_image.outcome == 'failure'" in refresh


def test_refresh_housekeeping_uses_atomic_metadata_tag_transaction() -> None:
    """Refresh tags the metadata commit and atomically publishes both refs."""
    workflow = REFRESH_WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/commit_refresh_housekeeping.sh" in workflow
    assert '"${APPLICATION_SHA}"' in workflow
    assert '"${DIGEST}"' in workflow
    assert 'git tag -a "v${{ env.REBUILD_VERSION }}"' not in workflow
    assert 'git push origin "refs/tags/v${{ env.REBUILD_VERSION }}"' not in workflow


def test_make_publication_targets_apply_explicit_version_policies() -> None:
    """Release and refresh finalization cannot use the generic dev default."""
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert "final: check-release-image-version" in makefile
    assert "final-noscan: check-release-image-version" in makefile
    assert "push: check-release-image-version" in makefile
    assert "refresh-final-noscan: check-refresh-image-version" in makefile
