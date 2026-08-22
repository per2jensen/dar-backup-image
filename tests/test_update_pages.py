"""Regression tests for generated documentation-page release selection."""

from scripts.update_pages import ANY_VERSION_RE, RELEASE_RE


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
