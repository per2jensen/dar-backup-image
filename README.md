# 📦 dar-backup image for container backups and more

![CI](https://github.com/per2jensen/dar-backup-image/actions/workflows/test.yml/badge.svg)
[![# clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/badges/badge_clones.json)](https://github.com/per2jensen/dar-backup-image/blob/main/doc/weekly_clones.png)
[![Milestone](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/badges/milestone_badge.json)](https://github.com/per2jensen/dar-backup-image/blob/main/doc/weekly_clones.png)

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

These images have been put on [DockerHub](https://hub.docker.com/r/per2jensen/dar-backup/tags)

| Tag           | Base OS      | dar-backup       |dar Version |
| ---------     | ------------ | ---------------- |------------|
| `0.5.0-alpha` | Ubuntu 24.04 | dar-backup 0.8.0 | 2.7.13     |

This command can be run against an image to verify the dar-backup version:

```bash
#example
IMAGE=dar-backup:0.5.0-alpha
docker run --rm -it --entrypoint "dar-backup" "$IMAGE" -v
```

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

## Inspect program versions in an image

### Local images or Docker Hub ones

```bash
IMAGE=per2jensen/dar-backup:0.5.0-alpha

# dar-backup version
docker run --rm -it --entrypoint "dar-backup" "$IMAGE" -v|grep -P "dar-backup +\d+.\d+.\d+"

# `dar` version
docker run --rm --entrypoint dar "$IMAGE" --version 2>/dev/null|grep "dar version"

# `par2` version
docker run --rm --entrypoint par2 "$IMAGE" --version
```

Or get everything in one go in a more verbose way.

```bash
IMAGE=per2jensen/dar-backup:0.5.0-alpha
docker run --rm --entrypoint "" "$IMAGE" bash -c "dar-backup -v; dar --version; par2 --version"
```

### Check LABELS on a Github Container Registry image

This example uses `jq` (on Ubuntu, install this way "sudo apt install jq"))

```bash
IMAGE=per2jensen/dar-backup:0.5.0-alpha
docker inspect "$IMAGE" --format '{{json .Config.Labels}}' | jq
```
