import os
import shutil
import tempfile
import pytest
from pathlib import Path
import subprocess

DEFAULT_BACKUP_DEFINITION = """\
-am
-R /data
-z5
-n
--slice 7G
--cache-directory-tagging
"""

@pytest.fixture(scope="session")
def image():
    return os.environ.get("IMAGE", "dar-backup:dev")

@pytest.fixture
def test_env(tmp_path_factory, request):
    """
    Sets up core environment variables and a default backup.d definition
    for most tests. The default can be skipped by marking a test
    with `@pytest.mark.no_default_definition`.
    """
    base_dir = tmp_path_factory.mktemp("dar-backup-test")
    workdir = base_dir / "workdir"
    backups = workdir / "backups"
    backup_d = workdir / "backup.d"
    data = workdir / "data"
    restore = workdir / "restore"

    for d in [workdir, backups, backup_d, data, restore]:
        d.mkdir(parents=True, exist_ok=True)

    # Skip adding the default backup.d definition if test is marked
    if not request.node.get_closest_marker("no_default_definition"):
        (backup_d / "default").write_text(DEFAULT_BACKUP_DEFINITION)

    env = {
        "WORKDIR": str(workdir),
        "DAR_BACKUP_DIR": str(backups),
        "DAR_BACKUP_D_DIR": str(backup_d),
        "DAR_BACKUP_DATA_DIR": str(data),
        "DAR_BACKUP_RESTORE_DIR": str(restore),
        "RUN_AS_UID": str(os.getuid()),
    }
    yield env
    shutil.rmtree(str(base_dir), ignore_errors=True)

@pytest.fixture
def dataset(test_env):
    """Prepares a default dataset for stateless tests."""
    data_dir = Path(test_env["DAR_BACKUP_DATA_DIR"])
    # Fresh dataset
    for f in data_dir.glob("*"):
        if f.is_file():
            f.unlink()
    (data_dir / "hello.txt").write_text(f"Hello World, created at pytest\n")
    (data_dir / "test.txt").write_text(f"Test file generated at pytest\n")
    subprocess.run(
        ["dd", "if=/dev/urandom", f"of={data_dir}/verify_test.bin", "bs=1M", "count=2"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return test_env
