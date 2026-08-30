<!--
SPDX-FileCopyrightText: 2025-2026 Per Jensen

SPDX-License-Identifier: GPL-3.0-or-later

This file is part of dar-backup-image:
https://github.com/per2jensen/dar-backup-image

License terms and warranty disclaimer:
https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
-->

# dar-backup image — verifiable backups and a long-term restore time capsule
<a href="https://github.com/per2jensen/dar-backup-image/releases"><img alt="Tag" src="https://img.shields.io/github/v/tag/per2jensen/dar-backup-image"/></a>
![CI](https://github.com/per2jensen/dar-backup-image/actions/workflows/build-test-scan.yml/badge.svg)
[![Large scale torture test](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/test-report/torture-test-badge.json)](https://github.com/per2jensen/dar-backup-image/blob/main/doc/test-report/large-scale-results.jsonl)
<a href="#verifying-an-image-yourself">
  <img alt="cosign badge" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/cosign_badge.json"/>
</a>
<img alt="License" src="https://img.shields.io/badge/license-GPL--3.0--or--later-blue"/>


<img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/per2jensen/dar-backup"/> 

[![# clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/clonepulse/badge_clones.json)](https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/clonepulse/weekly_clones.png)
[![Milestone](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/clonepulse/milestone_badge.json)](https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/clonepulse/weekly_clones.png)  <sub>🎯 Stats powered by [ClonePulse](https://github.com/per2jensen/clonepulse)</sub>

---

**GitHub**: [per2jensen/dar-backup-image](https://github.com/per2jensen/dar-backup-image)

**Docker Hub**: [per2jensen/dar-backup](https://hub.docker.com/r/per2jensen/dar-backup)

---

## dar-backup-image

`dar-backup-image` packages `dar-backup`, `dar`, PAR2, and their runtime dependencies into a versioned, auditable Docker image.

It has **two equally important purposes**:

1. **Run backups and restores today** in a clean, isolated environment without installing `dar`, Python tooling, or PAR2 on the host.
2. **Preserve a known-working restore environment for the future** by saving a versioned image alongside your archives.

The second use is deliberate: the image is a **restore time capsule**. If you need to recover an archive years from now, you can use the packaged toolchain preserved with the backup instead of hunting for compatible packages or reconstructing an old software environment.

For long-term archival use, save a **specific versioned image** rather than relying only on `:latest`. The mutable `:latest` tag is useful for current operations and receives regular security refreshes; a pinned and locally archived version is the artifact you want to retain with your backups.

A helper script, [`scripts/save-dar-backup-image.sh`](scripts/save-dar-backup-image.sh), is provided for this purpose. It selects the highest-numbered release or refresh in [`doc/build-history.json`](doc/build-history.json) and saves that versioned image as a compressed tar archive. Its current integrity limitations are documented in [Preserve the restore environment with your archives](#preserve-the-restore-environment-with-your-archives).

The image also works well as an everyday backup runner for cron jobs, systemd timers, CI pipelines, and FUSE-based storage. Its default entrypoint is `dar-backup`; `dar`, `par2`, or an interactive shell can be invoked directly by overriding the entrypoint.

At its core, `dar-backup` wraps `dar` and PAR2 for reliable FULL, DIFF, and INCR backups. It validates archives, performs restore tests, manages catalog databases, and can generate redundancy files to protect archives against bit rot.

### Bundled documentation

The image preserves documentation from the installed `dar-backup`
distribution. It works without network access, backup configuration, or
mounted volumes, so a saved image remains self-documenting years later.

```bash
IMAGE=per2jensen/dar-backup:latest

# Discover the documentation (a bare invocation does the same thing)
docker run --rm "$IMAGE" docs
docker run --rm "$IMAGE"

# Display a topic bundled by dar-backup
docker run --rm "$IMAGE" docs overview
docker run --rm "$IMAGE" docs getting-started

# Show paths, component versions, provenance, and project links
docker run --rm "$IMAGE" docs --path
docker run --rm "$IMAGE" info

# Verify every recorded documentation SHA-256
docker run --rm "$IMAGE" docs --verify
```

Use `docs --list` to see the topics available in a particular image. Topic
names follow the documentation actually present in its installation; for example,
the expanded `dar_backup/doc/` collection first appears with dar-backup
1.1.11.

The stable filesystem location is `/usr/share/doc/dar-backup/`. It contains:

- `image/README.md` — this image repository's exact build-context README
- `README.md`, the Markdown description embedded in package metadata
- `doc/`, every file included under `dar_backup/doc/` or `dar_backup/docs/`
- `licenses/` and raw `METADATA`
- `INDEX.md` and the integrity/provenance record `MANIFEST.json`

`/usr/share/doc/dar-backup-image/README.md` and `/README.md` link to the
embedded image operating guide for simple filesystem discovery. Use
`docs image` to print it and `docs overview` for the dar-backup overview.
The standalone executables `dar-backup-image-docs` and
`dar-backup-image-info` remain usable when the container entrypoint is
overridden. The OCI labels `org.opencontainers.image.documentation`,
`org.dar-backup.documentation.command`, and
`org.dar-backup.documentation.path` provide discovery without starting the
image.

The image contains man pages for `dar` and `par2` which make the image self-documenting for all commands used to restore or backup.

### Highlights

- **Long-term restore time capsule**, preserve a known-working `dar-backup` / `dar` / PAR2 environment with your archives
- **Reproducible backup runner**, no host installation of `dar`, Python tooling, or PAR2 required
- **Self-documenting**, all `dar-backup`, `dar-backup-image`, `dar` and `par2` documentation is included and easily discoverable by future users
- **Versioned and auditable**, released images are tested, scanned, signed, and accompanied by an SBOM
- **Stateless and portable**, archive the image itself and move it with your backup sets
- **FUSE-friendly**, works without root and is suited to user-space mounted storage
- **Built-in configuration**, automatically loads `/etc/dar-backup/dar-backup.conf` unless overridden
- **Ready for automation**, usable from cron, systemd timers, and CI pipelines

> **Current operation vs. long-term preservation**
>
> Use `:latest` when you want the current tested and security-refreshed image.
>
> For disaster recovery years into the future, pin a version and save the image itself alongside your archives.

## Table of Contents

- [dar-backup image — verifiable backups and a long-term restore time capsule](#dar-backup-image--verifiable-backups-and-a-long-term-restore-time-capsule)
  - [dar-backup-image](#dar-backup-image)
    - [Bundled documentation](#bundled-documentation)
    - [Highlights](#highlights)
  - [Table of Contents](#table-of-contents)
  - [Preserve the restore environment with your archives](#preserve-the-restore-environment-with-your-archives)
  - [Hands-on Demo: `dar-backup` in a Container](#hands-on-demo-dar-backup-in-a-container)
  - [`dar` versions](#dar-versions)
  - [Recent releases uploaded to Docker Hub](#recent-releases-uploaded-to-docker-hub)
  - [Release Pipeline and Supply Chain Security](#release-pipeline-and-supply-chain-security)
    - [Pipeline steps](#pipeline-steps)
    - [What cosign keyless signing provides](#what-cosign-keyless-signing-provides)
    - [Verifying an image yourself](#verifying-an-image-yourself)
    - [Verifying the SBOM attestation](#verifying-the-sbom-attestation)
    - [Inspecting the Rekor transparency log entry](#inspecting-the-rekor-transparency-log-entry)
  - [Understanding Volume Mounts and Backup Definitions](#understanding-volume-mounts-and-backup-definitions)
  - [Useful links](#useful-links)
  - [License](#license)
  - [Docker Hub image repo](#docker-hub-image-repo)
  - [Description](#description)
  - [Directory Layout and Permissions](#directory-layout-and-permissions)
    - [How Directory Overrides Work](#how-directory-overrides-work)
    - [UID and GID Behavior](#uid-and-gid-behavior)
    - [Recommended Directory Layouts](#recommended-directory-layouts)
      - [Personal (All Under Your Home Directory)](#personal-all-under-your-home-directory)
      - [Shared Group Setup (Multiple Users)](#shared-group-setup-multiple-users)
      - [Dedicated Service Account (Automated Backups)](#dedicated-service-account-automated-backups)
  - [Environment Variables](#environment-variables)
  - [How to test](#how-to-test)
  - [Image Tags](#image-tags)
    - [Tagging strategy](#tagging-strategy)
    - [Weekly image refresh](#weekly-image-refresh)
  - [Volumes / Runtime Configuration](#volumes--runtime-configuration)
    - [Choosing slice size and memory](#choosing-slice-size-and-memory)
  - [Usage Example](#usage-example)
  - [run-backup.sh](#run-backupsh)
    - [Baked-in config file](#baked-in-config-file)
    - [PyPI .darrc](#pypi-darrc)
    - [Logs to standard output](#logs-to-standard-output)
    - [Default directory layout](#default-directory-layout)
    - [Image used](#image-used)
    - [Backup Definitions](#backup-definitions)
      - [Usage](#usage)
      - [How It Works Internally](#how-it-works-internally)
      - [Example](#example)
    - [Common Pitfalls](#common-pitfalls)
    - [Basic usage](#basic-usage)
  - [🔍 Discover Image Metadata](#-discover-image-metadata)
    - [1. Check Tool Versions](#1-check-tool-versions)
    - [2. Inspect Image Labels](#2-inspect-image-labels)
    - [3. List Available Image Tags](#3-list-available-image-tags)
  - [Image deep diving](#image-deep-diving)
  - [Common `dar-backup` commands](#common-dar-backup-commands)
    - [Full backup](#full-backup)
    - [Diff backup (requires prior FULL)](#diff-backup-requires-prior-full)
    - [Incremental backup (requires DIFF)](#incremental-backup-requires-diff)
    - [List available archives](#list-available-archives)
    - [List contents of a backup](#list-contents-of-a-backup)
    - [Restore](#restore)
  - [Using the Makefile](#using-the-makefile)
    - [Testing Released Images from Docker Hub](#testing-released-images-from-docker-hub)
    - [Releasing a New Version](#releasing-a-new-version)
    - [Recommended Release Workflow](#recommended-release-workflow)
  - [Roadmap](#roadmap)
    - [Version 1.0](#version-10)
    - [Version 1.1](#version-11)
    - [Version 1.2](#version-12)
    - [Other tasks](#other-tasks)
  - [Software this project benefits from](#software-this-project-benefits-from)

## Preserve the restore environment with your archives

Long-term backups need more than durable data. They also need a practical way to run the software required to inspect, verify, repair, and restore that data.

A DAR archive is intentionally portable, and `dar` itself remains the essential restore tool. The container adds another layer of resilience by preserving a complete, known-working environment containing:

- `dar`
- `dar-backup`
- PAR2 tooling
- Python and required runtime libraries
- the image's baked-in configuration
- build metadata identifying the exact component versions

For a backup intended to survive many years, preserve the image **as data**, not merely as a Docker Hub tag.

A typical workflow is:

```bash
# Pin a released image
VERSION=0.5.27
IMAGE=per2jensen/dar-backup:${VERSION}

# Pull the exact version
docker pull "$IMAGE"

# Save it as a portable compressed artifact
docker save "$IMAGE" | gzip > "dar-backup-image-${VERSION}.tar.gz"
```

Years later, on a machine with a compatible container runtime:

```bash
gunzip -c dar-backup-image-0.5.27.tar.gz | docker load
docker run --rm --entrypoint dar per2jensen/dar-backup:0.5.27 --version
```

The supplied [`scripts/save-dar-backup-image.sh`](scripts/save-dar-backup-image.sh)
automates the pull and `docker save` operation. It is intended for cron or a
systemd timer and saves a new archive when build history gains a higher-numbered
release or weekly refresh.

The current helper is an availability tool, not a complete provenance archiver.
It does not yet compare the pulled tag with the recorded digest, run Cosign,
write a checksum for the compressed archive, or preserve the build-history
record, SBOM, signature, and attestation beside it. Cosign material stored in the
registry is not included by `docker save`. Until the helper implements those
checks, verify the immutable digest and Cosign identity as described below, save
the relevant evidence beside the archive, and generate a checksum yourself:

```bash
sha256sum "dar-backup-image-${VERSION}.tar.gz" \
  > "dar-backup-image-${VERSION}.tar.gz.sha256"
sha256sum --check "dar-backup-image-${VERSION}.tar.gz.sha256"
```

Container images are architecture-specific. Record the image architecture with
`docker image inspect --format '{{.Architecture}}' "$IMAGE"` and ensure the
future recovery host can run it natively or through tested emulation.

The practical preservation model is therefore:

```text
DAR archive slices
        +
PAR2 recovery data
        +
dar_manager catalogs
        +
documentation
        +
saved versioned dar-backup image
        =
a self-contained recovery set
```

This does **not** mean Docker Hub should be treated as part of your disaster-recovery dependency chain. The opposite is the goal: save the image locally so recovery does not depend on Docker Hub, PyPI, Ubuntu repositories, the original host, or this GitHub repository still being available.

The signed image digest, SBOM, build history, and Rekor record provide provenance
only when they are preserved and verified with the image; the locally saved image
provides availability.

## Hands-on Demo: `dar-backup` in a Container

Curious how it all works in practice?

Check out the [step-by-step demo](https://github.com/per2jensen/dar-backup-image/blob/main/doc/demo-containerized-dar-backup.md), which walks through:

- A full backup from mounted directories
- Archive listing and contents inspection
- Selective file restore (e.g., `.JPG` only)
- Output logs, par2 generation, and verification

All performed using `docker run`, no host installation required.

## `dar` versions

Starting with `dar-backup-image` **0.5.15**, `dar` (v2.7.18) is compiled from source rather than using Ubuntu 24.04’s older package.

The pinned `dar` release is compiled with the feature set verified by this
project, including zstd, lz4, Argon2, GPGME, and remote repository support.

The [Dockerfile](https://github.com/per2jensen/dar-backup-image/blob/main/Dockerfile) verifies the source tarball using **Denis Corbin’s GPG key**, checks all critical features, and only includes the built binary if everything passes.

To view the embedded `dar` version:

```bash
docker run -it --entrypoint /usr/local/bin/dar dar-backup:<tag> --version
```

Expected (abridged) output for tag `0.5.16`, confirming core capabilities:

```bash
 dar version 2.7.19, Copyright (C) 2002-2025 Denis Corbin

 Using libdar 6.8.3 built with compilation time options:
   gzip compression (libz)      : YES
   Strong encryption (libgcrypt): YES
   Public key ciphers (gpgme)   : YES
   Large files support (> 2GB)  : YES
   Remote repository (libcurl)  : YES (HTTPS, zstd, SSH, HTTP/2)
```

<a name="dockerhub-builds"></a>
## Recent releases uploaded to Docker Hub

> Weekly image refreshes (`:latest`) are not listed here, see the full audit trail in [build-history.json](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json).

<!-- BEGIN GENERATED RELEASE TABLE -->
| Tag | `dar-backup` | `dar` | Release date | Git Revision | Docker Hub | Note |
|---|---|---|---|---|---|---|
| 0.9.1 | 1.1.11 | 2.7.21 | 2026-08-26 | 5576be82b9fedf44df6c9e3d0eb6b6c274ec5274 | [tag:0.9.1](https://hub.docker.com/layers/per2jensen/dar-backup/0.9.1/images/sha256:5a50b74b12ffb6effa52d0095524817529e7e70b88bb385e8e018f9897063750) | - |
| 0.9.0 | 1.1.11 | 2.7.21 | 2026-08-16 | cfaadb1 | [tag:0.9.0](https://hub.docker.com/layers/per2jensen/dar-backup/0.9.0/images/sha256:3dc9c3240c1a51498504e0cd8f585b95fdeef12a9caf76bbab1b504ceb28fee2) | - |
| 0.5.28 | 1.1.10 | 2.7.21 | 2026-07-08 | c2b576e | [tag:0.5.28](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.28/images/sha256:1f8df16b31f7e5d019c3024d190158ab4adf1ad51cfd4739d0c257208c5cb731) | - |
| 0.5.27 | 1.1.9 | 2.7.21 | 2026-07-06 | 1948e6c | [tag:0.5.27](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.27/images/sha256:3b40cfbce68cbdc311f0cec9e8e8e7eb012b929bfb8a4ae415058ebbd346420e) | - |
| 0.5.26 | 1.1.8 | 2.7.21 | 2026-06-12 | 5aedf28 | [tag:0.5.26](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.26/images/sha256:eabf8f0f2bc805655b9258617eb2b76fe68b1160ac8ff8975c412b24b36575d9) | - |
<!-- END GENERATED RELEASE TABLE -->

The table is generated from `doc/build-history.json`. Refresh it at any time
with `python3 scripts/update_readme_releases.py`, or verify it without writing
with `python3 scripts/update_readme_releases.py --check`.

## Release Pipeline and Supply Chain Security

Every image released to Docker Hub is produced by a fully automated GitHub Actions workflow, no manual `docker push`, no local machine involvement. The pipeline enforces a strict sequence of gates before any image becomes publicly available.

### Pipeline steps

1. **Build**, The `dar-backup:dev` image is built using the repository's version pins. DAR is compiled from its GPG-verified source tarball; release images install the pinned `dar-backup` package from PyPI.
2. **Test**, The full pytest suite runs against the dev image. The pipeline halts if any test fails.
3. **Finalize**, The tested dev image is converted to the release tag with corrected OCI version and reference labels. Its application filesystem is retained without rebuilding packages.
4. **Verify**, Focused checks validate OCI labels, the embedded `dar-backup --version`, the exact application revision, and the SHA-256 of `/LICENSE` before publication. The full pytest suite is not repeated against the relabeled image.
5. **SBOM**, [Syft](https://github.com/anchore/syft) generates a CycloneDX JSON Software Bill of Materials from the local image before it leaves the runner.
6. **Vulnerability scan**, [Grype](https://github.com/anchore/grype) scans the SBOM and **fails the release if any High or Critical vulnerability is found**. Results are uploaded to the GitHub Security tab as SARIF.
7. **Candidate push**, Only the immutable version tag is initially pushed to Docker Hub; `:latest` still identifies the previous known-good image.
8. **Cosign signing**, The candidate is signed by digest (not by mutable tag) using [cosign](https://github.com/sigstore/cosign) keyless mode.
9. **SBOM attestation**, The SBOM is attached to that digest as a signed in-toto attestation via cosign.
10. **Remote sanity check**, The immutable digest is pulled back from Docker Hub and executed. Its `dar-backup --version` output and OCI image-version label must match exactly.
11. **Promotion**, Only the remotely verified digest is pushed as `:latest`; `:latest` is then pulled and required to resolve to the signed digest.
12. **Rollback**, If the candidate push, signing, attestation, or remote sanity check fails, the attempted unverified version tag is removed and the previous `:latest` remains untouched.

Manual releases and weekly image refreshes use the same tested publication
component and a shared concurrency lock, so their signing, rollback, remote
verification, `:latest` promotion, and always-run Docker credential cleanup
cannot drift apart or race.

### What cosign keyless signing provides

Keyless signing means the project does not manage or store a **long-lived signing
private key** in GitHub Secrets or on disk. Cosign generates an ephemeral key for
the signing operation, and [Fulcio](https://github.com/sigstore/fulcio) issues a
short-lived certificate bound to GitHub's OIDC identity for the workflow run.

Every signature is permanently recorded in [Rekor](https://github.com/sigstore/rekor), Sigstore's public, append-only transparency log. This means:

- **The signing identity is public and auditable**, the Rekor entry proves exactly which GitHub workflow, repository, branch, and run produced the signature.
- **Signing events are tamper-evident**, inclusion in the append-only log makes
  unexpected or inconsistent events auditable; it does not make compromised OIDC
  identities, workflows, or signing infrastructure impossible.
- **No long-lived project key management burden**, there is no persistent project
  signing key to rotate or retain.
- **Anyone can verify identity and content**, without an account or contacting the
  author. Verify an immutable digest; Docker Hub remains a distribution and
  availability dependency until the image and evidence are archived locally.

### Verifying an image yourself

```bash
cosign verify per2jensen/dar-backup:<tag> \
  --certificate-identity-regexp='^https://github\.com/per2jensen/dar-backup-image/\.github/workflows/(release|image-refresh)\.yml@refs/heads/main$' \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
```

A successful verification proves the image was signed on `main` by this
repository's manual-release or weekly-refresh workflow. Verification should use
the immutable digest recorded in `doc/build-history.json` when auditing a
specific publication.

### Verifying the SBOM attestation

```bash
cosign verify-attestation per2jensen/dar-backup:<tag> \
  --type cyclonedx \
  --certificate-identity-regexp='^https://github\.com/per2jensen/dar-backup-image/\.github/workflows/(release|image-refresh)\.yml@refs/heads/main$' \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  | jq '.payload | @base64d | fromjson | .predicate'
```

This retrieves and verifies the signed CycloneDX SBOM attached to the image, listing every package and library bundled inside.

### Inspecting the Rekor transparency log entry

Each release summary in the GitHub Actions tab includes a direct link to the Rekor entry for that release, for example:

```
https://search.sigstore.dev/?logIndex=1273042416
```

The entry records the signing certificate, the image digest that was signed, the GitHub workflow identity, the run URL, and the exact commit SHA, providing a complete, tamper-evident audit trail from source code to published image.

---

## Understanding Volume Mounts and Backup Definitions

The `-v` flag that maps host directories into the container is the key decision that controls
how many backup definitions you can use, and which host paths are reachable at all.

In short:

- **Map host `/` → container `/data` read-only**, the entire host tree is visible;
  multiple definitions can target different subtrees, but the backup destination
  and special filesystems can also reappear below `/data`. Use explicit exclusions.
- **Map a single subdirectory → container `/data` read-only**, only that directory
  is visible inside the container.
- **Map several sources to distinct paths below `/data` read-only**, multiple
  definitions work without exposing the full host; this is the preferred
  multi-source layout.

See **[doc/dar-backup-mount-scenarios.md](doc/dar-backup-mount-scenarios.md)** for a full explanation
with diagrams, worked examples, and a comparison table.

## Useful links

| Topic| Link   |
| -----| ------ |
| `dar-backup`       | [dar-backup on GitHub](https://github.com/per2jensen/dar-backup) |
| `dar-backup-image` | [dar-backup-image](https://github.com/per2jensen/dar-backup-image)|
| `Docker Hub repo`  | [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags) |
| `dar`              | [Disk ARchive](https://dar.sourceforge.io/)|

---

## License

`dar-backup-image` is licensed under `GPL-3.0-or-later`.

The complete license text is available in the [repository LICENSE file](https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE)
and is embedded in every image at `/LICENSE`. Print it without installing or starting
`dar-backup`:

Copyright and licensing information is also recorded per file using
[SPDX](https://spdx.dev/) and the [REUSE specification](https://reuse.software/).
Clonepulse files retain their MIT licence, while bundled upstream DAR source
archives retain their upstream GPL-2.0-or-later licensing. Run `reuse lint` and
`python3 scripts/validate_license_headers.py` to validate the complete policy.

```bash
docker run --rm --entrypoint cat per2jensen/dar-backup:latest /LICENSE

# The release and refresh workflows require this exact SHA-256 before publishing.
docker run --rm --entrypoint sha256sum \
  per2jensen/dar-backup:latest /LICENSE
# 3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986  /LICENSE
```

## Docker Hub image repo

You can see publicly available `dar-backup` docker images on [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags).

Those fond of curl can do this:

```bash
curl -s https://hub.docker.com/v2/repositories/per2jensen/dar-backup/tags | jq '.results[].name'
```

## Description

A minimal, Dockerized backup runner using dar (Disk ARchive) and dar-backup, ready for automated or manual archive creation and restore.

The image is tested by the full CI pipeline on pushes to `main` and on pull
requests targeting `main`. Weekly
refreshes keep `:latest` current with Ubuntu updates and reject images with any
known High or Critical vulnerability detected by the configured Grype scan.

This image includes:

- dar
- par2
- python3
- setpriv
- [dar-backup](https://github.com/per2jensen/dar-backup) (my `dar` Python based wrapper)
- Clean Ubuntu 24.04 base; image size varies with the pinned packages and architecture
- Explicit non-root execution and privilege drop via `setpriv`

## Directory Layout and Permissions

The `run-backup.sh` script uses a standardized directory structure to ensure backups work consistently across environments. These directories are host-mounted into the container so that all backup archives, definitions, and restored files remain accessible outside Docker.

By default, the script expects (or creates) the following structure relative to `WORKDIR`:

- `$WORKDIR/backups` → Mounted as `/backups` (DAR archives and logs)  
- `$WORKDIR/backup.d` → Mounted as `/backup.d` (backup definitions; current preflight requires write access)
- `$WORKDIR/data` → Mounted read-only as `/data` (source data to back up)
- `$WORKDIR/restore` → Mounted as `/restore` (restored files)

### How Directory Overrides Work

The script resolves its directory paths in the following priority order:

1. If an explicit directory environment variable is set (`DAR_BACKUP_DIR`, `DAR_BACKUP_D_DIR`, `DAR_BACKUP_DATA_DIR`, or `DAR_BACKUP_RESTORE_DIR`), that value is used.
2. Otherwise, if `WORKDIR` is set, each directory defaults to a subdirectory of `WORKDIR` (e.g., `$WORKDIR/backups`).
3. If `WORKDIR` is unset or empty, the script exits before creating directories or running Docker.

This allows full flexibility: you can set `WORKDIR` once for a standard layout, or override specific directories individually.

### UID and GID Behavior

Files created through `run-backup.sh` use the selected numeric host UID and GID:

- By default, `RUN_AS_UID` and `RUN_AS_GID` are set to your current UID and GID.
- These are passed to Docker via `--user "$RUN_AS_UID:$RUN_AS_GID"`.
- Running as `root` (UID 0) is disallowed; the script will exit with an error.
- You can override these values for special cases, such as:

  - **Group-based backups:**  
    `RUN_AS_GID=$(getent group backupgrp | cut -d: -f3)`  
    Ensures all archives are group-writable.

  - **Service accounts:**  
    `RUN_AS_UID=1050 RUN_AS_GID=1050 ./scripts/run-backup.sh -t FULL`
    Matches ownership for automated or scheduled jobs.

### Recommended Directory Layouts

Here are three common configurations, depending on your use case:

#### Personal (All Under Your Home Directory)

For single-user systems:

```bash
WORKDIR=$HOME/dar-backup
$HOME/dar-backup/backups # DAR archives and logs
$HOME/dar-backup/backup.d # Backup definition files
$HOME/dar-backup/data # Source data to back up
$HOME/dar-backup/restore # Restored files
```

Permissions: Owned entirely by your user (default behavior).

#### Shared Group Setup (Multiple Users)

For teams or shared servers, use a group to manage permissions:

```bash
WORKDIR=/srv/dar-backup

# Group ownership

chown -R :backupgrp /srv/dar-backup
chmod -R 2770 /srv/dar-backup
```

Environment for group-based runs:

```bash
RUN_AS_UID=$(id -u)
RUN_AS_GID=$(getent group backupgrp | cut -d: -f3)
```

All members of `backupgrp` can write backups while keeping data private.

#### Dedicated Service Account (Automated Backups)

For scheduled or service-based backups:

```bash
WORKDIR=/mnt/backups
```

Owned by a dedicated backup user (UID 1050:GID 1050)

Run with:

```bash
RUN_AS_UID=1050 RUN_AS_GID=1050 ./scripts/run-backup.sh -t FULL
```

This ensures consistent ownership for cron jobs or automated workflows.

For full environment variable documentation, see the header comments in [`scripts/run-backup.sh`](scripts/run-backup.sh).

## Environment Variables

Here’s a quick reference for all environment variables used by the script:

| Variable                | Default                  | Purpose                                                        |
|-------------------------|--------------------------|----------------------------------------------------------------|
| `IMAGE`                 | `per2jensen/dar-backup:latest` | Docker image tag to use for the backup container.        |
| `WORKDIR`               | Required                 | Base directory for all backup-related paths.                  |
| `RUN_AS_UID`            | Current user's UID       | UID passed to Docker to avoid root-owned files.               |
| `RUN_AS_GID`            | Current user's GID       | GID passed to Docker for correct file group ownership.        |
| `DAR_BACKUP_DIR`        | `$WORKDIR/backups`       | Host directory for DAR archives and logs (mounted at `/backups`). |
| `DAR_BACKUP_D_DIR`      | `$WORKDIR/backup.d`      | Host directory for backup definitions (mounted at `/backup.d`; current preflight requires write access). |
| `DAR_BACKUP_DATA_DIR`   | `$WORKDIR/data`          | Host source directory (mounted read-only at `/data`).          |
| `DAR_BACKUP_RESTORE_DIR`| `$WORKDIR/restore`       | Host directory for restored files (mounted at `/restore`).     |
| `DOCKER_PULL`           | `false`                  | Set exactly to `true` to pull `IMAGE` before running; `true` and `false` are the only valid values. |

For details on behavior, UID/GID handling, and usage examples, see the comments in [`scripts/run-backup.sh`](scripts/run-backup.sh).

## How to test

See [dev.md](dev.md) for development-image build and test instructions.

## Image Tags

All images are published to [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags).

Every build, whether a release or a scheduled refresh, is recorded in [build-history.json](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json).

### Tagging strategy

| Tag            | Description                                                              | Docker Hub | Example Usage  |
|----------------|--------------------------------------------------------------------------|------------|----------------|
| `:latest`      | Most recently verified release or refresh; mutable by design             | ✅ Yes     | `docker pull per2jensen/dar-backup:latest` |
| `:x.y.z`       | Stable semantic-versioned release                                        | ✅ Yes     | `docker pull per2jensen/dar-backup:1.0.0` |
| `:x.y.z-rcN`   | Release candidate; not selected as a weekly refresh base                 | ✅ Yes     | `docker pull per2jensen/dar-backup:1.0.0-rc1` |
| `:x.y.z-N`     | Numeric weekly refresh of stable release `x.y.z`                         | ✅ Yes     | `docker pull per2jensen/dar-backup:1.0.0-1` |
| `:dev`         | Local development version; may be incomplete                             | ❌ No      | `docker run dar-backup:dev` |


For normal day-to-day use, `:latest` is convenient because it tracks the most
recently verified publication. For reproducible operation and recovery, use a
versioned tag or, preferably, its immutable digest.

Publishing a release candidate also promotes its verified digest to `:latest`.
Weekly refreshes then pause while that RC is the newest build-history record.
Operators who require stable-only deployments must pin a stable version or digest
instead of following `:latest` during an RC window.

For **long-term recovery**, do not preserve only the `:latest` reference. Save a specific versioned image, for example `:0.5.27`, as a Docker/OCI archive alongside the backup set. A mutable registry tag is a locator; the saved image is the recovery artifact.

### Weekly image refresh

The refresh workflow runs every Saturday. It selects the newest build-history
record only when its tag is a stable `x.y.z` release or an existing numeric
`x.y.z-N` refresh. If the newest record is a prerelease such as `x.y.z-rc1`, the
workflow stops without publishing or moving `:latest`. For an eligible base,
each refresh:

- Rebuilds the exact application source commit recorded for that base, while picking up Ubuntu base-image and package updates
- Runs the full test suite, the pipeline halts if any test fails
- Refuses to reuse an existing Git or Docker Hub refresh tag and fails closed if
  remote tag availability cannot be established
- Requires the finalized image's OCI revision label to equal the complete recorded
  application SHA and verifies the baked `/LICENSE` SHA-256
- Scans with [Grype](https://github.com/anchore/grype), **the refresh is aborted if any High or Critical vulnerability is found**
- Signs the image with [cosign](https://github.com/sigstore/cosign) keyless signing and records the entry in the [Rekor](https://github.com/sigstore/rekor) transparency log
- Attaches a signed CycloneDX SBOM attestation
- Publishes as both `:latest` and a versioned refresh tag (e.g. `:0.5.22-1`, `:0.5.22-2`)
- Atomically publishes the build-history commit and its annotated Git tag; the
  annotation records the immutable application SHA and signed image digest
- Updates the [cosign badge](https://github.com/per2jensen/dar-backup-image/blob/main/doc/cosign_badge.json), `failed` means the most recent signing attempt was rejected and rolled back; the previously published `:latest` may remain valid

The [build-history.json](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json) file contains the full audit trail for every release and refresh, including digests, Rekor log entries, and Grype scan results.

## Volumes / Runtime Configuration

The default dar-backup.conf baked into the image assumes the directories mentioned below.

The locations should be mounted with actual directories on your machine for backups.

|Directories in file system| Directories in container| Purpose   |
|------------------------- | ------------------------| ---------------------------------------------|
|/some/dir/to/backup/      | `/data`                 | Source directory for backup                  |
|/keep/backups/here/       | `/backups`              | `dar` archives and .par2 files are put here  |
|/restore/tests/           | `/restore`              | Optional restore target                      |
|[/backup/definitions/](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#backup-definition-example)      | `/backup.d`             | Contains backup definition files             |

The mapping between physical directories on your file system and the expected directories inside the container is performed by the `-v /physical/dir:/container/dir` options  (see example below).

> 💡 **How you mount `/data` determines which backup definitions work.**
> See [Understanding Volume Mounts and Backup Definitions](#understanding-volume-mounts-and-backup-definitions).

### Choosing slice size and memory

`--slice` sets the maximum size of each numbered DAR archive file. Choose it
primarily for storage, transfer, verification, and repair granularity:

- Smaller slices produce more `.dar` and PAR2 files, but each damaged or
  transferred unit is smaller.
- Larger slices reduce file count, but make each PAR2 creation, verification, or
  repair operation cover a larger input and can increase both runtime and peak
  memory.
- Slice size is not a direct DAR memory reservation. DAR documents memory growth
  separately for compression block size and thread count; there is no supported
  rule such as “10 GiB slices require 10 GiB RAM.” See the
  [DAR manual](https://dar.sourceforge.io/doc/man/dar.html).

`dar-backup` runs PAR2 once per DAR slice. This bounds each PAR2 problem by one
slice rather than the complete archive, but it also means slice size materially
affects the largest PAR2 operation. The bundled PAR2 0.8.1 selects a default
memory limit from detected physical memory when no `-m` option is supplied. A
container memory limit may be lower than that detected value, so test the chosen
slice size under the same Docker memory constraints used in production and watch
for OOM termination.

The 5G, 7G, 10G, and 12G values elsewhere in this repository are examples, not
universal recommendations. Start conservatively on memory-constrained hosts and
measure a representative FULL backup plus PAR2 creation and repair before
increasing the size. The [large-scale test guide](doc/demo-large-scale-test.md)
explains what its peak-memory measurements do and do not prove.

The tracked large-scale history can also be explored through the read-only
[Datasette metrics dashboard](doc/metrics-dashboard.md). From a checkout, run
`./run_metrics_dashboard.sh` and open the localhost URL printed by the launcher.

## Usage Example

Determine whether you want to build an image yourself or use one from Docker
Hub. Development-image build instructions are in [dev.md](dev.md).

```bash
# Use your own locally built image
export IMAGE=dar-backup:dev

# Or use the most recently verified publication from Docker Hub
export IMAGE=per2jensen/dar-backup:latest

# Or pin to a specific version
VERSION=0.5.25.1; export IMAGE=per2jensen/dar-backup:${VERSION}
```

Now run `dar-backup` in the container

```bash
# Run it (from script or manually)
# Configuration
export DATA_DIR=/tmp/test-data          # the data to backup
export BACKUP_DIR=/tmp/test-backups     # the directory that keeps the backups
export RESTORE_DIR=/tmp/test-restore    # the directory used for restore tests during backup verification
export BACKUP_D_DIR=/tmp/test-backup.d  # the directory keeping the `backup definitions`

mkdir -p "$DATA_DIR" "$BACKUP_DIR" "$RESTORE_DIR" "$BACKUP_D_DIR"
cat > "$BACKUP_D_DIR/default" <<'EOF'
-am
-R /data
-z5
-n
--slice 7G
--cache-directory-tagging
EOF

docker run --rm \
  -e RUN_AS_UID="$(id -u)" \
  -e RUN_AS_GID="$(id -g)" \
  -v "$DATA_DIR":/data:ro \
  -v "$BACKUP_DIR":/backups \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" \
  -F --log-stdout
```

The image automatically uses [`/etc/dar-backup/dar-backup.conf`](https://github.com/per2jensen/dar-backup-image/blob/main/dar-backup.conf) unless you override it.

To use another config file you have multiple options:

- Modify the [baked-in](https://github.com/per2jensen/dar-backup-image/blob/main/dar-backup.conf) and build a new image.
- Use `--config` to select another file, for example
  `/backups/dar-backup.conf`. With the mounts above, place that file at
  `$BACKUP_DIR/dar-backup.conf` on the host.
- Let DAR_BACKUP_CONFIG point to a config file.

The container uses `setpriv` to drop root privileges. Pass
both `-e RUN_AS_UID="$(id -u)"` and `-e RUN_AS_GID="$(id -g)"` when
invoking Docker directly. `run-backup.sh` supplies both automatically.

## run-backup.sh

This script runs a backup using a dar-backup Docker image.

It runs a backup based on the specified type (FULL, DIFF, INCR)
with the following features:

### Baked-in config file

Uses the baked-in [dar-backup.conf](dar-backup.conf); see the
[`dar-backup` configuration documentation](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#config).

### PyPI .darrc

Uses the .darrc file from the [PyPI package](https://pypi.org/project/dar-backup/) added to the image,
   see image [details here](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json)
  
   .darrc [contents](https://github.com/per2jensen/dar-backup/blob/main/v2/src/dar_backup/.darrc)

### Logs to standard output

It prints log messages to standard output.

### Default directory layout

Expected directory structure when running this script:

```text
   WORKDIR/
     ├── backups/           # Where backups are stored
     ├── backup.d/          # Backup definitions
     ├── data/              # Data to backup
     └── restore/           # Where restored files will be placed
```

`WORKDIR` is required and becomes the base directory. The script fails clearly
when it is unset or empty.

These directories are host-mounted into the container so your data and archives remain accessible:

| Host Directory (default)      | Container Mount  | Purpose                           |
|--------------------------------|------------------|-----------------------------------|
| `$WORKDIR/backups`             | `/backups`       | DAR archives and log files       |
| `$WORKDIR/backup.d`            | `/backup.d`       | Backup definitions; current preflight requires write access |
| `$WORKDIR/data`                | `/data` (read-only) | Source data for the backup     |
| `$WORKDIR/restore`             | `/restore`       | Destination for restore tests    |

You can override any of these paths by setting the environment variables:
`DAR_BACKUP_DIR`, `DAR_BACKUP_D_DIR`, `DAR_BACKUP_DATA_DIR`, `DAR_BACKUP_RESTORE_DIR`.  
If an override is unset, its corresponding directory below `WORKDIR` is used.

More info on [backup definitions in general](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#backup-definition-example)

View [supplied `default` backup definition](https://github.com/per2jensen/dar-backup-image/blob/main/doc/backup-definitions/default)

### Image used

If `IMAGE` is not set, the script defaults to
`per2jensen/dar-backup:latest`.

See the available images on [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags).

If `RUN_AS_UID` or `RUN_AS_GID` is not set, it defaults to the current
user's numeric UID or GID. Running the helper as root is not allowed.

### Backup Definitions

The `run-backup.sh` script supports selecting a specific backup definition file, which allows you to maintain multiple dataset or policy definitions.

Each backup definition file resides in:

$DAR_BACKUP_D_DIR (default: $WORKDIR/backup.d)

and is automatically mounted into the container at `/backup.d`.

> **Note on daily backups per definition:**  
> `dar-backup` will only create one `FULL`, one `DIFF`, and one `INCR` backup **per definition per calendar day**.  
> - You can run all three types (FULL → DIFF → INCR) on the same day.  
> - A second run of the *same type* (e.g., another FULL) will be skipped to avoid overwriting the existing archive.
> - To force a new run, use [`cleanup`](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#cleanup-options)
>   so DAR slices, PAR2 data, and catalogue state are handled consistently. Do
>   not delete only the `.dar` files.

#### Usage

To specify a backup definition, use the `-d` or `--backup-definition` option:

```bash
WORKDIR=/path/to/workdir ./scripts/run-backup.sh -t FULL -d my-backup-definition
```

This instructs `dar-backup` to load:

$DAR_BACKUP_D_DIR/my-backup-definition

instead of the default definition (`default`).

If no `-d` option is supplied, the script falls back to the default definition.  
The `run-backup.sh` script generates a minimal default definition file at:

$DAR_BACKUP_D_DIR/default

if none exists.

#### How It Works Internally

The script passes the chosen definition to `dar-backup` using:

```bash
--backup-definition "<name>"
```

The script constructs a Bash array so an optional definition remains one safely
quoted argument:

```bash
DOCKER_ARGS=( "$BACKUP_FLAG" "--log-stdout" "--verbose" )
if [[ -n "$BACKUP_DEF" ]]; then
  DOCKER_ARGS+=( "--backup-definition" "$BACKUP_DEF" )
fi

docker run ... "$IMAGE" "${DOCKER_ARGS[@]}"
```

This:

- Adds `--backup-definition "<name>"` if `BACKUP_DEF` is non-empty.
- Skips it entirely if no `-d` was provided (dar-backup then uses the default definition).

#### Example

1. Create a new definition file:

```bash
mkdir -p "$HOME/dar-backup/backup.d"
cat > "$HOME/dar-backup/backup.d/projects" <<'EOF'
-R /data/projects
-z5
-am
--slice 5G
EOF
```

2. After creating a FULL backup for the definition, run a differential backup:

```bash
WORKDIR=$HOME/dar-backup ./scripts/run-backup.sh -t DIFF -d projects
```

The backup will:
- Store archives in `$HOME/dar-backup/backups`.
- Use `/backup.d/projects` as the definition.
- Retain ownership based on `RUN_AS_UID` and `RUN_AS_GID`.

### Common Pitfalls

> - **Why is my backup skipped?**  
>   Only one `FULL`, one `DIFF`, and one `INCR` backup can be created per definition per day.  
>   If a run is skipped, use the documented `cleanup` command; do not remove
>   only the `.dar` files and leave associated state behind.
>
> - **Permission issues on host files?**  
>   Ensure `RUN_AS_UID` and `RUN_AS_GID` match the desired owner.  
>   If unsure, run `id -u` and `id -g` to get your UID and GID.
>
> - **Definition not found?**  
>   Make sure your `backup.d/<name>` file exists (or let the script auto-create `default`).

### Basic usage

```bash
WORKDIR=/path/to/your/workdir \
IMAGE=per2jensen/dar-backup:latest \
./scripts/run-backup.sh -t FULL -d backup_definition
```

## 🔍 Discover Image Metadata

Learn what's inside the `dar-backup` image: program versions, build metadata, and available versions.

### 1. Check Tool Versions

Run the image with different entrypoints to check the bundled versions of `dar-backup`, `dar`, and `par2`:

```bash
VERSION=0.5.25.1; IMAGE=per2jensen/dar-backup:${VERSION}

# dar-backup version
docker run --rm --entrypoint "dar-backup" "$IMAGE" -v

# dar version
docker run --rm --entrypoint dar "$IMAGE" --version

# par2 version
docker run --rm --entrypoint par2 "$IMAGE" --version

# Or get them all in one go:
docker run --rm --entrypoint "" "$IMAGE" \
  bash -c "dar-backup -v; dar --version; par2 --version"
```

### 2. Inspect Image Labels

```bash
docker pull per2jensen/dar-backup:latest
docker inspect per2jensen/dar-backup:latest | jq '.[0].Config.Labels'
```

Inspect the provenance-critical labels without relying on a stale example:

```bash
docker inspect per2jensen/dar-backup:latest \
  | jq '.[0].Config.Labels | {
      image_version: .["org.opencontainers.image.version"],
      source_revision: .["org.opencontainers.image.revision"],
      base_digest: .["org.opencontainers.image.base.digest"],
      dar_backup_version: .["org.dar-backup.version"],
      dar_version: .["org.dar.version"],
      install_source: .["org.dar-backup.install-source"],
      license: .["org.opencontainers.image.licenses"]
    }'
```

Current release and refresh workflows require `source_revision` to be the full
application commit SHA and `install_source` to be `pypi`.

### 3. List Available Image Tags

```bash
# Show first 100 available tags
curl -s 'https://hub.docker.com/v2/repositories/per2jensen/dar-backup/tags?page_size=100' \
  | jq -r '.results[].name' | sort -V
```

## Image deep diving

Although `dar-backup` is the primary CLI inside the container, you can also run dar directly from the image to take manual backups or inspect archives, perfect for advanced workflows or testing.

Here's a minimal example of how to use dar directly:

```bash
export DATA_DIR=/tmp/test-data
export BACKUP_DIR=/tmp/test-backups
export VERSION=0.5.25.1
export IMAGE=per2jensen/dar-backup:${VERSION}
mkdir -p "$DATA_DIR" "$BACKUP_DIR"
touch "$DATA_DIR/TEST.txt"

docker run --rm \
  -v "$DATA_DIR":/data:ro \
  -v "$BACKUP_DIR":/backups \
  --entrypoint dar \
  "$IMAGE" -c /backups/myarchive -R /data
```

Example output

```bash
No terminal found for user interaction. All questions will be assumed a negative answer (less destructive choice), which most of the time will abort the program.

 --------------------------------------------
 1 inode(s) saved
   including 0 hard link(s) treated
 0 inode(s) changed at the moment of the backup and could not be saved properly
 0 byte(s) have been wasted in the archive to resave changing files
 0 inode(s) with only metadata changed
 0 inode(s) not saved (no inode/file change)
 0 inode(s) failed to be saved (filesystem error)
 0 inode(s) ignored (excluded by filters)
 0 inode(s) recorded as deleted from reference backup
 --------------------------------------------
 Total number of inode(s) considered: 1
 --------------------------------------------
 EA saved for 0 inode(s)
 FSA saved for 1 inode(s)
 --------------------------------------------
```

This shows that even without dar-backup, you can still invoke dar manually, helpful for debugging, recovery scenarios, or power-user workflows.

> Tip: You can also run PAR2 directly with `--entrypoint par2` when needed.

## Common `dar-backup` commands

These are arguments to the image's default `dar-backup` entrypoint. Supply the
same mounts and UID/GID settings used for backups:

```bash
RUNTIME_ARGS=(
  -e RUN_AS_UID="$(id -u)"
  -e RUN_AS_GID="$(id -g)"
  -v "$DATA_DIR":/data:ro
  -v "$BACKUP_DIR":/backups
  -v "$RESTORE_DIR":/restore
  -v "$BACKUP_D_DIR":/backup.d
)
```

### Full backup

```bash
docker run --rm "${RUNTIME_ARGS[@]}" "$IMAGE" --full-backup
```

### Diff backup (requires prior FULL)

```bash
docker run --rm "${RUNTIME_ARGS[@]}" "$IMAGE" --differential-backup
```

### Incremental backup (requires DIFF)

```bash
docker run --rm "${RUNTIME_ARGS[@]}" "$IMAGE" --incremental-backup
```

### List available archives

```bash
docker run --rm "${RUNTIME_ARGS[@]}" "$IMAGE" --list
```

### List contents of a backup

```bash
docker run --rm "${RUNTIME_ARGS[@]}" "$IMAGE" --list-contents ARCHIVE_NAME
```

### Restore

```bash
docker run --rm "${RUNTIME_ARGS[@]}" "$IMAGE" --restore ARCHIVE_NAME
```

## Using the Makefile

See [dev.md](dev.md) for the canonical development-image build and test
instructions, including how to install `dar-backup` from a local wheel.

### Testing Released Images from Docker Hub

After publishing a release, test the exact image on Docker Hub (ignoring local builds):

```bash
make IMAGE=per2jensen/dar-backup:0.5.15 test-pulled
```

This:

    Pulls the image from Docker Hub.

    Runs the full pytest suite (no local build).

### Releasing a New Version

Releases are fully automated via the **Manual Docker Release** GitHub Actions workflow, no local `docker push` required.

Dry-run the release locally first (build, test, verify labels, no push):

```bash
make FINAL_VERSION="$(cat IMAGE_VERSION)" dry-run-release
```

This validates:

- The image builds correctly
- Labels and `dar-backup --version` match expected values
- All tests pass

When ready, trigger the release by dispatching the workflow from GitHub Actions
(`workflow_dispatch`). The workflow will:

1. Lock the build to the full commit selected from `main` and validate `IMAGE_VERSION`
2. Build, test, and scan, hard gate on High/Critical vulnerabilities
3. Push `per2jensen/dar-backup:VERSION` as a candidate
4. Sign the candidate and attach its SBOM attestation
5. Roll back a failed candidate without moving the previous `:latest`
6. Promote the successfully signed digest to `:latest`
7. Atomically publish build history, documentation, evidence, and the source-pointing Git tag
8. Create the GitHub Release with non-empty SBOM and SARIF assets

> **Note:** Do NOT manually create the git tag before triggering the workflow, it is created automatically after all steps succeed.

The complete operator procedure, failure-state table, source policy, RC
acceptance gate, and GitHub Release recovery procedure are in
[doc/Release.md](doc/Release.md).

### Recommended Release Workflow

Follow [dev.md](dev.md) to build and test a PyPI-sourced development image.
Before release, validate locally:

```bash
make FINAL_VERSION="$(cat IMAGE_VERSION)" final
make FINAL_VERSION="$(cat IMAGE_VERSION)" dry-run-release
```

`FINAL_VERSION` defaults to `dev` for ordinary development. Release-related
Make targets reject that default and require an exact match with the committed
`IMAGE_VERSION` file. Weekly refreshes use the separate guarded
`refresh-final-noscan` target, which permits only `BASE_VERSION-N` where the
base comes from the latest `doc/build-history.json` entry. The same history
record supplies the application Git revision, which is resolved and checked
out as a full commit SHA. Refreshes intentionally do not consult
`IMAGE_VERSION`.

Trigger the release:

- Set `IMAGE_VERSION` to the new version, update `Changelog.md`, commit and push
- Dispatch the **Manual Docker Release** workflow from GitHub Actions

Verify the published image:

```bash
make IMAGE=per2jensen/dar-backup:x.y.z test-pulled
```

## Roadmap

### Version 1.0

1.0.0-rc1 is expected sometime Septemper 2026, with a 1.0.0 release following relative shortly thereafter.

### Version 1.1

- Integrate DAR 2.8
- Use Ubuntu 26.04 instead of 24.04 as base image and for local development
- Investigate and document compatibility between 1.0 and 1.1 backup archives and restore environments (1.0 uses ubuntu 24.04 / dar-2.7, 1.1 will use ubuntu 26.04 / dar-2.8)

### Version 1.2

- Investigate DAR's encryption features
- Possibly implement a dar supported encryption scheme

### Other tasks

- Investigate deterministic generated test cases so test runs can be reproduced across versions and during debugging

## Software this project benefits from

- [DAR of course :-)](https://dar.sourceforge.io/)
- [Par2](https://github.com/Parchive)
- [Ubuntu](https://ubuntu.com/)
- [Python](https://python.org/)
- [GNU software](https://www.fsf.org/)
