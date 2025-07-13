# 📦 dar-backup image for container backups and more

![CI](https://github.com/per2jensen/dar-backup-image/actions/workflows/test.yml/badge.svg)
[![# clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/badges/badge_clones.json)](https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/weekly_clones.png)
[![Milestone](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/badges/milestone_badge.json)](https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/weekly_clones.png)  <sub>🎯 Stats powered by [ClonePulse](https://github.com/per2jensen/clonepulse)</sub>

## Links to Gihub repositories

`Dar-backup` is a Python wrapper around the very excellent [dar](https://github.com/Edrusb/DAR) backup program. `Dar-backup` is known to work on Ubuntu, it probably works on a multitude of Linux'es.

`Dar-backup-image` is `dar-backup` baked into a Docker image.

| Topic              | Link to Github   |
| -------------------| ---------------- |
| `dar-backup`       | [dar-backup on Github](https://github.com/per2jensen/dar-backup) |
| `dar-backup-image` | [dar-backup-image](https://github.com/per2jensen/dar-backup-image)|

## Docker Hub image repo

You can see publicly available `dar-backup` docker images on [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags).

Those fond of curl can do this:

```bash
curl -s https://hub.docker.com/v2/repositories/per2jensen/dar-backup/tags | jq '.results[].name'
```

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

## License

This repo is licensed under the GPL 3.0 License

If you are not familiar with the license take a look at the included LICENSE file in the repository.

## How to test

```bash
# make new base and development image
make all-dev

# run FULL, DIFF and INCR backups in a temp directory
make test
```

## 🔧 Image Tags

Some  images are put on [DockerHub](https://hub.docker.com/r/per2jensen/dar-backup/tags).

The [Release procedure](https://github.com/per2jensen/dar-backup-image/blob/main/doc/Release.md) results in two things:

- An image pushed to [Docker Hub](https://hub.docker.com/r/per2jensen/dar-backup/tags).
- Metadata about the image put in [build-history.md](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json).

## 🧰 Volumes / Runtime Configuration

The default dar-backup.conf baked into the image assumes the directories mentioned below.

The locations should be mounted with actual directories on your machine for backups.

| Volume Mount | Purpose                                          |
| ------------ | ------------------------------------------------ |
| `/data`      | Source directory for backup                      |
| `/backup`    | `dar` archives and .par2 files are put here      |
| `/restore`   | Optional restore target                          |
| `/backup.d`  | Contains backup definition files                 |

## 🚀 Usage Example

```bash
# Build base image
docker build -f Dockerfile-base-image -t dar-backup-base:24.04 .

# Build final image
docker build -f Dockerfile-dar-backup -t dar-backup:0.5.0-alpha .

# Run it (from script or manually)
# Configuration
export DATA_DIR=/tmp/test-data
export BACKUP_DIR=/tmp/test-backups
export RESTORE_DIR=/tmp/test-restore
export BACKUP_D_DIR=/tmp/test-backup.d
export IMAGE=per2jensen/dar-backup:0.5.0-alpha

docker run --rm \
  -e RUN_AS_UID=1000 \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backup \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" \
  -F --log-stdout --config /etc/dar-backup/dar-backup.conf
```

## run-backup.sh

This script runs a backup using a dar-backup Docker image.

It runs a backup based on the specified type (FULL, DIFF, INCR)
with the following features:

### 1

Using the baked in dar-backup.conf file (se this repo).

### 2

Uses the .darrc file from the [PyPI package](https://pypi.org/project/dar-backup/) added to the image,
   see image [details here](https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json)
  
   .darrc [contents](https://github.com/per2jensen/dar-backup/blob/main/v2/src/dar_backup/.darrc)

### 3

It print log messages to stdout.

### 4

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

### 5

If IMAGE is not set, the script defaults to `dar-backup:dev`.

   You can see available images on [Docker Hub here)(https://hub.docker.com/r/per2jensen/dar-backup/tags)

   If RUN_AS_UID is not set, it defaults to the current user's UID.
    - running the script as root is not allowed, the script will exit with an error.

### 6

You can configure the directory layout by setting the following environment variables:

- DAR_BACKUP_DIR: Directory for backups (default: WORKDIR/backups)

- DAR_BACKUP_DATA_DIR: Directory for data to backup (default: WORKDIR/data) 

- DAR_BACKUP_D_DIR: Directory for backup definitions (default: WORKDIR/backup.d)

- DAR_BACKUP_RESTORE_DIR: Directory for restored files (default: WORKDIR/restore)

### Usage

```bash
WORKDIR=/path/to/your/workdir IMAGE=`image` ./run-backup.sh -t FULL|DIFF|INCR
```

## 🔍 Discover Image Metadata

Learn what's inside the `dar-backup` image: program versions, build metadata, and available versions.

---

### 🧪 1. Check Tool Versions

Run the image with different entrypoints to check the bundled versions of `dar-backup`, `dar`, and `par2`:

```bash
IMAGE=per2jensen/dar-backup:0.5.1

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
docker pull per2jensen/dar-backup:0.5.1
docker inspect per2jensen/dar-backup:0.5.1 | jq '.[0].Config.Labels'

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

## Release procedure

### Check version numbers and more

```bash
make FINAL_VERSION=0.5.2  DAR_BACKUP_VERSION=0.8.0 final-dryrun 
🔎 FINAL DRY-RUN
   FINAL_VERSION       = 0.5.2
   DAR_BACKUP_VERSION  = 0.8.0
   UBUNTU_VERSION      = 24.04
   BASE_IMAGE_NAME     = dar-backup-base
   FINAL_IMAGE_NAME    = dar-backup
   DOCKERHUB_REPO      = per2jensen/dar-backup

🔨 Image tags:
   - dar-backup:0.5.2
   - per2jensen/dar-backup:0.5.2

📦 Labels (subset):
   org.opencontainers.image.version       = 0.5.2
   org.dar-backup.version                 = 0.8.0
   org.opencontainers.image.revision      = 5cca8a9
   org.opencontainers.image.created       = 2025-07-13T14:06:57Z

✅ Dry-run done. Run 'make final' to build.
```

### Build final

```bash
make FINAL_VERSION=0.5.2 DAR_BACKUP_VERSION=0.8.0 final
...
🔎 Verifying 'dar-backup --version' matches DAR_BACKUP_VERSION (0.8.0 )
✅ dar-backup --version is correct: 0.8.0
make[1]: Leaving directory '/home/pj/git/dar-backup-image'
make[1]: Entering directory '/home/pj/git/dar-backup-image'
🔍 Verifying OCI image labels on dar-backup:0.5.2
✅ org.opencontainers.image.authors: Per Jensen <dar-backup@pm.me>
✅ org.opencontainers.image.base.name: ubuntu
✅ org.opencontainers.image.base.version: 24.04
✅ org.opencontainers.image.created: 2025-07-13T14:09:02Z
✅ org.opencontainers.image.description: Container for DAR-based backups using 
✅ org.opencontainers.image.licenses: GPL-3.0-or-later
✅ org.opencontainers.image.ref.name: per2jensen/dar-backup:0.5.2
✅ org.opencontainers.image.revision: 5cca8a9
✅ org.opencontainers.image.source: https://github.com/per2jensen/dar-backup-image
✅ org.opencontainers.image.title: dar-backup
✅ org.opencontainers.image.url: https://hub.docker.com/r/per2jensen/dar-backup
✅ org.opencontainers.image.version: 0.5.2
🎉 All required OCI labels are present.
make[1]: Leaving directory '/home/pj/git/dar-backup-image'
```

### Do a dry-run release

This builds the image and runs the test cases against it.

```bash
make FINAL_VERSION=0.5.2 DAR_BACKUP_VERSION=0.8.0 dry-run-release
...
2025-07-13 14:12:13,182 - INFO - Type of backup:   INCR
2025-07-13 14:12:13,183 - INFO - ======================================
2025-07-13 14:12:13,184 - INFO - ===> Starting INCR backup for /backup.d/default
[14:12:13] [~] Not a terminal — progress bar skipped.        rich_progress.py:62
2025-07-13 14:12:13,219 - INFO - INCR backup completed successfully.
2025-07-13 14:12:13,435 - INFO - Catalog for archive '/backups/default_INCR_2025-07-13' added successfully to its manager.
2025-07-13 14:12:13,436 - INFO - Starting verification...
[14:12:13] [~] Not a terminal — progress bar skipped.        rich_progress.py:62
2025-07-13 14:12:13,504 - INFO - Archive integrity test passed.
2025-07-13 14:12:13,569 - INFO - No files between 1MB and 20MB for verification, skipping
2025-07-13 14:12:13,569 - INFO - Verification completed successfully.
2025-07-13 14:12:13,569 - INFO - Generate par2 redundancy files.
2025-07-13 14:12:13,570 - INFO - 1/1: Now generating par2 files for /backups/default_INCR_2025-07-13.1.dar
2025-07-13 14:12:13,603 - INFO - 1/1: Done
2025-07-13 14:12:13,603 - INFO - par2 files completed successfully.
2025-07-13 14:12:13,603 - INFO - END TIME: 1752415933
✔ INCR backup (requires DIFF first)
make[1]: Leaving directory '/home/pj/git/dar-backup-image/.dryrun'
✅ Dry-run complete — no changes made to working directory
...
```

### Do a Release

Set DOCKER_USER and DOCKER_TOKEN envvars first.

```bash
make FINAL_VERSION=0.5.2 DAR_BACKUP_VERSION=0.8.0 release
...





