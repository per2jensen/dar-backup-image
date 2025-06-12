# 📦 dar-backup

A minimal, Dockerized backup runner using dar (Disk ARchive) and dar-backup, ready for automated or manual archive creation and restore.

This is early, the `dar-backup` images are not tested well, do not trust it too much. It will mature over time :-)

This image includes:

    dar

    par2

    python3

    dar-backup Python tooling

    Clean, minimal Ubuntu 24.04 base (~170 MB)

    CIS-aligned permissions and user-drop via gosu

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
export IMAGE=dar-backup:0.5.0-alpha

docker run --rm \
  -e RUN_AS_UID=1000 \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backup \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" \
  -F --log-stdout --config /etc/dar-backup/dar-backup.conf
```
