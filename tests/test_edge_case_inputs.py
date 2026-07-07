"""
test_edge_case_inputs.py
=========================
Backup/restore round-trip tests for unusual filenames and inputs not covered
elsewhere in the suite: leading-dash names, shell metacharacters, Unicode
normalization (NFC vs NFD) and multi-script text, backup-definition name
safety validation, and adversarial symlink targets.

Backups go through scripts/run-backup.sh (like tests/test_backup.py); restores
go straight through `docker run ... dar-backup --restore` since run-backup.sh
has no restore option.

Run with:
    pytest tests/test_edge_case_inputs.py -v

Prerequisites:
    - scripts/run-backup.sh is executable and on the path relative to CWD
    - The Docker image referenced by IMAGE env var (default: dar-backup:dev) is present
    - pytest, and the utils module (sha256sum) are available
"""

import os
import subprocess
import unicodedata
from pathlib import Path

from utils import sha256sum

SCRIPT = "scripts/run-backup.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_script(test_env: dict, *args: str, expect_fail: bool = False) -> subprocess.CompletedProcess:
    """Invoke SCRIPT with *args, merging test_env into the current environment.

    Args:
        test_env: Environment variable overrides (WORKDIR, DAR_BACKUP_*, RUN_AS_UID, ...).
        *args: Positional arguments passed to SCRIPT.
        expect_fail: When True, assert a non-zero exit code instead of zero.

    Returns:
        The completed subprocess, for callers that want to inspect stdout/stderr.
    """
    env = os.environ.copy()
    env.update(test_env)
    result = subprocess.run([SCRIPT, *args], env=env, capture_output=True)
    print(f"\n--- STDOUT [{' '.join([SCRIPT, *args])}] ---\n{result.stdout.decode(errors='replace')}")
    print(f"--- STDERR [{' '.join([SCRIPT, *args])}] ---\n{result.stderr.decode(errors='replace')}")
    if expect_fail:
        assert result.returncode != 0, f"Expected failure but got success\n{result.stdout.decode(errors='replace')}"
    else:
        assert result.returncode == 0, f"Script failed ({result.returncode}): {result.stderr.decode(errors='replace')}"
    return result


def find_full_archive_base(test_env: dict, definition: str = "default") -> str:
    """Find the FULL archive base name (without the .<slice>.dar suffix).

    Args:
        test_env: Environment dict containing DAR_BACKUP_DIR.
        definition: Backup definition name the archive was created under.

    Returns:
        The archive base name, e.g. "default_FULL_2026-07-07".

    Raises:
        AssertionError: If no matching archive slice file is found.
    """
    backup_dir = Path(test_env["DAR_BACKUP_DIR"])
    matches = sorted(backup_dir.glob(f"{definition}_FULL_*.1.dar"))
    assert matches, f"No FULL archive found for definition '{definition}' in {backup_dir}"
    # "<base>.1.dar" -> "<base>"
    return matches[0].name[: -len(".1.dar")]


def restore_archive(test_env: dict, image: str, archive_base: str, subdir: str) -> Path:
    """Restore archive_base to a fresh directory via `dar-backup --restore`.

    Uses the image's default entrypoint (same privilege-drop path run-backup.sh
    exercises) rather than manager's PITR restore-path, since these tests only
    ever restore a single FULL archive in full.

    Args:
        test_env: Environment dict containing WORKDIR/DAR_BACKUP_DIR/DAR_BACKUP_D_DIR.
        image: Docker image tag to run.
        archive_base: Archive base name as returned by find_full_archive_base().
        subdir: Name of the fresh restore directory to create under WORKDIR.

    Returns:
        Path to the directory the archive was restored into.
    """
    restore_target = Path(test_env["WORKDIR"]) / subdir
    restore_target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-e", f"RUN_AS_UID={os.getuid()}",
            "-e", f"RUN_AS_GID={os.getgid()}",
            "-v", f"{test_env['DAR_BACKUP_DIR']}:/backups",
            "-v", f"{test_env['DAR_BACKUP_D_DIR']}:/backup.d",
            "-v", f"{restore_target}:/restore",
            image,
            "--restore", archive_base,
            "--restore-dir", "/restore",
            "--log-stdout", "--verbose",
        ],
        capture_output=True,
    )
    print(f"\n--- STDOUT [restore {archive_base}] ---\n{result.stdout.decode(errors='replace')}")
    print(f"--- STDERR [restore {archive_base}] ---\n{result.stderr.decode(errors='replace')}")
    assert result.returncode == 0, f"Restore of {archive_base} failed: {result.stderr.decode(errors='replace')}"
    return restore_target


