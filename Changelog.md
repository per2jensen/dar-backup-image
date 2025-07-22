# dar-backup-image Changelog

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
