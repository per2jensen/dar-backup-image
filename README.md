# 📦 dar-backup image for container backups and more

A minimal, Dockerized backup runner using dar (Disk ARchive) and dar-backup, ready for automated or manual archive creation and restore.

This is early, the `dar-backup` images are not tested well, do not trust it too much. It will mature over time :-)

This image includes:

- dar
- par2
- python3
- [dar-backup](https://github.com/per2jensen/dar-backup) (my `dar` Python based wrapper)
- Clean, minimal Ubuntu 24.04 base (~170 MB)
- CIS-aligned permissions and user-drop via gosu

## 🔧 Image Tags

| Tag           | Base OS      | dar Version | Notes              |
| ---------     | ------------ | ----------- | ------------------ |
| `0.5.0-alpha` | Ubuntu 24.04 | 2.7.13      | Latest w/ bugfixes |

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