# ---------------------------------------------------------------------------
# 1. Leading-dash filenames
# ---------------------------------------------------------------------------

def test_leading_dash_filenames_survive_backup_restore(test_env, image):
    """Filenames starting with '-' must round-trip intact.

    Nothing in the pipeline (dar's own selection engine, dar-backup's
    subprocess argument construction) should ever mistake a filename for a
    CLI flag, since these files never get passed as bare CLI args — but the
    only way to be sure is to actually push one through backup + restore.
    """
    data_dir = Path(test_env["DAR_BACKUP_DATA_DIR"])
    weird_names = ["-rf", "--verbose", "-", "--"]
    for name in weird_names:
        (data_dir / name).write_text(f"content for {name!r}\n")

    run_script(test_env, "-t", "FULL")
    archive_base = find_full_archive_base(test_env)
    restore_dir = restore_archive(test_env, image, archive_base, "restore_leading_dash")

    for name in weird_names:
        restored = restore_dir / name
        assert restored.exists(), f"Restored file missing for filename {name!r}"
        assert restored.read_text() == f"content for {name!r}\n", f"Content mismatch for {name!r}"


# ---------------------------------------------------------------------------
# 2. Shell-metacharacter filename, binary content
# ---------------------------------------------------------------------------

def test_shell_metacharacter_filename_exact_roundtrip(test_env, image):
    """A filename loaded with shell-dangerous characters must survive
    byte-for-byte — both the exact name and binary content.
    """
    data_dir = Path(test_env["DAR_BACKUP_DATA_DIR"])
    weird_name = "file (2026) $HOME & 'quote'.txt"
    original_bytes = os.urandom(512)
    (data_dir / weird_name).write_bytes(original_bytes)
    original_hash = sha256sum(data_dir / weird_name)

    run_script(test_env, "-t", "FULL")
    archive_base = find_full_archive_base(test_env)
    restore_dir = restore_archive(test_env, image, archive_base, "restore_shell_meta")

    restored_names = sorted(p.name for p in restore_dir.glob("*"))
    assert restored_names == [weird_name], (
        f"Expected exactly one restored file named {weird_name!r}, got {restored_names} — "
        "the name was likely split or mangled by shell interpretation somewhere in the pipeline"
    )
    assert sha256sum(restore_dir / weird_name) == original_hash, "Content mismatch after restore"


# ---------------------------------------------------------------------------
# 3. Unicode normalization (NFC vs NFD) and multi-script filenames
# ---------------------------------------------------------------------------

def test_unicode_normalization_and_multiscript_filenames_are_distinct(test_env, image):
    """NFC and NFD forms of the same visual character must remain two distinct
    files (no silent Unicode normalization/collapsing), and multi-script names
    (emoji, CJK, Arabic RTL) must round-trip intact.
    """
    data_dir = Path(test_env["DAR_BACKUP_DATA_DIR"])

    # Built via unicodedata.normalize() rather than typed literals: two forms
    # of the same visual character that render identically but differ at the
    # byte level are otherwise impossible to tell apart just by reading the
    # source file.
    base = "café.txt"
    nfc_name = unicodedata.normalize("NFC", base)   # precomposed é (U+00E9)
    nfd_name = unicodedata.normalize("NFD", base)   # decomposed: e + combining acute (U+0301)
    multiscript_name = "\U0001F4F8-日本-مرحبا.txt"    # 📸 + CJK + Arabic (RTL)

    assert nfc_name != nfd_name, "Test setup bug: NFC/NFD names must differ byte-for-byte"
    assert unicodedata.is_normalized("NFC", nfc_name)
    assert unicodedata.is_normalized("NFD", nfd_name)

    names = {nfc_name, nfd_name, multiscript_name}
    hashes = {}
    for name in names:
        payload = os.urandom(256)
        (data_dir / name).write_bytes(payload)
        hashes[name] = sha256sum(data_dir / name)

    run_script(test_env, "-t", "FULL")
    archive_base = find_full_archive_base(test_env)
    restore_dir = restore_archive(test_env, image, archive_base, "restore_unicode")

    restored_names = set(p.name for p in restore_dir.glob("*"))
    assert restored_names == names, (
        f"Expected {names}, got {restored_names} — Unicode normalization or "
        "encoding was likely altered somewhere in the pipeline"
    )
    for name in names:
        assert sha256sum(restore_dir / name) == hashes[name], f"Content mismatch for {name!r}"


