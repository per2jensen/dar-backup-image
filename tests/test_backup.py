import os
import shutil
import subprocess
import pytest
import os
import shutil
import pytest
import subprocess
import re

from pathlib import Path
from utils import compare_to_originals
from utils import sha256sum, compare_to_originals

SCRIPT = "scripts/run-backup.sh"


def run_script(test_env, *args, expect_fail=False):
    env = os.environ.copy()
    env.update(test_env)
    result = subprocess.run([SCRIPT, *args], env=env, capture_output=True)
    if expect_fail:
        assert result.returncode != 0, f"Expected failure but got success\n{result.stdout.decode()}"
    else:
        assert result.returncode == 0, f"Script failed ({result.returncode}): {result.stderr.decode()}"
    return result

def snapshot_directory(src, snapshot_dir):
    """Snapshot dataset for later comparison."""
    shutil.rmtree(snapshot_dir, ignore_errors=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for file in Path(src).glob("*"):
        if file.is_file():
            shutil.copy2(file, snapshot_dir / file.name)

def print_sha256_for_dir(label, directory):
    directory = Path(directory)
    print(f"\n--- SHA256 hashes for {label} ---")
    if not directory.exists():
        print("(missing)")
    else:
        for f in sorted(directory.glob("**/*")):
            if f.is_file():
                print(f"{sha256sum(f)}  {f}")
    print("----------------------------------------")


# ---- Regular tests (from before) ----

def test_default_full_backup(test_env, dataset):
    run_script(test_env, "-t", "FULL")

def test_custom_image_diff_expect_fail(test_env, dataset):
    test_env["IMAGE"] = "dar-backup:custom"
    run_script(test_env, "-t", "DIFF", expect_fail=True)

def test_fail_when_run_as_root(test_env, dataset):
    test_env["RUN_AS_UID"] = "0"
    run_script(test_env, "-t", "INCR", expect_fail=True)

def test_fail_invalid_backup_type(test_env, dataset):
    run_script(test_env, "-t", "invalid", expect_fail=True)

def test_custom_backup_dir(test_env, dataset):
    custom_dir = Path("/tmp/custom_backups")
    if custom_dir.exists():
        shutil.rmtree(custom_dir)
    test_env["DAR_BACKUP_DIR"] = str(custom_dir)
    run_script(test_env, "-t", "FULL")
    assert any(custom_dir.glob("*.dar"))

# ---- Stateful chain (FULL → DIFF → INCR) ----

def test_stateful_full_diff_incr_chain(tmp_path_factory):
    """Runs FULL → DIFF → INCR backups, mutating dataset each time, with SHA256 validation."""
    base_dir = tmp_path_factory.mktemp("dar-backup-stateful")
    workdir = base_dir / "stateful"
    backups = workdir / "backups"
    backup_d = workdir / "backup.d"
    data = workdir / "data"
    restore = workdir / "restore"
    originals = workdir / "originals"
    for d in [workdir, backups, backup_d, data, restore]:
        d.mkdir(parents=True, exist_ok=True)

    env = {
        "WORKDIR": str(workdir),
        "DAR_BACKUP_DIR": str(backups),
        "DAR_BACKUP_D_DIR": str(backup_d),
        "DAR_BACKUP_DATA_DIR": str(data),
        "DAR_BACKUP_RESTORE_DIR": str(restore),
        "RUN_AS_UID": str(os.getuid()),
    }

    # Initial dataset for FULL
    (data / "hello.txt").write_text("Hello World (stateful)\n")
    (data / "test.txt").write_text("Initial state\n")
    subprocess.run(
        ["dd", "if=/dev/urandom", f"of={data}/verify_test.bin", "bs=1M", "count=1"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    snapshot_directory(data, originals)

    # --- FULL Backup ---
    print("\n=== FULL BACKUP ===")
    print_sha256_for_dir("data before FULL", data)
    run_script(env, "-t", "FULL")
    print_sha256_for_dir("data after FULL", data)
    mismatches = compare_to_originals(originals, data)
    assert not mismatches, f"Mismatched files after FULL: {mismatches}"

    # --- DIFF Backup ---
    with open(data / "test.txt", "a") as f:
        f.write("Stateful change after FULL\n")
    snapshot_directory(data, originals)

    print("\n=== DIFF BACKUP ===")
    print_sha256_for_dir("data before DIFF", data)
    run_script(env, "-t", "DIFF")
    print_sha256_for_dir("data after DIFF", data)
    mismatches = compare_to_originals(originals, data)
    assert not mismatches, f"Mismatched files after DIFF: {mismatches}"

    # --- INCR Backup ---
    with open(data / "test.txt", "a") as f:
        f.write("Stateful change after DIFF\n")
    snapshot_directory(data, originals)

    print("\n=== INCR BACKUP ===")
    print_sha256_for_dir("data before INCR", data)
    run_script(env, "-t", "INCR")
    print_sha256_for_dir("data after INCR", data)
    mismatches = compare_to_originals(originals, data)
    assert not mismatches, f"Mismatched files after INCR: {mismatches}"

    # Validate backup artifacts
    dar_files = list(backups.glob("*.dar"))
    assert dar_files, "No .dar files produced during FULL → DIFF → INCR chain"


# ---- Remaining Docker/restore/manager tests ----

def test_container_runs_as_daruser(image):
    uid = subprocess.check_output(
        ["docker", "run", "--rm", "--user", "1000", "--entrypoint", "/bin/sh", image, "-c", "id -u"]
    ).decode().strip()
    assert uid == "1000"

def test_venv_usage(image):
    path = subprocess.check_output(
        ["docker", "run", "--rm", "--entrypoint", "/bin/sh", image, "-c", "which dar-backup"]
    ).decode().strip()
    assert path == "/opt/venv/bin/dar-backup"
    for pkg in ["pip", "setuptools", "wheel"]:
        res = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "/bin/sh", image, "-c", f"python3 -m {pkg} --version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        assert res.returncode != 0, f"{pkg} still present"

def test_restore_dir_writable(test_env, dataset, image):
    subprocess.run([SCRIPT, "-t", "FULL"], env={**os.environ, **test_env}, check=True)
    subprocess.run([
        "docker", "run", "--rm",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{test_env['WORKDIR']}:{test_env['WORKDIR']}",
        "-e", f"DAR_BACKUP_RESTORE_DIR={test_env['DAR_BACKUP_RESTORE_DIR']}",
        "--entrypoint", "sh", image, "-c",
        'mkdir -p "$DAR_BACKUP_RESTORE_DIR" && touch "$DAR_BACKUP_RESTORE_DIR/restore_test.txt"'
    ], check=True)
    assert Path(test_env["DAR_BACKUP_RESTORE_DIR"], "restore_test.txt").exists()

def test_manager_creates_db(test_env, image):
    subprocess.run([
        "docker", "run", "--rm",
        "-v", f"{test_env['DAR_BACKUP_DIR']}:/backups",
        "-v", f"{test_env['DAR_BACKUP_D_DIR']}:/backup.d",
        "--entrypoint", "manager", image,
        "--create-db", "--config", "/etc/dar-backup/dar-backup.conf"
    ], check=True)
    assert any(Path(test_env["DAR_BACKUP_DIR"]).glob("*.db"))


###==============================


SCRIPT = "scripts/run-backup.sh"

def run_script(test_env, *args, expect_fail=False):
    env = os.environ.copy()
    env.update(test_env)
    result = subprocess.run([SCRIPT, *args], env=env, capture_output=True)
    if expect_fail:
        assert result.returncode != 0, f"Expected failure but got success\n{result.stdout.decode()}"
    else:
        assert result.returncode == 0, f"Script failed ({result.returncode}): {result.stderr.decode()}"
    return result

def create_definition(backup_d_dir, name, content):
    fpath = Path(backup_d_dir) / name
    fpath.write_text(content)
    return fpath


def dar_files_for_definition(backup_dir, definition, btype):
    """
    Return list of DAR files matching <definition>_<btype>_YYYY-MM-DD.<slice>.dar.
    """
    pattern = re.compile(
        rf"^{re.escape(definition)}_{btype}_[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\.[0-9]+\.dar$"
    )
    return [f for f in Path(backup_dir).glob("*.dar") if pattern.match(f.name)]




def test_fail_when_definition_does_not_exist(test_env, dataset):
    """
    Verify that specifying -d with a non-existent file causes failure.
    """
    run_script(test_env, "-t", "INCR", "-d", "does-not-exist", expect_fail=True)



#============

def test_default_chain_with_default_definition(test_env, dataset):
    """
    Verify FULL → DIFF → INCR chain works with the default definition.
    Ensures each stage produces .dar files named for "default".
    """
    def_name = "default"
    for stage in ["FULL", "DIFF", "INCR"]:
        run_script(test_env, "-t", stage)
        # Check that the expected .dar file(s) exist
        dar_files = dar_files_for_definition(test_env["DAR_BACKUP_DIR"], def_name, stage)
        assert dar_files, f"No DAR files for {def_name} at stage {stage}"

def test_full_and_diff_with_custom_definition(test_env, dataset):
    """
    Verify that a custom definition can do FULL followed by DIFF backups.
    """
    def_name = "customdef"
    create_definition(
        test_env["DAR_BACKUP_D_DIR"],
        def_name,
        "-am\n-R /data\n-z1\n--slice 1G\n# custom def\n"
    )
    # FULL
    run_script(test_env, "-t", "FULL", "-d", def_name)
    dar_files = dar_files_for_definition(test_env["DAR_BACKUP_DIR"], def_name, "FULL")
    assert dar_files

    # DIFF (requires FULL)
    run_script(test_env, "-t", "DIFF", "-d", def_name)
    dar_files = dar_files_for_definition(test_env["DAR_BACKUP_DIR"], def_name, "DIFF")
    assert dar_files

def test_full_diff_incr_with_longform(test_env, dataset):
    """
    Verify long option --backup-definition works through FULL → DIFF → INCR.
    """
    def_name = "longform"
    create_definition(
        test_env["DAR_BACKUP_D_DIR"],
        def_name,
        "-am\n-R /data\n-z2\n--slice 2G\n# longform test\n"
    )
    for stage in ["FULL", "DIFF", "INCR"]:
        run_script(test_env, "-t", stage, "--backup-definition", def_name)
        dar_files = dar_files_for_definition(test_env["DAR_BACKUP_DIR"], def_name, stage)
        assert dar_files, f"No DAR files for {def_name} at stage {stage}"
