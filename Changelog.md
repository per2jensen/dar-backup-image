# dar-backup-image Changelog

## 0.9.1 - not released

### Fixed

- align the README, release guide, contributor guide, demo, and generated site
  with the implemented helper defaults, mount paths, release/refresh policy,
  Cosign identities, and candidate verification flow
- make `DOCKER_PULL=true` pull before inspecting the selected image, validate
  the pull policy explicitly, and cover the helper's default image and mounts
  with isolated subprocess tests
- share one tested Docker publication interface between manual releases and
  weekly refreshes, including candidate rollback, digest signing and SBOM
  attestation, immutable remote pull/runtime verification, and delayed
  `:latest` promotion, followed by always-run Docker credential cleanup
- keep weekly refresh application source, current orchestration, and mutable
  housekeeping in separate checkouts instead of overlaying a `main` Makefile;
  select application source from the latest build-history record's Git revision
  and tolerate explicitly reported historical release-tag mismatches
- serialize release and refresh publication with one concurrency group so
  their `:latest` updates cannot race
- keep `FINAL_VERSION=dev` for development while making release targets require
  an exact `IMAGE_VERSION` match and refresh targets require an explicit,
  positive numeric `BASE_VERSION-N` derivation from build history, independent
  of `IMAGE_VERSION`
- make manual releases build from an immutable full source commit, keep
  housekeeping in a separate checkout, and tag the exact source revision
- push release candidates under their version first, roll that tag back on
  signing failure, and promote `:latest` only after signing and attestation
- persist the cosign failure badge to `main` with bounded concurrent-push
  retries, while preserving the previously published `:latest`
- publish refresh history and its source/digest-annotated Git tag atomically,
  force-stage the intended SBOM/SARIF evidence, and avoid reporting successful
  signing as failed when only Git housekeeping fails
- publish release housekeeping and its source-pointing annotated tag atomically,
  force-stage the intended SBOM/SARIF evidence, and reject unrelated changes
- require complete GitHub Release assets and add a verification-only recovery
  workflow for creating or repairing a failed existing GitHub Release
- construct release SBOM links from the uploaded asset basename and restore
  the Grype cache before the single dedicated release scan
- pin every external action in the release workflow to an immutable commit SHA
- avoid unbounded package installation before CI checkout and prevent the
  always-run SBOM summary from masking an unavailable checkout
- describe edge-mode badge evidence as 1% bitrot at both archive edges instead
  of the misleading 2% aggregate
- label binary archive sizes and RSS measurements as GiB and MiB in
  large-scale schema-v9 results, console output, and documentation
- normalize Docker's decimal layer sizes with decimal conversions in the
  image size report
- label complete, internally consistent schema-v6 badge evidence as
  `Full restore verified ✓`
- corrupt exactly 1% at each archive boundary in edge bitrot mode and record
  the per-boundary percentage explicitly
- include `-rc<number>` releases in the generated README release table while
  continuing to exclude weekly numeric-suffix refresh builds
- reject unitless or conflicting large-scale slice sizes before expensive
  setup, recognize long-form slice options in custom definitions, and report
  backup-command failures explicitly
- verify restored POSIX permission modes in every mandatory primer PITR and
  across optional complete restores, with explicit schema-v7 evidence
- verify the same-filesystem `portable-posix-v1` metadata contract during
  complete restores: numeric ownership, access/default ACLs, `user.*` xattrs,
  and hard-link topology, with defensive schema-v8 evidence
- preserve archived numeric UID/GID values by running only validated PITR
  extraction targets as container root, with scoped cleanup and a tiny
  positive/negative ownership round-trip test
- define and enforce a narrow literal `-g`/`-P` large-scale selection contract,
  and base disk preflight on exact selected bytes after pruning and cache tags

## 0.9.0 - 2026-08-16

### Added

- Nearing a 1.0 release - I am keeping it at 0.9.x for some time, will
  then run an -rc or two and hopefully reach 1.0 without too many issues

- add optional complete archive-root PITR restoration to the large-scale test,
  selected automatically through 25 GiB by default, forceable at any size, or
  explicitly disabled, with source comparison and schema-v6 decision evidence
- publish an evidence-backed Shields badge for explicitly approved successful
  torture tests of at least 100 GiB, using a defensive JSONL consumer
- support development-image builds from a validated external `dar-backup`
  wheel, with installation-source and wheel SHA-256 provenance labels
- add `dev.md` as the canonical development-image build guide
- register `dar-backup`, `cleanup`, and `manager` completion system-wide for
  interactive Bash shells
- install the real man system and retain all manuals generated from the
  verified DAR source
- retain the manuals for the installed `par2`, `par2create`, `par2repair`, and
  `par2verify` commands
- advertise the installed `dar` and `par2` manuals on the image documentation
  front page
- install checksum-verified, centrally pinned Syft and Grype releases with
  bounded retries and a weekly update reminder
- preserve a clear unavailable scan summary when upstream tool installation or
  SBOM generation fails, without cascading missing-file errors