# ---------------------------------------------------------------------------
# 4. Backup-definition name safety validation
# ---------------------------------------------------------------------------

def test_definition_name_with_underscore_requires_unsafe_flag(test_env, image):
    """A definition name containing an underscore is rejected by default and
    only accepted with --allow-unsafe-definition-names.

    run-backup.sh has no passthrough for this flag, so both invocations go
    straight through `docker run` (same pattern as test_manager_creates_db
    and test_restore_dir_writable in test_backup.py).
    """
    def_name = "unsafe_definition_name"
    (Path(test_env["DAR_BACKUP_D_DIR"]) / def_name).write_text("-am\n-R /data\n-z1\n--slice 1G\n")
    (Path(test_env["DAR_BACKUP_DATA_DIR"]) / "hello.txt").write_text("hi\n")

    base_docker_args = [
        "docker", "run", "--rm",
        "-e", f"RUN_AS_UID={os.getuid()}",
        "-e", f"RUN_AS_GID={os.getgid()}",
        "-v", f"{test_env['DAR_BACKUP_DIR']}:/backups",
        "-v", f"{test_env['DAR_BACKUP_D_DIR']}:/backup.d",
        "-v", f"{test_env['DAR_BACKUP_DATA_DIR']}:/data",
        "-v", f"{test_env['DAR_BACKUP_RESTORE_DIR']}:/restore",
        image,
    ]

    # --- Negative: rejected without the flag ---
    result = subprocess.run(
        base_docker_args + ["-F", "-d", def_name, "--log-stdout", "--verbose"],
        capture_output=True,
    )
    print(f"\n--- STDOUT [no flag] ---\n{result.stdout.decode(errors='replace')}")
    print(f"--- STDERR [no flag] ---\n{result.stderr.decode(errors='replace')}")
    assert result.returncode != 0, "Expected rejection of unsafe definition name without the flag"

    # --- Positive: accepted with the flag ---
    result = subprocess.run(
        base_docker_args + [
            "-F", "-d", def_name, "--allow-unsafe-definition-names",
            "--log-stdout", "--verbose",
        ],
        capture_output=True,
    )
    print(f"\n--- STDOUT [with flag] ---\n{result.stdout.decode(errors='replace')}")
    print(f"--- STDERR [with flag] ---\n{result.stderr.decode(errors='replace')}")
    assert result.returncode == 0, (
        f"Expected success with --allow-unsafe-definition-names, "
        f"got {result.returncode}: {result.stderr.decode(errors='replace')}"
    )
    assert any(Path(test_env["DAR_BACKUP_DIR"]).glob(f"{def_name}_FULL_*.dar")), (
        "Expected archive files for the unsafe definition name after success"
    )


# ---------------------------------------------------------------------------
# 5. Adversarial symlink target
# ---------------------------------------------------------------------------

def test_symlink_with_unicode_space_target_preserved(test_env, image):
    """A dangling symlink whose target contains spaces and Unicode must
    survive backup/restore with the exact target string preserved, without
    dar-backup trying to dereference (and failing on) the nonexistent target.
    """
    data_dir = Path(test_env["DAR_BACKUP_DATA_DIR"])
    link_name = "broken-link.txt"
    target = "../does not exist/target with spaces and üñíçødé.bin"
    (data_dir / link_name).symlink_to(target)
    assert not (data_dir / link_name).exists(), "Test setup bug: symlink should be dangling"

    run_script(test_env, "-t", "FULL")
    archive_base = find_full_archive_base(test_env)
    restore_dir = restore_archive(test_env, image, archive_base, "restore_symlink")

    restored_link = restore_dir / link_name
    assert restored_link.is_symlink(), "Restored path should be a symlink"
    actual_target = os.readlink(restored_link)
    assert actual_target == target, f"Symlink target mismatch: expected {target!r}, got {actual_target!r}"
