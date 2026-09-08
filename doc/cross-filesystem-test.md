<!--
SPDX-FileCopyrightText: 2025-2026 Per Jensen

SPDX-License-Identifier: GPL-3.0-or-later

This file is part of dar-backup-image:
https://github.com/per2jensen/dar-backup-image

License terms and warranty disclaimer:
https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
-->

# Cross-filesystem backup and restore test

`run_cross_filesystem_test.sh` is a host-specific integration harness for the
Btrfs `/home` and ZFS `/data` layout. It is separate from the large-scale
torture test and does not change its scripts or result history.

The harness creates a FULL archive, verifies DAR and per-slice PAR2 integrity,
restores the archive, and compares content plus portable POSIX metadata. It
supports these scenarios:

- `etc-to-home`: write the archive beneath `/data/tmp` and restore `/etc`
  beneath `/home/pj/tmp/restore-test`.
- `home-to-data`: back up explicitly selected files or directories below
  `/home/pj` and restore them beneath `/data/tmp`.
- `both`: run both scenarios, stopping at the first unexpected failure.

## Examples

The default runs the deliberate non-root `/etc` permission test. A passing run
proves that unreadable system files caused a clear failure and that the harness
did not claim an incomplete archive as usable:

```bash
./run_cross_filesystem_test.sh
```

If the selected `dar-backup` version describes its partial error-5 archive as
usable, the harness deliberately returns failure and retains that run for
inspection. This is distinct from a cleanly rejected non-root backup.

Use root inside the container for a complete `/etc` round trip. The host script
itself does not need to be invoked through `sudo`:

```bash
./run_cross_filesystem_test.sh --backup-user root
```

Back up selected home data as `pj` and restore it to ZFS:

```bash
./run_cross_filesystem_test.sh \
  --scenario home-to-data \
  --home-source /home/pj/Documents \
  --home-source '/home/pj/Pictures/family photos' \
  --dataset-id personal-files-v1
```

Use `--scenario both` with at least one `--home-source` to exercise both
directions. Add `--keep` to retain archives, logs, source manifests, and
restored trees. `--build` runs `make dev`; otherwise the local
`dar-backup:dev` image must already exist.

## Safety and metadata contract

Sources are mounted read-only. Home selections must be absolute descendants of
`/home/pj`; selecting the complete home directory or a path overlapping the
test outputs is rejected. Non-root home restores also reject source ownership
that `pj` cannot reproduce.

Every work and restore directory is freshly generated and marked. Automatic
cleanup only removes marked directories beneath the configured bases. Failed
runs are retained for diagnosis. `/etc` archives can contain credentials and
other secrets, so run directories use mode `0700` and a restrictive umask.

The comparison covers entry types, SHA-256 file content, symbolic-link targets,
hard-link relationships, modes, numeric ownership, POSIX ACLs, and `user.*`
extended attributes. It deliberately excludes timestamps, inode numbers,
physical allocation, and filesystem-specific Btrfs or ZFS attributes.

## JSONL results

Each initialized invocation appends exactly one schema-v1 record to:

```text
/data/tmp/dar-backup-cross-filesystem-test/results/cross-filesystem-results.jsonl
```

The history persists when successful archives and restores are cleaned. Each
line records the requested scenario, execution identity, image and Git
provenance, filesystem devices, source/archive sizes, timings, lifecycle
checks, comparison counts, and the overall result. `both` uses one record with
nested `etc_to_home` and `home_to_data` objects.

Home path names are intentionally absent. The record contains only the
selection count, optional opaque `--dataset-id`, and backup-definition SHA-256.
Results are local to `/data`; the harness never modifies a tracked history
file.

## Requirements

- `/home` must be Btrfs and `/data` must be ZFS.
- Docker must be available to the invoking account.
- The local selected image must include `dar-backup`, DAR, PAR2, and manager.
- `pj` must exist for the default identity mode.

The harness exits before creating a result when arguments are invalid or when
the persistent results directory cannot be initialized. Once initialized, its
exit handler records completed and aborted runs.