- embed the GPL license text at `/LICENSE` in the image
- document how to print the embedded license
- verify the embedded license SHA-256 and exact OCI license label during release
- record schema-v3 large-scale-test evidence with immutable image provenance,
  source scale, exact archive bytes, total runtime, and per-stage outcomes
- record schema-v4 reproducible random bitrot evidence, including affected
  slices and byte ranges, injection/repair timings, and PAR2 data-block counts
- add a standalone generator and CI drift check for the README release table
- preserve the installed dar-backup metadata manual, licenses, and every
  packaged documentation file inside the image
- preserve the image repository README as the hashed offline `image` topic
- add configuration-free `docs` and `info` image commands, stable embedded
  documentation paths, an integrity manifest, and OCI discovery labels

### Changed

- show `Full restore ✓` on the torture-test badge only for complete,
  internally consistent schema-v6 restore evidence, and make exactly 100 GiB
  eligible for explicitly requested publication
- keep PyPI installation as the default and refuse to publish images built
  from local development wheels
- add selectable contiguous, fragmented, and archive-edge bitrot modes while
  keeping contiguous 2% corruption as the default and repairing each affected
  DAR slice only once
- corrupt a random 2% range per backup phase, allow the range to cross DAR
  slice boundaries, and use buffered byte-accurate writes for faster injection
- accept `BITROT_SEED`/`--bitrot-seed` to replay exact corruption selections
- generate the complete README release table, including UTC release dates,
  from canonical `doc/build-history.json` metadata during every release
- collect documentation only after the existing dar-backup installation has
  completed, without changing its proven `pip install` deployment path

### Fixed

- test documentation completion against files actually present in the selected
  `dar-backup` wheel while verifying shell registration independently
- discover each large-scale-test archive by its unique phase-specific first
  slice so runs crossing midnight do not reject successful DIFF/INCR backups
- ensure initialized large-scale tests write exactly one JSONL result when they
  complete, fail, abort, or receive an interrupt
- fail PAR2 verification when no slice files exist instead of reporting a
  vacuous pass
- restore the accidentally removed `0.5.28` README release row
- accept and verify the expected PITR tombstone result for deleted paths in
  the backup/restore comparison flow without hiding unrelated report failures
- run the FULL restore comparison once and correctly verify that the INCR
  restore no longer preserves the deliberately broken hard link
- retry transient GHCR image-pull failures with bounded backoff in every
  image-consuming build/test/scan job

## 0.5.28 - 2026-07-08

### BUGFIX

- use dar-backup version v2-1.1.10 with a PITR fix

### Changed

- `scripts/large_scale_test.sh`/`run_large_scale_test.sh` no longer compensates for a bug found in the PITR code in `dar-backup`

### Added

- test cases exercising file names with special non-ascii UTF-8 chars
- [documentation](doc/demo-large-scale-test.md) on how to try out `run_large_scale_test.sh` as a user

## 0.5.27 - 2026-07-06

### Changed

- dar-backup version 1.1.9

## 0.5.26 - 2026-06-12

### Changed

- dar-backup version 1.1.8

## 0.5.25.1 - 2026-06-10

### Vuln fix

- Rebuild image to include openssl fix

## 0.5.25 - 2026-06-07

### BUGFIX

- Use `dar-backup` version v2-1.1.7 (with an important par2 OOM bugfix)

### Added

- Baked in en_US.UTF-8 locale + danish, german, french and spanish
- documented how to mount directories into a container
- test cases for the run_backup.sh script
  
### Changed

- run-backup.sh demo script improvements. Now in a solid state
- build_history.json now records versions of `dar-backup` and `dar`
  - release and refresh workflows now commit sbom and sarif files in repo

## 0.5.24 - 2026-05-17 (busy bee at work)

### Changed

- dar-backup version now 1.1.5

## v0.5.23 - 2026-05-17

### Added

- helper script `scripts/save-dar-backup-image.sh` saves Docker images locally. Suitable for crontab/systemd.

### Changed

- Release workflow improvements
  - Release workflow now reads IMAGE_VERSION and aborts release if version exists
  - cosign rollback:  change badge to "failed" in dull grey
  - add/commit badge success in housekeeping step
  - add/commit clonepulse release annotation in housekeeping step
  - Github release now adds useful information and links in body
  - release a versioned image and make it :latest also
- Image refresh workflow which can rebuild the latest released version to keep the underlying base os up to date
  - builds x.y.z-1, x.y.z-2 .. x.y.z-n
  - make the new image `:latest`
- README badges update
- Manually added the missing cosign ok badge from version 0.5.22 release
- Using dar version 2.7.21 (no longer the RC1)
- State specific base image digest in build-history.json
  
## v0.5.22 - 2026-04-10

### Added

- Release workflow with cosign and SBOM attestation uploaded to DockerHub

### Changed

- Image with `dar-backup` v1.1.3 refreshed.

## v0.5.21 - 2026-03-24

- Image refresh

## v0.5.20 - 2026-02-14

- dar-backup version 1.1.1 included in the image
- image rebuilt to include Ubuntu 24.04 vuln fixes
- CI E2E now runs `scripts/backup-restore-compare.sh` (PITR restore + PITR report) to keep workflow behavior aligned with local testing

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
