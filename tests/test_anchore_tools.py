# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for pinned Anchore tool installation helpers."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "anchore_tools.py"
MODULE_SPEC = importlib.util.spec_from_file_location("anchore_tools", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load Anchore tool helper from {MODULE_PATH}")
ANCHORE_TOOLS = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(ANCHORE_TOOLS)


class _RetryHandler(BaseHTTPRequestHandler):
    """Serve one transient failure followed by a successful response."""

    request_count: ClassVar[int] = 0
    response_body: ClassVar[bytes] = b"downloaded"

    def do_GET(self) -> None:
        """Respond to a test download request."""
        type(self).request_count += 1
        if type(self).request_count == 1:
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(type(self).response_body)))
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress HTTP-server diagnostics during tests.

        Args:
            format: Server log format string.
            args: Values for the log format string.
        """


def _release_archive(tool: str, version: str) -> bytes:
    """Build a small executable release archive for installation tests.

    Args:
        tool: Executable basename.
        version: Version text reported by the executable.

    Returns:
        In-memory gzip-compressed tar archive.
    """
    executable = f"#!/bin/sh\nprintf 'Version: {version}\\n'\n".encode("utf-8")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as release:
        member = tarfile.TarInfo(name=tool)
        member.mode = 0o755
        member.size = len(executable)
        release.addfile(member, io.BytesIO(executable))
    return archive.getvalue()


def test_load_version_pins_valid_file_returns_both_tools(tmp_path: Path) -> None:
    """A complete version file produces validated tool pins.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    version_file = tmp_path / "versions.env"
    version_file.write_text(
        "SYFT_VERSION=v1.51.0\nGRYPE_VERSION=v0.117.0\n",
        encoding="utf-8",
    )

    pins = ANCHORE_TOOLS.load_version_pins(version_file)

    assert pins == {"syft": "v1.51.0", "grype": "v0.117.0"}


def test_load_version_pins_invalid_version_raises_value_error(tmp_path: Path) -> None:
    """A mutable latest value is rejected instead of weakening reproducibility.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    version_file = tmp_path / "versions.env"
    version_file.write_text(
        "SYFT_VERSION=latest\nGRYPE_VERSION=v0.117.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid SYFT_VERSION"):
        ANCHORE_TOOLS.load_version_pins(version_file)


def test_download_bytes_transient_503_retries_and_succeeds() -> None:
    """A real local HTTP 503 is retried before returning the response body."""
    _RetryHandler.request_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RetryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        content = ANCHORE_TOOLS.download_bytes(
            f"http://{host}:{port}/asset",
            attempts=2,
            base_delay_seconds=0,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert content == _RetryHandler.response_body
    assert _RetryHandler.request_count == 2


def test_install_archive_valid_checksum_installs_reported_version(
    tmp_path: Path,
) -> None:
    """A verified archive is installed atomically as an executable.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    archive_name = "syft_1.51.0_linux_amd64.tar.gz"
    archive = _release_archive("syft", "1.51.0")
    checksum = hashlib.sha256(archive).hexdigest()
    checksums = f"{checksum}  {archive_name}\n".encode("utf-8")

    installed = ANCHORE_TOOLS.install_archive(
        "syft",
        "v1.51.0",
        archive,
        checksums,
        archive_name,
        tmp_path / "bin",
    )

    assert installed.is_file()
    assert installed.stat().st_mode & 0o111
    assert ANCHORE_TOOLS._binary_version(installed) == "v1.51.0"


def test_install_archive_wrong_checksum_does_not_create_binary(
    tmp_path: Path,
) -> None:
    """A checksum mismatch fails before replacing or creating an executable.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    archive_name = "grype_0.117.0_linux_amd64.tar.gz"
    archive = _release_archive("grype", "0.117.0")
    checksums = f"{'0' * 64}  {archive_name}\n".encode("utf-8")
    bin_dir = tmp_path / "bin"

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ANCHORE_TOOLS.install_archive(
            "grype",
            "v0.117.0",
            archive,
            checksums,
            archive_name,
            bin_dir,
        )

    assert not (bin_dir / "grype").exists()


def test_available_updates_newer_release_returns_upgrade_message() -> None:
    """A newer stable release is reported with both version numbers."""
    updates = ANCHORE_TOOLS.available_updates(
        {"syft": "v1.50.0", "grype": "v0.117.0"},
        {"syft": "v1.51.0", "grype": "v0.117.0"},
    )

    assert updates == ["syft: pinned v1.50.0, latest v1.51.0"]


def test_available_updates_current_releases_returns_empty_list() -> None:
    """Current stable release pins do not create a false update reminder."""
    updates = ANCHORE_TOOLS.available_updates(
        {"syft": "v1.51.0", "grype": "v0.117.0"},
        {"syft": "v1.51.0", "grype": "v0.117.0"},
    )

    assert updates == []
