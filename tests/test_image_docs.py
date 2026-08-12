"""Tests for documentation preserved inside the dar-backup image."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
from importlib import metadata as importlib_metadata
import io
import json
import subprocess
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "image_docs.py"
MODULE_SPEC = importlib.util.spec_from_file_location("image_docs", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load image documentation helper from {MODULE_PATH}")
IMAGE_DOCS_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(IMAGE_DOCS_MODULE)
build_documentation_bundle = IMAGE_DOCS_MODULE.build_documentation_bundle
run_docs_command = IMAGE_DOCS_MODULE.run_docs_command


def _distribution_metadata(version: str, description: str) -> bytes:
    """Create valid Core Metadata containing an optional Markdown description.

    Args:
        version: Synthetic dar-backup version.
        description: Long-description payload.

    Returns:
        UTF-8 encoded Core Metadata.
    """
    return (
        "Metadata-Version: 2.4\n"
        "Name: dar-backup\n"
        f"Version: {version}\n"
        "Description-Content-Type: text/markdown\n"
        "Project-URL: Homepage, https://example.invalid/dar-backup\n"
        "\n"
        f"{description}"
    ).encode("utf-8")


def _create_distribution(
    site_packages: Path,
    version: str = "1.1.11",
    description: str = "# dar-backup overview\n\nPreserved metadata documentation.\n",
    include_package_docs: bool = True,
) -> importlib_metadata.Distribution:
    """Create an isolated installed dar-backup distribution with RECORD hashes.

    Args:
        site_packages: Synthetic site-packages directory to populate.
        version: Installed distribution version.
        description: Core Metadata description payload.
        include_package_docs: Whether to include the upcoming documentation tree.

    Returns:
        Discoverable installed distribution object.
    """
    site_packages.mkdir(parents=True, exist_ok=True)
    dist_info = f"dar_backup-{version}.dist-info"
    contents: dict[str, bytes] = {
        f"{dist_info}/METADATA": _distribution_metadata(version, description),
        f"{dist_info}/licenses/LICENSE": b"test license\n",
        "dar_backup/__init__.py": b"",
    }
    if include_package_docs:
        contents.update(
            {
                "dar_backup/doc/getting-started.md": (
                    b"# Getting started\n\nExact package documentation.\n"
                ),
                "dar_backup/doc/restoring-advanced.md": b"# Advanced restoration\n",
            }
        )

    record_rows: list[list[str]] = []
    for relative_path, content in contents.items():
        destination = site_packages / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest())
        encoded_digest = digest.rstrip(b"=").decode("ascii")
        record_rows.append(
            [relative_path, f"sha256={encoded_digest}", str(len(content))]
        )

    record_relative = f"{dist_info}/RECORD"
    record_path = site_packages / record_relative
    record_rows.append([record_relative, "", ""])
    with record_path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(record_rows)

    distributions = list(
        importlib_metadata.distributions(path=[str(site_packages)])
    )
    if len(distributions) != 1:
        raise RuntimeError(
            f"Expected one synthetic distribution, found {len(distributions)}"
        )
    return distributions[0]


def _docker_run(
    image: str, *arguments: str, entrypoint: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the image without mounts and capture text output.

    Args:
        image: Docker image reference under test.
        arguments: Arguments passed after the image reference.
        entrypoint: Optional direct entrypoint override.

    Returns:
        Completed Docker subprocess without an automatic status check.
    """
    command = ["docker", "run", "--rm", "-e", "DAR_BACKUP_CONFIG=/missing"]
    if entrypoint is not None:
        command.extend(["--entrypoint", entrypoint])
    command.extend([image, *arguments])
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_bundle_preserves_every_installed_package_document(
    tmp_path: Path,
) -> None:
    """Bundle generation exposes every document from the installation.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    distribution = _create_distribution(tmp_path / "site-packages")
    output_dir = tmp_path / "bundle"
    image_readme = tmp_path / "image-README.md"
    image_readme.write_text("# Image operating guide\n", encoding="utf-8")

    manifest = build_documentation_bundle(
        distribution=distribution,
        output_dir=output_dir,
        expected_version="1.1.11",
        image_readme_path=image_readme,
    )

    assert (output_dir / "README.md").read_text(encoding="utf-8").startswith(
        "# dar-backup overview"
    )
    assert (output_dir / "doc/getting-started.md").read_text(
        encoding="utf-8"
    ).endswith("Exact package documentation.\n")
    assert (output_dir / "doc/restoring-advanced.md").is_file()
    assert (output_dir / "image/README.md").read_text(encoding="utf-8") == (
        "# Image operating guide\n"
    )
    assert (output_dir / "licenses/LICENSE").is_file()
    assert not (output_dir / "wheel").exists()
    assert {record["source"] for record in manifest["documentation"]} >= {
        f"dar_backup-1.1.11.dist-info/METADATA#Description",
        "dar_backup/doc/getting-started.md",
        "dar_backup/doc/restoring-advanced.md",
        "build-context:README.md",
    }

    stored_manifest = json.loads(
        (output_dir / "MANIFEST.json").read_text(encoding="utf-8")
    )
    assert stored_manifest == manifest
    verification_output = io.StringIO()
    assert run_docs_command(["--verify"], output_dir, verification_output) == 0
    assert "Documentation integrity verified" in verification_output.getvalue()


def test_bundle_without_package_doc_tree_preserves_metadata_manual(
    tmp_path: Path,
) -> None:
    """Current installations remain supported before the package doc tree appears.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    distribution = _create_distribution(
        tmp_path / "site-packages",
        version="1.1.10",
        include_package_docs=False,
    )
    output_dir = tmp_path / "bundle"

    manifest = build_documentation_bundle(
        distribution=distribution,
        output_dir=output_dir,
        expected_version="1.1.10",
    )

    topics = {record["topic"] for record in manifest["documentation"]}
    assert "overview" in topics
    assert (output_dir / "README.md").is_file()


