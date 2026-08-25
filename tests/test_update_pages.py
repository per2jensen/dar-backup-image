"""Regression tests for generated documentation-page release selection."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "update_pages.py"
MODULE_SPEC = importlib.util.spec_from_file_location("update_pages", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load page generator from {MODULE_PATH}")
UPDATE_PAGES_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = UPDATE_PAGES_MODULE
MODULE_SPEC.loader.exec_module(UPDATE_PAGES_MODULE)
ANY_VERSION_RE = UPDATE_PAGES_MODULE.ANY_VERSION_RE
RELEASE_RE = UPDATE_PAGES_MODULE.RELEASE_RE
render_row = UPDATE_PAGES_MODULE.render_row


def test_release_filter_accepts_stable_and_release_candidate_tags() -> None:
    """Stable, historical four-part, and RC tags appear as releases."""
    for tag in ("1.0.0", "0.5.25.1", "1.0.0-rc1", "2.3.4-rc12"):
        assert RELEASE_RE.fullmatch(tag)


def test_release_filter_rejects_refresh_and_invalid_prerelease_tags() -> None:
    """Numeric refreshes and malformed RC tags do not appear as releases."""
    for tag in ("1.0.0-1", "1.0.0-rc0", "1.0.0-rc1-1", "dev"):
        assert not RELEASE_RE.fullmatch(tag)


def test_all_version_filter_accepts_release_and_refresh_tags() -> None:
    """The inclusive page mode accepts releases and stable refreshes."""
    for tag in ("1.0.0", "0.5.25.1", "1.0.0-rc1", "1.0.0-2"):
        assert ANY_VERSION_RE.fullmatch(tag)


def test_all_version_filter_rejects_prerelease_refresh_tags() -> None:
    """The page generator never treats an RC numeric suffix as a refresh."""
    for tag in ("1.0.0-rc1-1", "1.0.0-0", "1.0", "latest"):
        assert not ANY_VERSION_RE.fullmatch(tag)


def test_latest_release_row_uses_unambiguous_badge() -> None:
    """Newest release row is distinguished from the mutable latest image tag."""
    row = render_row({"tag": "1.0.0"}, is_latest=True)

    assert "Latest release" in row


def test_older_release_row_omits_latest_badge() -> None:
    """Older release rows do not receive the newest-release badge."""
    row = render_row({"tag": "0.9.0"}, is_latest=False)

    assert "Latest release" not in row
