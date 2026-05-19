# Demo: Backup, List, List-Contents, and Selective Restore Using `dar-backup` in Docker

This demo illustrates how to use [`dar-backup`](https://github.com/per2jensen/dar-backup) to perform reliable, verifiable, and selective file backups — entirely from within a container.

Using Docker, you can mount your data, backup, and restore directories and let `dar-backup` handle slicing, verification, cataloging, and parity (par2) redundancy generation for integrity assurance.

Key features demonstrated:

- Declarative backup definitions (via `-d` or iterating over `backup.d`)
- Full backups with configurable compression and slicing
- Automatic catalog creation and integrity verification
- Par2 redundancy generation for each archive slice
- Archive inspection and selective restore (e.g., restore only `.NEF` files)

All commands run as a non-root user inside the container (using `RUN_AS_UID`) and require no host-side software beyond Docker.

---

## Prerequisites

You’ll need:

- Docker installed
- A directory with files to back up (`$DATA_DIR`)
- A mounted backup target directory (`$BACKUP_DIR`)
- A directory for restore testing (`$RESTORE_DIR`)
- One or more backup definitions in `$BACKUP_D_DIR`
- A `dar-backup` image (e.g., `per2jensen/dar-backup:latest`)

---

## Backup Definition

Below is a sample backup definition file named `media-demo-backup`, located in `${BACKUP_D_DIR}/`:

```text
# Switch to ordered selection mode (options are evaluated top to bottom)
 -am

# Root directory to operate from (inside the container)
 -R /

# Directories to include (relative to root)
 -g data

# Directories to exclude
 -P some/directory
 -P data/temp-files

# Compression level
 -z5

# Do not overwrite existing archives
# (used with -Q: dar exits if an archive already exists)
 -n

# Archive slice size
 --slice 12G

# Ignore file ownership during restore test (see docs)
--comparison-field=ignore-owner

# Skip directories marked as cache
--cache-directory-tagging
```

---

## Run a Full Backup of ~/data

```bash
DATA_DIR=/home/pj/data/2023              # Source data to backup
BACKUP_DIR=/media/pj/86e85ffe-5a77-49eb-afb4-f1eb391fcdaf/demo      # USB disk or backup destination
RESTORE_DIR=/tmp/test-restore            # Directory for restore testing
BACKUP_D_DIR=/tmp/test-backup.d          # Backup definitions location
IMAGE=per2jensen/dar-backup:latest       # dar-backup Docker image

mkdir -p "$BACKUP_DIR"
mkdir -p "$RESTORE_DIR"
mkdir -p "$BACKUP_D_DIR"

cat >  "$BACKUP_D_DIR/media-demo-backup"  << 'EOF'
-am
-R /
-g data
-P some/directory
-P data/temp-files
-z5
-n
--slice 12G
--comparison-field=ignore-owner
--cache-directory-tagging
EOF

# check environment variable to avoid unwanted pulls, if you have a tried and tested image.
DOCKER_PULL=${DOCKER_PULL:-false}
# only pull if you state so
if [[ "$DOCKER_PULL" == "true" ]]; then
  docker pull "$IMAGE"
fi

# the pull happens if :latest is not found locally
docker run --rm \
  -e RUN_AS_UID=$(id -u) \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backups \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" \
  -F --log-stdout
```

The command resulted in this output:

```text
Unable to find image 'per2jensen/dar-backup:latest' locally
latest: Pulling from per2jensen/dar-backup
b40150c1c271: Already exists 
f7c3f267c0a7: Pull complete 
d73d0508c408: Pull complete 
3a8029c5d39b: Pull complete 
afe11dc9caec: Pull complete 
634e008601e0: Pull complete 
18199f82efbb: Pull complete 
107a50bbfe8e: Pull complete 
a6d0a66e896c: Pull complete 
cad9e27d7cda: Pull complete 
6ee430e18016: Pull complete 
2185d2e42a13: Pull complete 
050bf885afc2: Pull complete 
Digest: sha256:68f48e71e32c4233590276fe5cec270aca10f7cd8216f217931103e8447f8713
Status: Downloaded newer image for per2jensen/dar-backup:latest
2026-05-17 17:17:04,810 - INFO - START TIME: 1779038224
2026-05-17 17:17:04,822 - INFO - ========== Startup Settings ==========
2026-05-17 17:17:04,822 - INFO - dar-backup:       1.1.4
2026-05-17 17:17:04,822 - INFO - dar path:         /usr/local/bin/dar
2026-05-17 17:17:04,822 - INFO - dar version:      2.7.21
2026-05-17 17:17:04,822 - INFO - Script directory: /opt/venv/lib/python3.12/site-packages/dar_backup
2026-05-17 17:17:04,823 - INFO - Config file:      /etc/dar-backup/dar-backup.conf
2026-05-17 17:17:04,823 - INFO - .darrc location:  /opt/venv/lib/python3.12/site-packages/dar_backup/.darrc
2026-05-17 17:17:04,823 - INFO - Type of backup:   FULL
2026-05-17 17:17:04,823 - INFO - ======================================
2026-05-17 17:17:04,823 - INFO - ===> Starting FULL backup for /backup.d/media-demo-backup
2026-05-17 17:27:41,480 - INFO - FULL backup completed successfully.
2026-05-17 17:27:42,138 - INFO - Catalog for archive '/backups/media-demo-backup_FULL_2026-05-17' added successfully to its manager.
2026-05-17 17:27:42,139 - INFO - Starting verification...
2026-05-17 17:40:19,912 - INFO - Archive integrity test passed.
2026-05-17 17:40:20,995 - INFO - Verification completed successfully.
2026-05-17 17:40:20,995 - INFO - Generate par2 redundancy files.
2026-05-17 17:40:20,995 - INFO - Generating par2 set for archive: media-demo-backup_FULL_2026-05-17
2026-05-17 18:16:31,418 - INFO - par2 files completed successfully.
2026-05-17 18:16:31,424 - INFO - Discord message not sent: DAR_BACKUP_DISCORD_WEBHOOK_URL not configured.
2026-05-17 18:16:31,424 - INFO - END TIME: 1779041791
```

Notice the `Digest`, it can be found in the [build-history.json](build-history.json) which keeps an audit trail of dar-backup-image builds. This proves you downloaded an image which has not been tampered with.

---

## List backups

List all backups in /backups/

```bash
$ docker run --rm  \
  -e RUN_AS_UID=$(id -u)  \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backups  \
  -v "$RESTORE_DIR":/restore  \
  -v "$BACKUP_D_DIR":/backup.d  \
  "$IMAGE" -l
```

results in:

```bash
media-demo-backup_FULL_2026-05-17 : 86924 MB
```

---

## List contents of an archive

List the contents of the archive "media-demo-backup_FULL_2026-05-17"

```bash
$ docker run --rm   -e RUN_AS_UID=$(id -u) \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backups \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" --list-contents media-demo-backup_FULL_2026-05-17
```

results in:

```text
...
[Saved][-]       [-L-][   0%][ ]  drwxrwx---   daruser	1000	567 Mio	Tue Jun 11 17:29:36 2024	data/2023-12-25-Merle-Hundebjerget
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   daruser	1000	11 Mio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8591.NEF
[Saved][ ]       [-L-][  92%][ ]  -rwxrwx---   daruser	1000	25 kio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8591.NEF.xmp
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   daruser	1000	11 Mio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8593.NEF
[Saved][ ]       [-L-][  92%][ ]  -rwxrwx---   daruser	1000	25 kio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8593.NEF.xmp
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   daruser	1000	12 Mio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8610.NEF
[Saved][ ]       [-L-][  92%][ ]  -rwxrwx---   daruser	1000	21 kio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8610.NEF.xmp
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   daruser	1000	11 Mio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8615.NEF
[Saved][ ]       [-L-][  92%][ ]  -rwxrwx---   daruser	1000	25 kio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8615.NEF.xmp
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   daruser	1000	11 Mio	Sun May 12 05:09:46 2024	data/2023-12-25-Merle-Hundebjerget/D3S_8631.NEF
...
```

---

## Restore NEF files from data/2023-12-25-Merle-Hundebjerget/

As can be seen above .NEF and .xmp files have been backed up.

In this step, we selectively restore only *.NEF files from the `data/2023-12-25-Merle-Hundebjerget` directory using the --selection option.

```bash
# first prove no files in expected restore directory
~$ ls $RESTORE_DIR/data/2023-12-25-Merle-Hundebjerget/ 
ls: cannot access '/tmp/test-restore/data/2023-12-25-Merle-Hundebjerget/': No such file or directory

$ docker run --rm  \
  -e RUN_AS_UID=$(id -u) \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backups \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" -r  media-demo-backup_FULL_2026-05-17 \
  --selection=" -I '*.NEF' -g data/2023-12-25-Merle-Hundebjerget"

$ ls $RESTORE_DIR/data/2023-12-25-Merle-Hundebjerget/ 
D3S_8591.NEF  D3S_8631.NEF  D3S_8688.NEF  D3S_8710.NEF  D3S_8716.NEF  D3S_8728.NEF  D3S_8741.NEF  D3S_8751.NEF  D3S_8761.NEF  D3S_8769.NEF  D3S_8777.NEF  D3S_8803.NEF
D3S_8593.NEF  D3S_8670.NEF  D3S_8690.NEF  D3S_8712.NEF  D3S_8719.NEF  D3S_8732.NEF  D3S_8746.NEF  D3S_8753.NEF  D3S_8763.NEF  D3S_8772.NEF  D3S_8788.NEF  D3S_8808.NEF
D3S_8610.NEF  D3S_8681.NEF  D3S_8703.NEF  D3S_8714.NEF  D3S_8722.NEF  D3S_8733.NEF  D3S_8747.NEF  D3S_8758.NEF  D3S_8767.NEF  D3S_8773.NEF  D3S_8792.NEF  D3S_8809.NEF
D3S_8615.NEF  D3S_8687.NEF  D3S_8704.NEF  D3S_8715.NEF  D3S_8724.NEF  D3S_8740.NEF  D3S_8748.NEF  D3S_8759.NEF  D3S_8768.NEF  D3S_8775.NEF  D3S_8794.NEF  D3S_8811.NEF

# NEF files restored :-)
```

Success :-)