def test_bundle_version_mismatch_fails_without_partial_output(
    tmp_path: Path,
) -> None:
    """An installed-version/build-pin mismatch fails atomically.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    distribution = _create_distribution(tmp_path / "site-packages", version="1.1.11")
    output_dir = tmp_path / "bundle"

    with pytest.raises(ValueError, match="does not match build pin"):
        build_documentation_bundle(
            distribution=distribution,
            output_dir=output_dir,
            expected_version="1.1.10",
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".bundle.*"))


def test_bundle_without_displayable_documentation_fails(
    tmp_path: Path,
) -> None:
    """An installation with no readable documentation is rejected.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    version = "1.1.11"
    distribution = _create_distribution(
        tmp_path / "site-packages",
        version=version,
        description="",
        include_package_docs=False,
    )

    with pytest.raises(ValueError, match="no displayable documentation"):
        build_documentation_bundle(
            distribution=distribution,
            output_dir=tmp_path / "bundle",
            expected_version=version,
        )


def test_bundle_rejects_installed_file_that_differs_from_record(
    tmp_path: Path,
) -> None:
    """Documentation changed after installation fails RECORD verification.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    site_packages = tmp_path / "site-packages"
    distribution = _create_distribution(site_packages)
    (site_packages / "dar_backup/doc/getting-started.md").write_text(
        "changed after installation\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="RECORD hash mismatch"):
        build_documentation_bundle(
            distribution=distribution,
            output_dir=tmp_path / "bundle",
            expected_version="1.1.11",
        )


def test_docs_topic_prints_exact_embedded_document(tmp_path: Path) -> None:
    """A listed topic prints the corresponding installed document.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    distribution = _create_distribution(tmp_path / "site-packages")
    output_dir = tmp_path / "bundle"
    build_documentation_bundle(distribution, output_dir, "1.1.11")
    output = io.StringIO()

    status = run_docs_command(["getting-started"], output_dir, output)

    assert status == 0
    assert output.getvalue() == "# Getting started\n\nExact package documentation.\n"


def test_docs_list_includes_command_manual_hints(tmp_path: Path) -> None:
    """The documentation front page advertises installed command manuals.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    distribution = _create_distribution(tmp_path / "site-packages")
    output_dir = tmp_path / "bundle"
    build_documentation_bundle(distribution, output_dir, "1.1.11")
    output = io.StringIO()

    status = run_docs_command([], output_dir, output)

    assert status == 0
    assert "Command manuals (inside an interactive shell):" in output.getvalue()
    assert "  man dar\n" in output.getvalue()
    assert "  man par2\n" in output.getvalue()


def test_docs_unknown_topic_fails_clearly(tmp_path: Path) -> None:
    """An unknown topic is rejected instead of becoming a filesystem path.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    distribution = _create_distribution(tmp_path / "site-packages")
    output_dir = tmp_path / "bundle"
    build_documentation_bundle(distribution, output_dir, "1.1.11")

    with pytest.raises(ValueError, match="Unknown documentation topic"):
        run_docs_command(["does-not-exist"], output_dir, io.StringIO())


def test_docs_verify_detects_modified_document(tmp_path: Path) -> None:
    """Integrity verification rejects a changed embedded document.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    distribution = _create_distribution(tmp_path / "site-packages")
    output_dir = tmp_path / "bundle"
    build_documentation_bundle(distribution, output_dir, "1.1.11")
    (output_dir / "README.md").write_text("modified\n", encoding="utf-8")

    with pytest.raises(ValueError, match="integrity check failed"):
        run_docs_command(["--verify"], output_dir, io.StringIO())


def test_container_docs_work_without_backup_configuration(image: str) -> None:
    """The default entrypoint dispatches docs before operational validation.

    Args:
        image: Docker image fixture.
    """
    result = _docker_run(image, "docs", "--list")

    assert result.returncode == 0, result.stderr
    assert "Bundled dar-backup documentation" in result.stdout
    assert "overview" in result.stdout
    assert "image" in result.stdout


def test_container_docs_work_as_non_root_user(image: str) -> None:
    """Offline documentation remains readable without root privileges.

    Args:
        image: Docker image fixture.
    """
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "1000:100",
            "-e",
            "DAR_BACKUP_CONFIG=/missing",
            image,
            "docs",
            "overview",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "dar-backup" in result.stdout


def test_container_info_command_works_as_direct_entrypoint(image: str) -> None:
    """The standalone information executable needs no mounts or config.

    Args:
        image: Docker image fixture.
    """
    result = _docker_run(image, entrypoint="dar-backup-image-info")

    assert result.returncode == 0, result.stderr
    assert "dar-backup image information" in result.stdout
    assert "Protected files:" in result.stdout
    assert "MANIFEST.json" in result.stdout


def test_container_unknown_documentation_topic_fails(image: str) -> None:
    """The image returns a clear failure for an unknown documentation topic.

    Args:
        image: Docker image fixture.
    """
    result = _docker_run(image, "docs", "does-not-exist")

    assert result.returncode != 0
    assert "Unknown documentation topic" in result.stderr


def test_container_bare_invocation_is_documentation_discovery(image: str) -> None:
    """Running the image without arguments explains its embedded docs.

    Args:
        image: Docker image fixture.
    """
    result = _docker_run(image)

    assert result.returncode == 0, result.stderr
    assert "Command manuals (inside an interactive shell):" in result.stdout
    assert "  man dar\n" in result.stdout
    assert "  man par2\n" in result.stdout
    assert "Usage: docs <topic>" in result.stdout
