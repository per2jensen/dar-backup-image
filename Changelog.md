# dar-backup-image Changelog

## v0.5.20 - 2026-02-14

- dar-backup version 1.1.0 included in the image
- image rebuilt to include Ubuntu 24.04 vuln fixes

## v0.5.19 - 2025-10-28

Github link: [v0.5.19](https://github.com/per2jensen/dar-backup-image/tree/v0.5.19)

### Changed

- **`dar-backup` now at version 1.0.01**
- **Image refreshed**

## v0.5.16 - 2025-08-01

Github link: [v0.5.16](https://github.com/per2jensen/dar-backup-image/tree/v0.5.16)

### Changed

- **`dar` compiled from source (v2.7.19)**  
  - Replaces Ubuntu 24.04’s older `dar` package with the latest upstream release.
  - The build process:
    - Verifies the tarball using **Denis Corbin’s GPG signature**.
    - Builds from source with **full feature set** (zstd, lz4, Argon2, GPGME, librsync, and remote repository support).
    - Runs **strict feature verification** (gzip, encryption, symlink handling, multi-threading, etc.) before including it in the final image.

## v0.5.15 - 2025-07-26

Github link: [v0.5.15](https://github.com/per2jensen/dar-backup-image/tree/v0.5.15)

### Added

- **`dar` compiled from source (v2.7.18)**  
  - Replaces Ubuntu 24.04’s older `dar` package with the latest upstream release.
  - The build process:
    - Verifies the tarball using **Denis Corbin’s GPG signature**.
    - Builds from source with **full feature set** (zstd, lz4, Argon2, GPGME, librsync, and remote repository support).
    - Runs **strict feature verification** (gzip, encryption, symlink handling, multi-threading, etc.) before including it in the final image.
  - Ensures consistent, modern functionality.

### Changed

- **Docker image improvements**
  - Stripped unnecessary build artifacts and documentation.
  - Optimized venv cleanup, reducing the final image size to **~160 MB**.
  - Improved linker and runtime configuration for smooth `libdar64` and `libthreadar` loading.

### Testing

- Full pytest suite passes after integrating source-built `dar`.
- Confirmed compatibility with both locally built and pulled images:

  ```bash
  make test
  make IMAGE=per2jensen/dar-backup:0.5.15 test-pulled
  ```

## v0.5.14 - 2025-07-24

Github link: [v0.5.14](https://github.com/per2jensen/dar-backup-image/tree/v0.5.14)

### Added

- **Backup definition support (`-d` / `--backup-definition`)**  
  - `run-backup.sh` now accepts `-d <name>` or `--backup-definition <name>` to select a specific definition file.  
  - Falls back to `default` (auto-created if missing) when no definition is given.  
  - Backup archives now follow the pattern:  
    `<definition>_<type>_YYYY-MM-DD.<slice>.dar`

- **Expanded script documentation**  
  - Comprehensive header in `run-backup.sh` describing:
    - Environment variables, UID/GID handling, and directory resolution order.
    - Daily backup rules (one FULL, one DIFF, one INCR per definition per day).
    - Multiple quick-start examples for personal, shared, and automated setups.
  - README updated with matching directory layout, UID/GID, and usage examples.

### Changed

- **Updated `run-backup.sh` behavior**  
  - Enforces the **one-per-day-per-type rule** for backups.
  - Displays which backup definition is being used in its output.
  - Now generates a default `backup.d/default` if none exists (ensuring first-run success).

- **Improved testing**  
  - New pytest tests for the `-d`/`--backup-definition` feature:
    - Confirms correct DAR filenames.
    - Validates separate runs with different definitions.
    - Covers default fallback behavior when `-d` is omitted.
  - Tests updated to start from a **clean slate** (removes old archives) so FULL → DIFF → INCR chains work reliably.

### Testing

- Full test suite passes (`make test`) with **stateful chains** and **definition-aware backups**.
- Ensured compatibility with Docker Hub–pulled and locally built images.
  - `make IMAGE=per2jensen/dar-backup:0.5.13 test-pulled` succeeds

## v0.5.13 - 2025-07-22

Github link: [v0.5.13](https://github.com/per2jensen/dar-backup-image/tree/v0.5.13)

### Added

- **`make size-report`**: New target to display image layer sizes in MB (normalized, readable table).  
- **`make dev-nuke`**: Easy cleanup of all build cache and layers for troubleshooting.

### Changed

- Image size reduced from **270 MB → 143 MB** while retaining:
  - Standard `ubuntu:24.04` base image (no switch to slim/minimal).  
  - Full `dist-upgrade` for security updates.  
- Combined redundant `RUN` steps in Dockerfile to shrink intermediate layers.
- Virtualenv cleanup improved (removes tests, `pip`, `setuptools`, and `wheel` entirely).  
- Truncated long Docker history commands in size reports for easier reading.

### Testing

- Legacy Bash test suite replaced with **pytest setup**
  - Proper fixtures and `conftest.py`.
  - Stateful FULL → DIFF → INCR tests combined into a single coherent test.
  - SHA256 hash reporting preserved for dataset integrity checks.

---

## v0.5.12 - 2025-07-21

Github link: [v0.5.12](https://github.com/per2jensen/dar-backup-image/tree/v0.5.12)

### Added

- Unified test dataset handling with `stateful` and `stateless` modes to support FULL → DIFF → INCR backup chains.
- Comprehensive **SHA256 tracing** in test harness for debugging data integrity across test runs.
- Test case enhancements:
  - `test_case_8`: Verifies restore directory usability (permissions and writability).
  - `test_case_9`: Validates `manager` command creates `.db` files correctly when backup definitions exist.

### Changed

- Reworked **test framework** to ensure a **clean baseline (`clean_dirs`)** at the start of every test run, eliminating state leakage between tests.
- Fixed `prepare_dataset()` logic to prevent accidental file mutations unless explicitly in stateful mode.
- `run-backup.sh` no longer injects sample data (datasets are now entirely managed by the test suite).

### Security & Build

- Consolidated to a **single Dockerfile**, simplifying the build pipeline and reducing maintenance complexity.
- Removed unnecessary Python tooling (`pip`, `setuptools`, `wheel`) from the final runtime image to shrink the attack surface.
- Enforced **non-root execution (`daruser`, UID 1000)** for all container operations.
- Cleaned up intermediate build artifacts to reduce image size and attack surface.
- All base image and dependency vulnerabilities addressed; image verified with **Scout** (no high/critical CVEs).

---
