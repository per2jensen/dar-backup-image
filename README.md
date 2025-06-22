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
