# dar-backup image — reproducible backups and a long-term restore time capsule
<a href="https://github.com/per2jensen/dar-backup-image/releases"><img alt="Tag" src="https://img.shields.io/github/v/tag/per2jensen/dar-backup-image"/></a>
![CI](https://github.com/per2jensen/dar-backup-image/actions/workflows/build-test-scan.yml/badge.svg)
[![Large scale torture test](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/test-report/torture-test-badge.json)](https://github.com/per2jensen/dar-backup-image/blob/main/doc/test-report/large-scale-results.jsonl)
<a href="https://github.com/per2jensen/dar-backup-image/blob/main/doc/DETAILS.md#image-signing-and-supply-chain-verification">
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

`dar-backup-image` packages `dar-backup`, `dar`, PAR2, and their runtime dependencies into a reproducible Docker image.

It has **two equally important purposes**:

1. **Run backups and restores today** in a clean, isolated environment without installing `dar`, Python tooling, or PAR2 on the host.
2. **Preserve a known-working restore environment for the future** by saving a versioned image alongside your archives.

The second use is deliberate: the image is a **restore time capsule**. If you need to recover an archive years from now, you can use the packaged toolchain preserved with the backup instead of hunting for compatible packages or reconstructing an old software environment.

For long-term archival use, save a **specific versioned image** rather than relying only on `:latest`. The mutable `:latest` tag is useful for current operations and receives regular security refreshes; a pinned and locally archived version is the artifact you want to retain with your backups.

A helper script, [`scripts/save-dar-backup-image.sh`](scripts/save-dar-backup-image.sh), is provided for this purpose. It checks the latest released image against [`doc/build-history.json`](doc/build-history.json) and saves the image as a compressed tar archive. Run it periodically and let the restore environment travel with the DAR archives to your backup server, USB copies, or other offsite storage.

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
- `README.md` — the Markdown description embedded in package metadata
- `doc/` — every file included under `dar_backup/doc/` or `dar_backup/docs/`
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

- **Long-term restore time capsule** — preserve a known-working `dar-backup` / `dar` / PAR2 environment with your archives
- **Reproducible backup runner** — no host installation of `dar`, Python tooling, or PAR2 required
- **Self-documenting** — all `dar-backup`, `dar-backup-image`, `dar` and `par2` documentation is included and easily discoverable by future users
- **Versioned and auditable** — released images are tested, scanned, signed, and accompanied by an SBOM
- **Stateless and portable** — archive the image itself and move it with your backup sets
- **FUSE-friendly** — works without root and is suited to user-space mounted storage
- **Built-in configuration** — automatically loads `/etc/dar-backup/dar-backup.conf` unless overridden
- **Ready for automation** — usable from cron, systemd timers, and CI pipelines

> **Current operation vs. long-term preservation**
>
> Use `:latest` when you want the current tested and security-refreshed image.
>
> For disaster recovery years into the future, pin a version and save the image itself alongside your archives.


---

## Table of Contents

- [dar-backup image — reproducible backups and a long-term restore time capsule](#dar-backup-image--reproducible-backups-and-a-long-term-restore-time-capsule)
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
  - [Usage Example](#usage-example)
  - [run-backup.sh](#run-backupsh)
    - [Baked-in config file](#baked-in-config-file)
    - [PyPI .darrc](#pypi-darrc)
    - [3 Logs to stdout](#3-logs-to-stdout)
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
  - [TODO](#todo)
    - [Version 1.0](#version-10)
    - [Version 1.1](#version-11)
    - [Version 1.2](#version-12)
    - [Other tasks](#other-tasks)
  - [Software this project benefits from](#software-this-project-benefits-from)

---

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

The supplied [`scripts/save-dar-backup-image.sh`](scripts/save-dar-backup-image.sh) automates this process. It is intended to be run periodically from cron or a systemd timer and only saves a new image when a new release is available.

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

The signed image digest, SBOM, build history, and Rekor record provide provenance for the preserved environment; the locally saved image provides availability.

---

## Hands-on Demo: `dar-backup` in a Container

Curious how it all works in practice?

Check out the [step-by-step demo](https://github.com/per2jensen/dar-backup-image/blob/main/doc/demo-containerized-dar-backup.md), which walks through:

- A full backup from mounted directories
- Archive listing and contents inspection
- Selective file restore (e.g., `.JPG` only)
- Output logs, par2 generation, and verification

All performed using `docker run` — no host installation required.

---

## `dar` versions

Starting with `dar-backup-image` **0.5.15**, `dar` (v2.7.18) is compiled from source rather than using Ubuntu 24.04’s older package.

`dar` is compiled to provide the **latest features, performance optimizations, and bug fixes** (including full zstd, lz4, Argon2, GPGME, and remote repository support).

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

> Weekly image refreshes (`:latest`) are not listed here — see the full audit trail in [build-history.json](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json).

<!-- BEGIN GENERATED RELEASE TABLE -->
| Tag | `dar-backup` | `dar` | Release date | Git Revision | Docker Hub | Note |
|---|---|---|---|---|---|---|
| 0.9.0 | 1.1.11 | 2.7.21 | 2026-08-16 | cfaadb1 | [tag:0.9.0](https://hub.docker.com/layers/per2jensen/dar-backup/0.9.0/images/sha256:3dc9c3240c1a51498504e0cd8f585b95fdeef12a9caf76bbab1b504ceb28fee2) | - |
| 0.5.28 | 1.1.10 | 2.7.21 | 2026-07-08 | c2b576e | [tag:0.5.28](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.28/images/sha256:1f8df16b31f7e5d019c3024d190158ab4adf1ad51cfd4739d0c257208c5cb731) | - |
| 0.5.27 | 1.1.9 | 2.7.21 | 2026-07-06 | 1948e6c | [tag:0.5.27](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.27/images/sha256:3b40cfbce68cbdc311f0cec9e8e8e7eb012b929bfb8a4ae415058ebbd346420e) | - |
| 0.5.26 | 1.1.8 | 2.7.21 | 2026-06-12 | 5aedf28 | [tag:0.5.26](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.26/images/sha256:eabf8f0f2bc805655b9258617eb2b76fe68b1160ac8ff8975c412b24b36575d9) | - |
| 0.5.25.1 | 1.1.7 | 2.7.21 | 2026-06-10 | 46b3fe8 | [tag:0.5.25.1](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.25.1/images/sha256:092f1895dd31f99b4c240744ad2ffe800b233af509919dd94574325ee2f2038a) | - |
<!-- END GENERATED RELEASE TABLE -->

The table is generated from `doc/build-history.json`. Refresh it at any time
with `python3 scripts/update_readme_releases.py`, or verify it without writing
with `python3 scripts/update_readme_releases.py --check`.

---


## Release Pipeline and Supply Chain Security

Every image released to Docker Hub is produced by a fully automated GitHub Actions workflow — no manual `docker push`, no local machine involvement. The pipeline enforces a strict sequence of gates before any image becomes publicly available.

### Pipeline steps

1. **Build** — The `dar-backup:dev` image is built (version 0.5.22 onwards) from source using the versioned `DAR_VERSION` and `DAR_BACKUP_VERSION` pins in the repository.
2. **Test** — The full pytest suite runs against the dev image. The pipeline halts if any test fails.
3. **Promote** — The tested dev image is re-labeled and promoted to the release tag (e.g. `0.5.22`). No rebuild occurs; the promoted image is byte-for-byte identical to the tested one.
4. **Verify** — OCI labels and the embedded `dar-backup --version` are checked against expected values.
5. **SBOM** — [Syft](https://github.com/anchore/syft) generates a CycloneDX JSON Software Bill of Materials from the local image before it leaves the runner.
6. **Vulnerability scan** — [Grype](https://github.com/anchore/grype) scans the SBOM and **fails the release if any High or Critical vulnerability is found**. Results are uploaded to the GitHub Security tab as SARIF.
7. **Candidate push** — Only the immutable version tag is initially pushed to Docker Hub; `:latest` still identifies the previous known-good image.
8. **Cosign signing** — The candidate is signed by digest (not by mutable tag) using [cosign](https://github.com/sigstore/cosign) keyless mode.
9. **SBOM attestation** — The SBOM is attached to that digest as a signed in-toto attestation via cosign.
10. **Remote sanity check** — The immutable digest is pulled back from Docker Hub and executed. Its `dar-backup --version` output and OCI image-version label must match exactly.
11. **Promotion** — Only the remotely verified digest is pushed as `:latest`; `:latest` is then pulled and required to resolve to the signed digest.
12. **Rollback** — If the candidate push, signing, attestation, or remote sanity check fails, the attempted unverified version tag is removed and the previous `:latest` remains untouched.

Manual releases and weekly image refreshes use the same tested publication
component and a shared concurrency lock, so their signing, rollback, remote
verification, `:latest` promotion, and always-run Docker credential cleanup
cannot drift apart or race.

### What cosign keyless signing provides

Keyless signing means **no private key is stored anywhere** — not in GitHub Secrets, not on disk, not in the workflow. Instead, the signature is produced using a short-lived certificate issued by [Fulcio](https://github.com/sigstore/fulcio) (Sigstore's certificate authority), bound to GitHub's OIDC token for the specific workflow run.

Every signature is permanently recorded in [Rekor](https://github.com/sigstore/rekor), Sigstore's public, append-only transparency log. This means:

- **The signing identity is public and auditable** — the Rekor entry proves exactly which GitHub workflow, repository, branch, and run produced the signature.
- **Signatures cannot be backdated or forged** — the transparency log is immutable.
- **No key management burden** — there is no private key that could be leaked, rotated, or forgotten.
- **Anyone can verify** — without an account, without trusting Docker Hub, without contacting the author.

### Verifying an image yourself

```bash
cosign verify per2jensen/dar-backup:<tag> \
  --certificate-identity-regexp="https://github.com/per2jensen/dar-backup-image" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
```

A successful verification proves the image was signed by the `dar-backup-image` GitHub Actions workflow on the `main` branch — and by nothing else.

### Verifying the SBOM attestation

```bash
cosign verify-attestation per2jensen/dar-backup:<tag> \
  --type cyclonedx \
  --certificate-identity-regexp="https://github.com/per2jensen/dar-backup-image" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  | jq '.payload | @base64d | fromjson | .predicate'
```

This retrieves and verifies the signed CycloneDX SBOM attached to the image, listing every package and library bundled inside.

### Inspecting the Rekor transparency log entry

Each release summary in the GitHub Actions tab includes a direct link to the Rekor entry for that release, for example:

```
https://search.sigstore.dev/?logIndex=1273042416
```

The entry records the signing certificate, the image digest that was signed, the GitHub workflow identity, the run URL, and the exact commit SHA — providing a complete, tamper-evident audit trail from source code to published image.

---

## Understanding Volume Mounts and Backup Definitions

The `-v` flag that maps host directories into the container is the key decision that controls
how many backup definitions you can use — and which host paths are reachable at all.

In short:

- **Map host `/` → container `/data`** — the entire host tree is visible; multiple definitions
  can each target different subtrees (`data/home/alice/photos`, `data/srv/media`, …).
- **Map a single subdirectory → container `/data`** — only that directory is visible inside the
  container; only one definition (or definitions that stay within that subtree) will work.

See **[doc/volume-mount-scenarios.md](doc/volume-mount-scenarios.md)** for a full explanation
with diagrams, worked examples, and a comparison table.

---

## Useful links

| Topic| Link   |
| -----| ------ |
| `dar-backup`       | [dar-backup on Github](https://github.com/per2jensen/dar-backup) |
| `dar-backup-image` | [dar-backup-image](https://github.com/per2jensen/dar-backup-image)|
| `Docker Hub repo`  | [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags) |
| `dar`              | [Disk ARchive](http://dar.linux.free.fr/)|

---

## License

`dar-backup-image` is licensed under `GPL-3.0-or-later`.

The complete license text is available in the [repository LICENSE file](https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE)
and is embedded in every image at `/LICENSE`. Print it without installing or starting
`dar-backup`:

```bash
docker run --rm --entrypoint cat per2jensen/dar-backup:latest /LICENSE
```

---

## Docker Hub image repo

You can see publicly available `dar-backup` docker images on [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags).

Those fond of curl can do this:

```bash
curl -s https://hub.docker.com/v2/repositories/per2jensen/dar-backup/tags | jq '.results[].name'
```

---

## Description

A minimal, Dockerized backup runner using dar (Disk ARchive) and dar-backup, ready for automated or manual archive creation and restore.

The image is continuously tested via a full CI pipeline on every commit, with weekly refreshes to keep `:latest` current and vulnerability-free.

This image includes:

- dar
- par2
- python3
- setpriv
- [dar-backup](https://github.com/per2jensen/dar-backup) (my `dar` Python based wrapper)
- Clean, minimal Ubuntu 24.04 base (~170 MB)
- CIS-aligned permissions and user-drop via setpriv

---

## Directory Layout and Permissions

The `run-backup.sh` script uses a standardized directory structure to ensure backups work consistently across environments. These directories are host-mounted into the container so that all backup archives, definitions, and restored files remain accessible outside Docker.

By default, the script expects (or creates) the following structure relative to `WORKDIR`:

- `$WORKDIR/backups` → Mounted as `/backups` (DAR archives and logs)  
- `$WORKDIR/backup.d` → Mounted as `/backup.d` (backup definition files)  
- `$WORKDIR/data` → Mounted as `/data` (source data to back up)  
- `$WORKDIR/restore` → Mounted as `/restore` (restored files)

### How Directory Overrides Work

The script resolves its directory paths in the following priority order:

1. If an explicit directory environment variable is set (`DAR_BACKUP_DIR`, `DAR_BACKUP_D_DIR`, `DAR_BACKUP_DATA_DIR`, or `DAR_BACKUP_RESTORE_DIR`), that value is used.
2. Otherwise, if `WORKDIR` is set, each directory defaults to a subdirectory of `WORKDIR` (e.g., `$WORKDIR/backups`).
3. If neither is set, the script defaults to using the directory where `run-backup.sh` resides as the base.

This allows full flexibility: you can set `WORKDIR` once for a standard layout, or override specific directories individually.

### UID and GID Behavior

All files written by `dar-backup` inside the container will match your host user and group:

- By default, `RUN_AS_UID` and `RUN_AS_GID` are set to your current UID and GID.
- These are passed to Docker via `--user "$RUN_AS_UID:$RUN_AS_GID"`.
- Running as `root` (UID 0) is disallowed; the script will exit with an error.
- You can override these values for special cases, such as:

  - **Group-based backups:**  
    `RUN_AS_GID=$(getent group backupgrp | cut -d: -f3)`  
    Ensures all archives are group-writable.

  - **Service accounts:**  
    `RUN_AS_UID=1050 RUN_AS_GID=1050 ./run-backup.sh -t FULL`  
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
Group ownership

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
RUN_AS_UID=1050 RUN_AS_GID=1050 ./run-backup.sh -t FULL
```

This ensures consistent ownership for cron jobs or automated workflows.

For full environment variable documentation, see the header comments in [`run-backup.sh`](./run-backup.sh).

## Environment Variables

Here’s a quick reference for all environment variables used by the script:

| Variable                | Default                  | Purpose                                                        |
|-------------------------|--------------------------|----------------------------------------------------------------|
| `IMAGE`                 | `dar-backup:dev`         | Docker image tag to use for the backup container.             |
| `WORKDIR`               | Script directory         | Base directory for all backup-related paths.                  |
| `RUN_AS_UID`            | Current user's UID       | UID passed to Docker to avoid root-owned files.               |
| `RUN_AS_GID`            | Current user's GID       | GID passed to Docker for correct file group ownership.        |
| `DAR_BACKUP_DIR`        | `$WORKDIR/backups`       | Host directory for DAR archives and logs (mounted at `/backups`). |
| `DAR_BACKUP_D_DIR`      | `$WORKDIR/backup.d`      | Host directory for backup definition files (mounted at `/backup.d`). |
| `DAR_BACKUP_DATA_DIR`   | `$WORKDIR/data`          | Host directory containing source data (mounted at `/data`).    |
| `DAR_BACKUP_RESTORE_DIR`| `$WORKDIR/restore`       | Host directory for restored files (mounted at `/restore`).     |

For details on behavior, UID/GID handling, and usage examples, see the comments in [`run-backup.sh`](./run-backup.sh).

---

## How to test

See [dev.md](dev.md) for development-image build and test instructions.

## Image Tags

All images are published to [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags).

Every build — whether a release or a scheduled refresh — is recorded in [build-history.json](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json).

---

### Tagging strategy

| Tag           | Description                                                                 | Docker Hub | Example Usage  |
|---------------|-----------------------------------------------------------------------------|------------|----------------|
| `:latest`     | Most recent weekly refresh or release — always signed, scanned, and fresh   | ✅ Yes     | `docker pull per2jensen/dar-backup:latest` |
| `:0.x.y`      | Versioned release following semantic versioning                              | ✅ Yes     | `docker pull per2jensen/dar-backup:0.5.22` |
| `:0.x.y-N`    | Scheduled weekly refresh of release `0.x.y` (N increments each refresh)    | ✅ Yes     | `docker pull per2jensen/dar-backup:0.5.22-1` |
| `:dev`        | Development version; may be broken or incomplete                            | ❌ No      | `docker run dar-backup:dev` |


For normal day-to-day use, `:latest` is convenient because it tracks the most recently tested and refreshed image.

For **long-term recovery**, do not preserve only the `:latest` reference. Save a specific versioned image, for example `:0.5.27`, as a Docker/OCI archive alongside the backup set. A mutable registry tag is a locator; the saved image is the recovery artifact.


### Weekly image refresh

`:latest` is kept up to date by a scheduled weekly rebuild that runs every Saturday. Each refresh:

- Rebuilds from the same source as the latest stable release, picking up any Ubuntu base image security patches
- Runs the full test suite — the pipeline halts if any test fails
- Scans with [Grype](https://github.com/anchore/grype) — **the refresh is aborted if any High or Critical vulnerability is found**
- Signs the image with [cosign](https://github.com/sigstore/cosign) keyless signing and records the entry in the [Rekor](https://github.com/sigstore/rekor) transparency log
- Attaches a signed CycloneDX SBOM attestation
- Publishes as both `:latest` and a versioned refresh tag (e.g. `:0.5.22-1`, `:0.5.22-2`)
- Atomically publishes the build-history commit and its annotated Git tag; the
  annotation records the immutable application SHA and signed image digest
- Updates the [cosign badge](https://github.com/per2jensen/dar-backup-image/blob/main/doc/cosign_badge.json) — `failed` means the most recent signing attempt was rejected and rolled back; the previously published `:latest` may remain valid

The [build-history.json](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json) file contains the full audit trail for every release and refresh, including digests, Rekor log entries, and Grype scan results.

---

## Volumes / Runtime Configuration

The default dar-backup.conf baked into the image assumes the directories mentioned below.

The locations should be mounted with actual directories on your machine for backups.

|Directories in file system| Directories in container| Purpose   |
|------------------------- | ------------------------| ---------------------------------------------|
|/some/dir/to/backup/      | `/data`                 | Source directory for backup                  |
|/keep/backups/here/       | `/backup`               | `dar` archives and .par2 files are put here  |
|/restore/tests/           | `/restore`              | Optional restore target                      |
|[/backup/definitions/](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#backup-definition-example)      | `/backup.d`             | Contains backup definition files             |

The mapping between physical directories on your file system and the expected directories inside the container is performed by the `-v /physical/dir:/container/dir` options  (see example below).

> 💡 **How you mount `/data` determines which backup definitions work.**
> See [Understanding Volume Mounts and Backup Definitions](#-understanding-volume-mounts-and-backup-definitions).

---

## Usage Example

Determine whether you want to build an image yourself or use one from Docker
Hub. Development-image build instructions are in [dev.md](dev.md).

```bash
# Use your own locally built image
export IMAGE=dar-backup:dev

# Or use one from Docker Hub — latest is always signed, scanned, and fresh
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

docker run --rm \
  -e RUN_AS_UID=$(id -u) \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backups \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" \
  -F --log-stdout
```

The image automatically uses [`/etc/dar-backup/dar-backup.conf`](https://github.com/per2jensen/dar-backup-image/blob/main/dar-backup.conf) unless you override it.

To use another config file you have multiple options:

- Modify the [baked-in](https://github.com/per2jensen/dar-backup-image/blob/main/dar-backup.conf) and build a new image.
- Use --config option to point to another (for example: /backup/dar-backup.conf, which in the example above means you physically put it on "$BACKUP_DIR"/dar-backup.conf)
- Let DAR_BACKUP_CONFIG point to a config file.

The container uses set-priv to drop root privileges. Pass -e RUN_AS_UID=$(id -u) to run as your own user inside the container.

---

## run-backup.sh

This script runs a backup using a dar-backup Docker image.

It runs a backup based on the specified type (FULL, DIFF, INCR)
with the following features:

### Baked-in config file

Using the baked in [dar-backup.conf](https://github.com/per2jensen/dar-backup-image/blob/main/dar-backup.conf) file (se more [here](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#config)).

### PyPI .darrc

Uses the .darrc file from the [PyPI package](https://pypi.org/project/dar-backup/) added to the image,
   see image [details here](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json)
  
   .darrc [contents](https://github.com/per2jensen/dar-backup/blob/main/v2/src/dar_backup/.darrc)

### 3 Logs to stdout

It print log messages to stdout.

### Default directory layout

Expected directory structure when running this script:

```text
   WORKDIR/
     ├── backups/           # Where backups are stored
     ├── backup.d/          # Backup definitions
     ├── data/              # Data to backup
     └── restore/           # Where restored files will be placed
```

If envvar WORKDIR is set, the script uses that as the base directory.

If WORKDIR is not set, the script uses the directory where the script is located as the base directory.

These directories are host-mounted into the container so your data and archives remain accessible:

| Host Directory (default)      | Container Mount  | Purpose                           |
|--------------------------------|------------------|-----------------------------------|
| `$WORKDIR/backups`             | `/backups`       | DAR archives and log files       |
| `$WORKDIR/backup.d`            | `/backup.d`      | Backup definition files          |
| `$WORKDIR/data`                | `/data`          | Source data for the backup       |
| `$WORKDIR/restore`             | `/restore`       | Destination for restore tests    |

You can override any of these paths by setting the environment variables:
`DAR_BACKUP_DIR`, `DAR_BACKUP_D_DIR`, `DAR_BACKUP_DATA_DIR`, `DAR_BACKUP_RESTORE_DIR`.  
If none are set, `WORKDIR` (or the script’s own directory) is used as the base.

More info on [backup definitions in general](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#backup-definition-example)

View [supplied `default` backup definition](https://github.com/per2jensen/dar-backup-image/blob/main/doc/backup-definitions/default)

### Image used

If IMAGE is not set, the script defaults to `dar-backup:dev`.

   You can see available images on [Docker Hub here)(https://hub.docker.com/r/per2jensen/dar-backup/tags)

   If RUN_AS_UID is not set, it defaults to the current user's UID.
    - running the script as root is not allowed, the script will exit with an error.

### Backup Definitions

The `run-backup.sh` script supports selecting a specific backup definition file, which allows you to maintain multiple dataset or policy definitions.

Each backup definition file resides in:

$DAR_BACKUP_D_DIR (default: $WORKDIR/backup.d)

and is automatically mounted into the container at `/backup.d`.

> **Note on daily backups per definition:**  
> `dar-backup` will only create one `FULL`, one `DIFF`, and one `INCR` backup **per definition per calendar day**.  
> - You can run all three types (FULL → DIFF → INCR) on the same day.  
> - A second run of the *same type* (e.g., another FULL) will be skipped to avoid overwriting the existing archive.
> - To force a new run, either remove or archive the previous `.dar` files for that definition/date.
> -- Use [`cleanup`](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#cleanup-options) for safe archive deletions

#### Usage

To specify a backup definition, use the `-d` or `--backup-definition` option:

```bash
WORKDIR=/path/to/workdir ./run-backup.sh -t FULL -d my-backup-definition
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

This is achieved dynamically using:

```bash
${BACKUP_DEF:+--backup-definition "$BACKUP_DEF"}
```

in the `docker run` command, which:

- Adds `--backup-definition "<name>"` if `BACKUP_DEF` is non-empty.
- Skips it entirely if no `-d` was provided (dar-backup then uses the default definition).

---

#### Example

1. Create a new definition file:

```bash
cat > $HOME/dar-backup/backup.d/projects << 'EOF'
-R /data/projects
-z5
-am
--slice 5G
EOF
```

2. Run a differential backup using it:

```bash
WORKDIR=$HOME/dar-backup ./run-backup.sh -t DIFF -d projects
```

The backup will:
- Store archives in `$HOME/dar-backup/backups`.
- Use `/backup.d/projects` as the definition.
- Retain ownership based on `RUN_AS_UID` and `RUN_AS_GID`.

### Common Pitfalls

> - **Why is my backup skipped?**  
>   Only one `FULL`, one `DIFF`, and one `INCR` backup can be created per definition per day.  
>   If a run is skipped, remove or archive the existing `.dar` files for that definition/date.
>
> - **Permission issues on host files?**  
>   Ensure `RUN_AS_UID` and `RUN_AS_GID` match the desired owner.  
>   If unsure, run `id -u` and `id -g` to get your UID and GID.
>
> - **Definition not found?**  
>   Make sure your `backup.d/<name>` file exists (or let the script auto-create `default`).

### Basic usage

```bash
WORKDIR=/path/to/your/workdir IMAGE=`image` ./run-backup.sh -t FULL|DIFF|INCR -d "backup_definition"
```

## 🔍 Discover Image Metadata

Learn what's inside the `dar-backup` image: program versions, build metadata, and available versions.

---

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

Example output:
{
  "org.dar-backup.version": "1.1.5",
  "org.dar.version": "2.7.21",
  "org.opencontainers.image.authors": "Per Jensen <dar-backup@pm.me>",
  "org.opencontainers.image.base.digest": "sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b",
  "org.opencontainers.image.base.name": "ubuntu",
  "org.opencontainers.image.base.version": "24.04",
  "org.opencontainers.image.created": "2026-05-17T20:03:16Z",
  "org.opencontainers.image.description": "Container for DAR-based backups using `dar-backup`",
  "org.opencontainers.image.documentation": "https://github.com/per2jensen/dar-backup-image/blob/main/README.md",
  "org.opencontainers.image.licenses": "GPL-3.0-or-later",
  "org.opencontainers.image.ref.name": "per2jensen/dar-backup:0.5.24",
  "org.opencontainers.image.revision": "d5bf339",
  "org.opencontainers.image.source": "https://github.com/per2jensen/dar-backup-image",
  "org.opencontainers.image.title": "dar-backup",
  "org.opencontainers.image.url": "https://hub.docker.com/r/per2jensen/dar-backup",
  "org.opencontainers.image.version": "0.5.24",
  "org.dar-backup.documentation.command": "docs",
  "org.dar-backup.documentation.path": "/usr/share/doc/dar-backup"
}
```

### 3. List Available Image Tags

```bash
# Show first 100 available tags
curl -s 'https://hub.docker.com/v2/repositories/per2jensen/dar-backup/tags?page_size=100' \
  | jq -r '.results[].name' | sort -V
```

## Image deep diving

Although `dar-backup` is the primary CLI inside the container, you can also run dar directly from the image to take manual backups or inspect archives — perfect for advanced workflows or testing.

Here's a minimal example of how to use dar directly:

```bash
export DATA_DIR=/tmp/test-data
export BACKUP_DIR=tmp/test-backups
export VERSION=0.5.25.1; export IMAGE=per2jensen/dar-backup:${VERSION}
touch /tmp/test-data/TEST.txt

docker run --rm -v "$DATA_DIR":/data -v "$BACKUP_DIR":/backups --entrypoint dar "$IMAGE" -c /backups/myarchive -R /data
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

This shows that even without dar-backup, you can still invoke dar manually — helpful for debugging, recovery scenarios, or power-user workflows.

    🧠 Tip: You can also run par2 directly using --entrypoint par2 if needed.

---

## Common `dar-backup` commands

### Full backup

dar-backup --full-backup

### Diff backup (requires prior FULL)

dar-backup --differential-backup

### Incremental backup (requires DIFF)

dar-backup --incremental-backup

### List available archives

dar-backup --list

### List contents of a backup

dar-backup --list-contents <archive_name>

### Restore

dar-backup --restore <archive_name>

---

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

Releases are fully automated via the **Manual Docker Release** GitHub Actions workflow — no local `docker push` required.

Dry-run the release locally first (build, test, verify labels — no push):

```bash
make FINAL_VERSION="$(cat IMAGE_VERSION)" dry-run-release
```

This validates:

- The image builds correctly
- Labels and `dar-backup --version` match expected values
- All tests pass

When ready, trigger the release by dispatching the workflow from GitHub Actions (`workflow_dispatch`). The workflow will:

1. Lock the build to the full commit selected from `main` and validate `IMAGE_VERSION`
2. Build, test, and scan — hard gate on High/Critical vulnerabilities
3. Push `per2jensen/dar-backup:VERSION` as a candidate
4. Sign the candidate and attach its SBOM attestation
5. Roll back a failed candidate without moving the previous `:latest`
6. Promote the successfully signed digest to `:latest`
7. Update build history, README, badge, pages, and the source-pointing Git tag

> **Note:** Do NOT manually create the git tag before triggering the workflow — it is created automatically after all steps succeed.

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

## TODO

### Version 1.0

- Evaluate the current documentation and decide whether it is sufficient for 1.0
- Perform additional torture testing and verification to solidify the image
- Determine whether test coverage is suitable for a 1.0 release
- Harden the release workflow

### Version 1.1

- Integrate DAR 2.8
- Investigate and document compatibility between 1.0 and 1.1 backup archives and restore environments

### Version 1.2

- Investigate DAR's encryption features

### Other tasks

- Investigate deterministic generated test cases so test runs can be reproduced across versions and during debugging

---

## Software this project benefits from

- [DAR of course :-)](http://dar.linux.free.fr/)
- [Ubuntu](https://ubuntu.com/)
- [Python](https://python.org/)
- [GNU sofware](https://www.fsf.org/)
