# 📦 dar-backup image for container backups and more

![CI](https://github.com/per2jensen/dar-backup-image/actions/workflows/test.yml/badge.svg)
[![# clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/badges/badge_clones.json)](https://github.com/per2jensen/dar-backup-image/blob/main/doc/weekly_clones.png)
[![Milestone](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/badges/milestone_badge.json)](https://github.com/per2jensen/dar-backup-image/blob/main/doc/weekly_clones.png)

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
# make new development image
make all-dev

# run FULL, DIFF and INCR backups
make test
```

## 🔧 Image Tags

This command is run against the image to verify the dar-backup version:

```bash
IMAGE=dar-backup:0.5.1-alpha
docker run --rm -it --entrypoint "dar-backup" "$IMAGE" -v
```

| Tag           | Base OS      | dar-backup       |dar Version | Notes      |
| ---------     | ------------ | ---------------- |------------|------------|
| `0.5.0-alpha` | Ubuntu 24.04 | dar-backup 0.7.2 | 2.7.13     |            |
| `0.5.1-alpha` | Ubuntu 24.04 | dar-backup 0.8.0 | 2.7.13     |            |

## 🧰 Volumes / Runtime Configuration

| Volume Mount | Purpose                                          |
| ------------ | ------------------------------------------------ |
| `/data`      | Source directory for backup                      |
| `/backup`    | Destination archive path                         |
| `/restore`   | Optional restore target                          |
| `/backup.d`  | Contains backup definition files (`.dar` format) |

## 📦 Container Availability on GHCR

The dar-backup Docker image is now published on the GitHub Container Registry (GHCR). You can pull the latest pre-release version tagged 0.5.0-alpha using:

docker pull ghcr.io/per2jensen/dar-backup:0.5.0-alpha

This image is based on Ubuntu 24.04 and includes the dar-backup CLI tool along with required dependencies like dar, par2, and gosu. It's ready for use in CI pipelines or local backup workflows. See the usage examples below for getting started quickly with test data and backup definitions.

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
export IMAGE=ghcr.io/per2jensen/dar-backup:0.5.0-alpha

docker run --rm \
  -e RUN_AS_UID=1000 \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backup \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" \
  -F --log-stdout --config /etc/dar-backup/dar-backup.conf
```

## Inspect program versions in an image

### Local images or Docker ones

```bash
IMAGE=dar-backup:0.5.1-alpha

# dar-backup version
docker run --rm -it --entrypoint "dar-backup" "$IMAGE" -v|grep -P "dar-backup +\d+.\d+.\d+"

# `dar` version
docker run --rm --entrypoint dar "$IMAGE" --version 2>/dev/null|grep "dar version"

# `par2` version
docker run --rm --entrypoint par2 "$IMAGE" --version
```

### Github Container Registry images

The only change to the above is the IMAGE specification.

```bash
IMAGE=ghcr.io/per2jensen/dar-backup:0.5.1-alpha

# dar-backup version
docker run --rm -it --entrypoint "dar-backup" "$IMAGE" -v|grep -P "dar-backup +\d+.\d+.\d+"

# `dar` version
docker run --rm --entrypoint dar "$IMAGE" --version 2>/dev/null|grep "dar version"

# `par2` version
docker run --rm --entrypoint par2 "$IMAGE" --version
```

Or get everythin in one go in a more verbose way.

```bash
IMAGE=ghcr.io/per2jensen/dar-backup:0.5.1-alpha
docker run --rm --entrypoint "" "$IMAGE" bash -c "dar-backup -v; dar --version; par2 --version"
```

### Check LABELS on a Github Container Registry image

This example uses `jq` (on Ubuntu, install this way "sudo apt install jq"))

```bash
IMAGE=ghcr.io/per2jensen/dar-backup:0.5.1-alpha
docker inspect "$IMAGE" --format '{{json .Config.Labels}}' | jq
```
