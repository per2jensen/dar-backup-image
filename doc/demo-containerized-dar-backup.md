# Demo: Backup, List, List-Contents, and Selective Restore Using `dar-backup` in Docker

This demo illustrates how to use [`dar-backup`](https://github.com/per2jensen/dar-backup) to perform reliable, verifiable, and selective file backups — entirely from within a container.

Using Docker, you can mount your data, backup, and restore directories and let `dar-backup` handle slicing, verification, cataloging, and parity (par2) redundancy generation for integrity assurance.

Key features demonstrated:

- Declarative backup definitions (via `-d` or iterating over `backup.d`)
- Full backups with configurable compression and slicing
- Automatic catalog creation and integrity verification
- Par2 redundancy generation for each archive slice
- Archive inspection and selective restore (e.g., restore only `.JPG` files)

All commands run as a non-root user inside the container (using `RUN_AS_UID`) and require no host-side software beyond Docker.

---

## Prerequisites

You’ll need:

- Docker installed
- A directory with files to back up (`$DATA_DIR`)
- A mounted backup target directory (`$BACKUP_DIR`)
- A directory for restore testing (`$RESTORE_DIR`)
- One or more backup definitions in `$BACKUP_D_DIR`
- A `dar-backup` image (e.g., `per2jensen/dar-backup:0.5.8`)

---

## Backup Definition

Below is a sample backup definition file named `media-test-backup`, located in `${BACKUP_D_DIR}/`:

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
export DATA_DIR=/home/pj/data                   # Source data
export BACKUP_DIR=/media/pj/usb/image-test      # USB disk or backup destination
export RESTORE_DIR=/tmp/test-restore            # Directory for restore testing
export BACKUP_D_DIR=/tmp/test-backup.d          # Backup definitions location
export IMAGE=per2jensen/dar-backup:0.5.8          # dar-backup Docker image

docker run --rm \
  -e RUN_AS_UID=$(id -u) \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backups \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" \
  -F --log-stdout \
  --config /etc/dar-backup/dar-backup.conf
```

The command resulted in this output:

```text
Running as root — will drop to UID 1000
dar-backup: /usr/local/bin/dar-backup
manager:    /usr/local/bin/manager
Creating catalog databases if needed...
2025-07-15 14:42:38,084 - INFO - START TIME: 1752590558
2025-07-15 14:42:38,098 - INFO - ========== Startup Settings ==========
2025-07-15 14:42:38,098 - INFO - manager:        0.8.0
2025-07-15 14:42:38,098 - INFO - Config file:    /etc/dar-backup/dar-backup.conf
2025-07-15 14:42:38,098 - INFO - Logfile:        /backups/dar-backup.log
2025-07-15 14:42:38,098 - INFO - dar_manager:    /usr/bin/dar_manager
2025-07-15 14:42:38,098 - INFO - dar_manager v.: 1.9.0
2025-07-15 14:42:38,098 - INFO - ======================================
2025-07-15 14:42:38,098 - INFO - Create catalog database: "/backups/media-test-backup.db"
2025-07-15 14:42:38,130 - INFO - Database created: "/backups/media-test-backup.db"
Running dar-backup with args: -F --log-stdout --config /etc/dar-backup/dar-backup.conf
2025-07-15 14:42:38,399 - INFO - START TIME: 1752590558
2025-07-15 14:42:38,412 - INFO - ========== Startup Settings ==========
2025-07-15 14:42:38,412 - INFO - dar-backup:       0.8.0
2025-07-15 14:42:38,412 - INFO - dar path:         /usr/bin/dar
2025-07-15 14:42:38,412 - INFO - dar version:      2.7.13
2025-07-15 14:42:38,412 - INFO - Script directory: /usr/local/lib/python3.12/dist-packages/dar_backup
2025-07-15 14:42:38,412 - INFO - Config file:      /etc/dar-backup/dar-backup.conf
2025-07-15 14:42:38,412 - INFO - .darrc location:  /usr/local/lib/python3.12/dist-packages/dar_backup/.darrc
2025-07-15 14:42:38,412 - INFO - Type of backup:   FULL
2025-07-15 14:42:38,412 - INFO - ======================================
2025-07-15 14:42:38,413 - INFO - ===> Starting FULL backup for /backup.d/media-test-backup
[14:42:38] [~] Not a terminal — progress bar skipped.        rich_progress.py:62
2025-07-15 15:09:00,104 - INFO - FULL backup completed successfully.
2025-07-15 15:09:00,870 - INFO - Catalog for archive '/backups/media-test-backup_FULL_2025-07-15' added successfully to its manager.
2025-07-15 15:09:00,871 - INFO - Starting verification...
[15:09:00] [~] Not a terminal — progress bar skipped.        rich_progress.py:62
2025-07-15 15:32:34,601 - INFO - Archive integrity test passed.
2025-07-15 15:32:36,161 - INFO - Verification completed successfully.
2025-07-15 15:32:36,161 - INFO - Generate par2 redundancy files.
2025-07-15 15:32:36,161 - INFO - 1/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.1.dar
2025-07-15 15:34:07,126 - INFO - 1/28: Done
2025-07-15 15:34:07,127 - INFO - 2/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.2.dar
2025-07-15 15:35:39,445 - INFO - 2/28: Done
2025-07-15 15:35:39,446 - INFO - 3/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.3.dar
2025-07-15 15:37:11,080 - INFO - 3/28: Done
2025-07-15 15:37:11,080 - INFO - 4/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.4.dar
2025-07-15 15:38:44,313 - INFO - 4/28: Done
2025-07-15 15:38:44,313 - INFO - 5/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.5.dar
2025-07-15 15:40:19,181 - INFO - 5/28: Done
2025-07-15 15:40:19,181 - INFO - 6/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.6.dar
2025-07-15 15:41:50,936 - INFO - 6/28: Done
2025-07-15 15:41:50,936 - INFO - 7/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.7.dar
2025-07-15 15:43:24,203 - INFO - 7/28: Done
2025-07-15 15:43:24,204 - INFO - 8/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.8.dar
2025-07-15 15:44:59,328 - INFO - 8/28: Done
2025-07-15 15:44:59,328 - INFO - 9/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.9.dar
2025-07-15 15:46:33,888 - INFO - 9/28: Done
2025-07-15 15:46:33,889 - INFO - 10/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.10.dar
2025-07-15 15:48:06,411 - INFO - 10/28: Done
2025-07-15 15:48:06,411 - INFO - 11/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.11.dar
2025-07-15 15:49:39,303 - INFO - 11/28: Done
2025-07-15 15:49:39,303 - INFO - 12/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.12.dar
2025-07-15 15:51:17,128 - INFO - 12/28: Done
2025-07-15 15:51:17,128 - INFO - 13/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.13.dar
2025-07-15 15:52:47,425 - INFO - 13/28: Done
2025-07-15 15:52:47,425 - INFO - 14/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.14.dar
2025-07-15 15:54:20,105 - INFO - 14/28: Done
2025-07-15 15:54:20,106 - INFO - 15/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.15.dar
2025-07-15 15:55:53,255 - INFO - 15/28: Done
2025-07-15 15:55:53,256 - INFO - 16/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.16.dar
2025-07-15 15:57:26,482 - INFO - 16/28: Done
2025-07-15 15:57:26,482 - INFO - 17/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.17.dar
2025-07-15 15:59:00,838 - INFO - 17/28: Done
2025-07-15 15:59:00,838 - INFO - 18/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.18.dar
2025-07-15 16:00:36,625 - INFO - 18/28: Done
2025-07-15 16:00:36,626 - INFO - 19/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.19.dar
2025-07-15 16:02:10,804 - INFO - 19/28: Done
2025-07-15 16:02:10,805 - INFO - 20/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.20.dar
2025-07-15 16:03:45,035 - INFO - 20/28: Done
2025-07-15 16:03:45,035 - INFO - 21/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.21.dar
2025-07-15 16:05:19,207 - INFO - 21/28: Done
2025-07-15 16:05:19,207 - INFO - 22/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.22.dar
2025-07-15 16:06:54,950 - INFO - 22/28: Done
2025-07-15 16:06:54,950 - INFO - 23/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.23.dar
2025-07-15 16:08:29,715 - INFO - 23/28: Done
2025-07-15 16:08:29,715 - INFO - 24/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.24.dar
2025-07-15 16:10:03,371 - INFO - 24/28: Done
2025-07-15 16:10:03,371 - INFO - 25/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.25.dar
2025-07-15 16:11:41,641 - INFO - 25/28: Done
2025-07-15 16:11:41,641 - INFO - 26/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.26.dar
2025-07-15 16:13:15,768 - INFO - 26/28: Done
2025-07-15 16:13:15,768 - INFO - 27/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.27.dar
2025-07-15 16:14:48,841 - INFO - 27/28: Done
2025-07-15 16:14:48,841 - INFO - 28/28: Now generating par2 files for /backups/media-test-backup_FULL_2025-07-15.28.dar
2025-07-15 16:14:55,731 - INFO - 28/28: Done
2025-07-15 16:14:55,731 - INFO - par2 files completed successfully.
2025-07-15 16:14:55,731 - INFO - END TIME: 1752596095
```

---

## List backups

List all backups in /backups/

```bash
$ docker run --rm   -e RUN_AS_UID=$(id -u)   -v "$DATA_DIR":/data   -v "$BACKUP_DIR":/backups   -v "$RESTORE_DIR":/restore   -v "$BACKUP_D_DIR":/backup.d   "$IMAGE" -l  --config /etc/dar-backup/dar-backup.conf
```

results in:

```bash
Running as root — will drop to UID 1000
media-test-backup_FULL_2025-07-15 : 332661 MB
```

---

## List contents of an archive

List the contents of the archive "media-test-backup_FULL_2025-07-15"

```bash
$ docker run --rm   -e RUN_AS_UID=$(id -u) \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backups \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" --list-contents media-test-backup_FULL_2025-07-15 \
  --config /etc/dar-backup/dar-backup.conf
```

results in:

```text
...
[Saved][-]       [-L-][   0%][ ]  drwxrwx---   ubuntu	ubuntu	190 Mio	Fri Jul 11 17:27:36 2025	data/2025/2025-07
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   ubuntu	ubuntu	27 Mio	Fri Jul 11 17:12:50 2025	data/2025/2025-07/Z50_1219.NEF
[Saved][ ]       [-L-][   1%][X]  -rwxrwx---   ubuntu	ubuntu	11 Mio	Fri Jul 11 17:12:50 2025	data/2025/2025-07/Z50_1219.JPG
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   ubuntu	ubuntu	26 Mio	Fri Jul 11 17:12:45 2025	data/2025/2025-07/Z50_1217.NEF
[Saved][ ]       [-L-][   1%][X]  -rwxrwx---   ubuntu	ubuntu	10 Mio	Fri Jul 11 17:12:45 2025	data/2025/2025-07/Z50_1217.JPG
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   ubuntu	ubuntu	25 Mio	Fri Jul 11 17:05:33 2025	data/2025/2025-07/Z50_1215.NEF
[Saved][ ]       [-L-][   1%][X]  -rwxrwx---   ubuntu	ubuntu	11 Mio	Fri Jul 11 17:05:32 2025	data/2025/2025-07/Z50_1215.JPG
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   ubuntu	ubuntu	26 Mio	Fri Jul 11 17:05:32 2025	data/2025/2025-07/Z50_1214.NEF
[Saved][ ]       [-L-][   1%][X]  -rwxrwx---   ubuntu	ubuntu	11 Mio	Fri Jul 11 17:05:32 2025	data/2025/2025-07/Z50_1214.JPG
[Saved][ ]       [-L-][   0%][X]  -rwxrwx---   ubuntu	ubuntu	27 Mio	Fri Jul 11 17:05:17 2025	data/2025/2025-07/Z50_1213.NEF
[Saved][ ]       [-L-][   1%][X]  -rwxrwx---   ubuntu	ubuntu	11 Mio	Fri Jul 11 17:05:17 2025	data/2025/2025-07/Z50_1213.JPG
```

---

## Restore JPG files from data/2025/2025-07/

As can be seen above JPG's and NEF files have been backed up.

In this step, we selectively restore only *.JPG files from the data&2025/2025-07/ directory using the --selection option.

```bash
$ docker run --rm   -e RUN_AS_UID=$(id -u) \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backups \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" -r  media-test-backup_FULL_2025-07-15 \
  --selection=\" -I '*.JPG' -g data/2025/2025-07\" \
  --config /etc/dar-backup/dar-backup.conf
```

results in:

```bash
Running as root — will drop to UID 1000

# check the restored directory:  $RESTORE_DIR/data/2025/2025-07
$ ls -l $RESTORE_DIR/data/2025/2025-07/
total 58292
-rwxrwx--- 1 pj pj 12521157 jul 11 19:05 Z50_1213.JPG
-rwxrwx--- 1 pj pj 12181413 jul 11 19:05 Z50_1214.JPG
-rwxrwx--- 1 pj pj 12123001 jul 11 19:05 Z50_1215.JPG
-rwxrwx--- 1 pj pj 11349151 jul 11 19:12 Z50_1217.JPG
-rwxrwx--- 1 pj pj 12188193 jul 11 19:12 Z50_1219.JPG
```

Success :-)
