# 📦 dar-backup image for container backups and more

![CI](https://github.com/per2jensen/dar-backup-image/actions/workflows/build-test-scan.yml/badge.svg)
<img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/per2jensen/dar-backup"/>
[![# clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/badges/badge_clones.json)](https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/weekly_clones.png)
[![Milestone](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/badges/milestone_badge.json)](https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/weekly_clones.png)  <sub>🎯 Stats powered by [ClonePulse](https://github.com/per2jensen/clonepulse)</sub>

## 🗄️ dar-backup-image

`dar-backup-image` is a Docker image that bundles the powerful dar (Disk ARchiver) utility with the robust Python wrapper `dar-backup`. Together, they provide a flexible, automated, and verifiable backup solution suited for long-term data retention.

This image makes it easy to run `dar-backup` in a clean, isolated container environment — perfect for use in cron jobs, systemd timers, or CI pipelines. Whether you're backing up from FUSE-based cloud storage or verifying years-old archives, this image delivers consistent, reproducible results without requiring dar or Python tooling on the host.

At it's core is `dar-backup`, a Python-powered CLI that wraps dar and par2 for reliable full, differential, and incremental backups. It validates archives, performs restore tests, manages catalog databases, and optionally generates redundancy files to protect against bit rot.

🔧 Highlights

    Automated backup logic with dar-backup: tested, restore-verified, and redundancy-enhanced

    Stateless and portable: no installation required on the host system

    Ideal for FUSE filesystems: works without root, designed for user-space storage

    The image automatically loads its baked-in config (/etc/dar-backup/dar-backup.conf). No --config argument is required unless you need a custom one.

    Includes par2 for integrity protection

    Ready for CI / cron / systemd: just mount volumes and go

>The default entrypoint of this image is `dar-backup`, meaning any docker run invocation without a command will start dar-backup directly. You can also run dar, par2, or a shell interactively by overriding the entrypoint.

Use `dar-backup-image` to centralize and simplify your backup operations — with restore confidence built in.

---

## 📑 Table of Contents

- [📦 dar-backup image for container backups and more](#-dar-backup-image-for-container-backups-and-more)
  - [🗄️ dar-backup-image](#️-dar-backup-image)
  - [📑 Table of Contents](#-table-of-contents)
  - [`dar` versions](#dar-versions)
  - [Builds uploaded to Docker Hub](#builds-uploaded-to-docker-hub)
  - [🔧 Hands-on Demo: `dar-backup` in a Container](#-hands-on-demo-dar-backup-in-a-container)
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
  - [🔧 Image Tags](#-image-tags)
    - [🐳 tagging strategy](#-tagging-strategy)
  - [🧰 Volumes / Runtime Configuration](#-volumes--runtime-configuration)
  - [🚀 Usage Example](#-usage-example)
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
    - [⚠️ Common Pitfalls](#️-common-pitfalls)
    - [Basic usage](#basic-usage)
  - [🔍 Discover Image Metadata](#-discover-image-metadata)
    - [🧪 1. Check Tool Versions](#-1-check-tool-versions)
    - [🏷️ 2. Inspect Image Labels](#️-2-inspect-image-labels)
    - [📦 3. List Available Image Tags](#-3-list-available-image-tags)
  - [Image deep diving](#image-deep-diving)
  - [Common `dar-backup` commands](#common-dar-backup-commands)
    - [Full backup](#full-backup)
    - [Diff backup (requires prior FULL)](#diff-backup-requires-prior-full)
    - [Incremental backup (requires DIFF)](#incremental-backup-requires-diff)
    - [List available archives](#list-available-archives)
    - [List contents of a backup](#list-contents-of-a-backup)
    - [Restore](#restore)
  - [Using the Makefile](#using-the-makefile)
    - [Common Targets](#common-targets)
    - [dar and dar-backup versions](#dar-and-dar-backup-versions)
    - [Testing Locally Built Images](#testing-locally-built-images)
    - [Testing Released Images from Docker Hub](#testing-released-images-from-docker-hub)
    - [Releasing a New Version](#releasing-a-new-version)
    - [Recommended Workflow](#recommended-workflow)
  - [Software this project benefits from](#software-this-project-benefits-from)

---

## `dar` versions

Starting with `dar-backup-image` **0.5.15**, `dar` (v2.7.18) is compiled from source rather than using Ubuntu 24.04’s older package.

Table of `dar` version in `dar-backup-image` tagged images:
| Tag | `dar` | Note |
|---|-------------------|------------|
| 0.5.17| 2.7.19| |
| 0.5.16| 2.7.19| [Release note 2.7.19](https://sourceforge.net/p/dar/mailman/message/59214592/)
| 0.5.15| 2.7.18| [Release note 2.7.18](https://sourceforge.net/p/dar/mailman/message/59186067/) |
| ... - 0.5.14| 2.7.13| Ubuntu 24.04 standard |

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
## Builds uploaded to Docker Hub

|Tag|`dar-backup`version|Git Revision|Docker Hub|
|---|-------------------|------------|----------|
| 0.5.17| 0.8.4| 02822f5|[tag:0.5.17](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.17/images/sha256:a0f4dfec55005c1b07f69d1af6bc750a0c56a38cc04c536a8390347d02a3fdae)|
| 0.5.16| 0.8.2| 9b6dc45|[tag:0.5.16](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.16/images/sha256:462d35c545b2d516bfa402374b2ef1566f1f68298280dcdbefe5a1a9e45130af)|
| 0.5.15| 0.8.2| 3a40112|[tag:0.5.15](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.15/images/sha256:386e095482e6cdcff0a0ec23924bae196ea5da31cdd4f6f7a1d62b89786f517f)|
| 0.5.14| 0.8.2| eba3646|[tag:0.5.14](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.14/images/sha256:0ba8c08ef240728693b200c102dc78d1f39510da66e0581262d720c81c0ad015)|
| 0.5.13| 0.8.2| ba12177|[tag:0.5.13](https://hub.docker.com/layers/per2jensen/dar-backup/0.5.13/images/sha256:69bd96f894ff4708b1377cb61cac55d4269f6ea5de5a09d7d6885f4181fdcd1c)|

---

## 🔧 Hands-on Demo: `dar-backup` in a Container

Curious how it all works in practice?

Check out the [📄 step-by-step demo](https://github.com/per2jensen/dar-backup-image/blob/main/doc/demo-containerized-dar-backup.md), which walks through:

- A full backup from mounted directories
- Archive listing and contents inspection
- Selective file restore (e.g., `.JPG` only)
- Output logs, par2 generation, and verification

All performed using `docker run` — no host installation required.

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

`dar-backup-image`is licensed under `GPL 3` or later.

If you are unfamiliar with that license, take a look at the [LICENSE file in this repo](https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE)

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

This is early, the `dar-backup` images are not tested well, do not trust it too much. It will mature over time :-)

This image includes:

- dar
- par2
- python3
- gosu
- [dar-backup](https://github.com/per2jensen/dar-backup) (my `dar` Python based wrapper)
- Clean, minimal Ubuntu 24.04 base (~170 MB)
- CIS-aligned permissions and user-drop via gosu

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

```bash
# make new base and development image
make all-dev

# run FULL, DIFF and INCR backups in a temp directory
make test
```

Two images are built:

1. A [base image](https://github.com/per2jensen/dar-backup-image/blob/main/Dockerfile-base-image) which currently is a slimmed down ubuntu 24.04 image

2. [dar-backup image](https://github.com/per2jensen/dar-backup-image/blob/main/Dockerfile-dar-backup) is installed on top of the base image

## 🔧 Image Tags

Some  images are put on [DockerHub](https://hub.docker.com/r/per2jensen/dar-backup/tags).

The [Release procedure](https://github.com/per2jensen/dar-backup-image/blob/main/doc/Release.md) results in two things:

- An image pushed to [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags).
- Metadata about the image put in [build-history.md](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json).

---

### 🐳 tagging strategy

For now I am not using `latest`, as the images have not yet demonstrated their quality.

I am currently going with:

| Tag        | Description                                      | Docker Hub | Example Usage  |
|------------|--------------------------------------------------|------------|----------------|
| `:0.x.y`   | Versioned releases following semantic versioning | ✅ Yes     | `docker pull per2jensen/dar-backup:0.5.6`   |
| `:stable`  | Latest "good" and trusted version; perhaps `:rc` | ✅ Yes     | `docker pull per2jensen/dar-backup:stable` |
| `:dev`     | Development version; may be broken or incomplete | ❌ No      | `docker run dar-backup:dev` |

---

## 🧰 Volumes / Runtime Configuration

The default dar-backup.conf baked into the image assumes the directories mentioned below.

The locations should be mounted with actual directories on your machine for backups.

|Directories in file system| Directories in container| Purpose   |
|------------------------- | ------------------------| ---------------------------------------------|
|/some/dir/to/backup/      | `/data`                 | Source directory for backup                  |
|/keep/backups/here/       | `/backup`               | `dar` archives and .par2 files are put here  |
|/restore/tests/           | `/restore`              | Optional restore target                      |
|[/backup/definitions/](https://github.com/per2jensen/dar-backup?tab=readme-ov-file#backup-definition-example)      | `/backup.d`             | Contains backup definition files             |

The mapping between physical directories on your file system and the expected directories inside the container is performed by the `-v /physical/dir:/container/dir` options  (see example below).

---

## 🚀 Usage Example

Determine if you want to built an image yourself, or use one of mine from Docker Hub.

```bash
# make a container
$ make FINAL_VERSION=dev DAR_BACKUP_VERSION=0.8.0 dev  # make a local development image

# check
$ docker images |grep "dev"
dar-backup              dev           e72a7fd82a4b   19 seconds ago   174MB

# Set IMAGE to your own
export IMAGE=dar-backup:dev  # your own locally build image

# Or set IMAGE to one of mine on Docker Hub
VERSION=0.5.17; export IMAGE=per2jensen/dar-backup:${VERSION}
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
  -v "$BACKUP_DIR":/backup \
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
WORKDIR=/path/to/workdir ./run-backup.sh -t FULL -d my-dataset
```

This instructs `dar-backup` to load:

$DAR_BACKUP_D_DIR/my-dataset

instead of the default definition (`default`).

If no `-d` option is supplied, the script falls back to the default definition.  
The `run-backup.sh` script also generates a minimal default definition file at:

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
echo "-R /data/projects -z5 -am --slice 5G" > $HOME/dar-backup/backup.d/projects
```

2. Run a differential backup using it:

```bash
WORKDIR=$HOME/dar-backup ./run-backup.sh -t DIFF -d projects
```

The backup will:
- Store archives in `$HOME/dar-backup/backups`.
- Use `/backup.d/projects` as the definition.
- Retain ownership based on `RUN_AS_UID` and `RUN_AS_GID`.

### ⚠️ Common Pitfalls

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

### 🧪 1. Check Tool Versions

Run the image with different entrypoints to check the bundled versions of `dar-backup`, `dar`, and `par2`:

```bash
VERSION=0.5.17; IMAGE=per2jensen/dar-backup:${VERSION}

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

### 🏷️ 2. Inspect Image Labels

```bash
VERSION=0.5.17; docker pull per2jensen/dar-backup:${VERSION}
docker inspect per2jensen/dar-backup:${VERSION} | jq '.[0].Config.Labels'

Example output:

{
  "org.opencontainers.image.base.created": "2025-06-19T13:38:32Z",
  "org.opencontainers.image.created": "2025-06-19T13:38:32Z",
  "org.opencontainers.image.description": "Container for DAR-based backups using dar-backup",
  "org.opencontainers.image.ref.name": "ubuntu",
  "org.opencontainers.image.source": "https://hub.docker.com/r/per2jensen/dar-backup",
  "org.opencontainers.image.version": "0.5.1"
}
```

### 📦 3. List Available Image Tags

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
VERSION=0.5.17; export IMAGE=per2jensen/dar-backup:${VERSION}
touch /tmp/test-data/TEST.txt

docker run --rm -v "$DATA_DIR":/data -v "$BACKUP_DIR":/backup --entrypoint dar "$IMAGE" -c /backup/myarchive -R /data
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

The `Makefile` automates building, testing, and releasing the `dar-backup-image` Docker images.  
It supports **local development builds**, **final version tagging**, and **release workflows** (including Docker Hub pushes).

### Common Targets

| Target                        | What It Does                                                                                         |
|-------------------------------|------------------------------------------------------------------------------------------------------|
| `make dev`                    | Builds a **development image** (`dar-backup:dev`) using the local Dockerfile and configuration.      |
| `make all-dev`                | Builds both the base image and the `dar-backup:dev` image (default dependency for most other targets).|
| `make test`                   | Builds `dar-backup:dev` (via `all-dev`) and runs the full pytest suite against it.                   |
| `make FINAL_VERSION=x.y.z final` | Tags the current `dar-backup:dev` as `dar-backup:x.y.z` and verifies version/labels.                        |
| `make FINAL_VERSION=x.y.z test`  | Builds (or re-tags) `dar-backup:x.y.z`, then runs pytest against it.                                      |
| `make IMAGE=per2jensen/dar-backup:x.y.z test-pulled` | Pulls the specified released image from Docker Hub and tests it (skips local build).                                 |
| `make FINAL_VERSION=x.y.z DAR_BACKUP_VERSION=a.b.c dry-run-release` | Creates a detached worktree, builds the image as `dar-backup:x.y.z`, runs tests, verifies labels, but does **not** push to Hub. |
| `make FINAL_VERSION=x.y.z DAR_BACKUP_VERSION=a.b.c release`         | Builds, verifies, tests, and **pushes the final image** to Docker Hub, also updating `doc/build-history.json` and `READNE.md`.                   |
| `make size-report`            | Displays a normalized report of image layer sizes (for auditing image size).                       |
| `make dev-nuke`               | Cleans all cached layers and build artifacts (forces a full fresh build next time).                 |

### dar and dar-backup versions

The versions of `dar` and `dar-backup` used in the image is controlled by the values in the two files

| File | Note |
|------|------|
|DAR_VERSION|For example `2.7.19`|
|DAR_BACKUP_VERSION|For example `0.8.2`|

The values are read by the Makefile and by the `build-test-scan.yml`action.

---

### Testing Locally Built Images

During development, build and test the local `dar-backup:dev` image:

```bash
make dev       # Build dar-backup:dev
make test      # Run tests against dar-backup:dev
```

To test a specific local version (tagged dar-backup:x.y.z):

```bash
make FINAL_VERSION=0.5.15 test
```

### Testing Released Images from Docker Hub

After publishing a release, test the exact image on Docker Hub (ignoring local builds):

```bash
make IMAGE=per2jensen/dar-backup:0.5.15 test-pulled
```

This:

    Pulls the image from Docker Hub.

    Runs the full pytest suite (no local build).

### Releasing a New Version

    Dry-run the release (build & test only, no push):

```bash
make FINAL_VERSION=0.5.15 dry-run-release
```

This validates:

    The image builds correctly.

    Labels and dar-backup --version match.

    All tests pass.

Perform the actual release (push to Docker Hub):

```bash
export DOCKER_USER=your-username
  export DOCKER_TOKEN=your-access-token  # do not put token in bash_history
make FINAL_VERSION=0.5.15 release
```

The release target will:

    Build and tag dar-backup:0.5.15.

    Verify labels and CLI version.

    Run tests.

    Push the image to Docker Hub.

    Update doc/build-history.json.

### Recommended Workflow

    During development:
    make dev && make test

    Before release:
    make dev-nuke
    make FINAL_VERSION=x.y.z final (validate your local final image)

    Dry-run release:
    make FINAL_VERSION=x.y.z dry-run-release

    Push the final image:
    make FINAL_VERSION=x.y.z release

    Verify the published image:
    make IMAGE=per2jensen/dar-backup:x.y.z test-pulled

---

## Software this project benefits from

- [DAR of course :-)](http://dar.linux.free.fr/)
- [Ubuntu](https://ubuntu.com/)
- [Python](https://python.org/)
- [GNU sofware](https://www.fsf.org/)
