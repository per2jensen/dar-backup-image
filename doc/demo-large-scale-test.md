# Demo: Large-Scale Backup, Bitrot Recovery, and PITR Restore, Fully Containerized

`run_large_scale_test.sh` runs `dar-backup`'s complete backup lifecycle — FULL,
DIFF, and INCR backups, `dar`/`par2` integrity checks, bitrot injection and
repair, and a Point-In-Time-Recovery (PITR) restore with sha256 content
verification — entirely inside Docker containers built from this repo, against
real data of whatever size you point it at.

It exists as a pre-release torture test for the `dar-backup` image, but it
doubles as a good demo of what a full backup/verify/repair/restore cycle looks
like when run entirely containerized, with no host-side install beyond Docker.

Key features demonstrated:

- FULL → DIFF → INCR backup chain, driven through the image's default
  entrypoint exactly as a real user would invoke it
- `dar -t` integrity checks and `par2 verify` after every backup
- Reproducible bitrot simulation with contiguous, fragmented, and archive-edge
  modes: confirm `dar -t` detects the damage, repair every affected slice once
  with its own PAR2 set, and confirm `dar -t` passes again
- Point-in-Time Recovery restore of the latest primer state via `manager
  --restore-path`, with hard-link and deletion-record verification
- sha256 checksum verification of every restored file against the live source
- optional complete archive-root PITR restore: automatic through 25 GiB by
  default, forceable at any size, or explicitly disabled, with the
  same-filesystem `portable-posix-v1` metadata profile
- A structured JSONL result appended to a results directory (and mirrored into
  this repo's `doc/test-report/`, for tracking metrics release over release)

---

## Prerequisites

- Docker installed, and enough free disk space under `BASE_DIR`'s filesystem —
  the script's own preflight check requires roughly 2x the size of the data
  you point it at (archive + par2 redundancy + a restore copy)
- `make`, unless you set `BUILD_IMAGE=false` and point `IMAGE` at an
  already-built or already-pulled image
- host `findmnt`, `stat`, `setfacl`, and `setfattr` commands; the inner harness
  fails preflight with a specific error when one is unavailable
- Some real data to back up — see [Pointing it at your own data](#pointing-it-at-your-own-data) below

### ZFS prerequisites

The `portable-posix-v1` profile requires Linux POSIX ACLs and extended
attributes. OpenZFS datasets may have ACLs disabled even though the filesystem
itself supports them. Configure the dataset containing both the source and
`BASE_DIR` once as an administrator, replacing `pool/dataset` with the source
reported by `findmnt`:

```bash
findmnt -T /data -n -o SOURCE
sudo zfs set acltype=posix pool/dataset
sudo zfs set xattr=sa pool/dataset
```

`acltype=posix` is required. Extended attributes must also be enabled;
`xattr=sa` is the recommended ZFS storage mode for ACL- and xattr-heavy
metadata. Verify the effective mount before starting the test:

```bash
findmnt -T /data -o TARGET,SOURCE,FSTYPE,OPTIONS
```

A correctly configured Linux ZFS mount reports `xattr` and `posixacl`, for
example:

```text
/data pool/dataset zfs rw,noatime,xattr,posixacl,casesensitive
```

If it reports `noacl`, `setfacl` will fail with `Operation not supported`.
Changing ZFS dataset properties requires administrative access, but afterward
the large-scale test itself can run as an ordinary user such as `pj`; that user
owns the generated ACL and xattr fixtures.

### Ownership-preserving restore execution

Start `run_large_scale_test.sh` as your ordinary user; do not invoke the whole
harness with `sudo`. Backup creation, archive verification, bitrot injection,
PAR2 repair, and result comparison remain unprivileged. Only manager's PITR
extraction containers run with UID/GID `0:0` and `--preserve-ownership`, because
setting arbitrary archived numeric UID/GID values is a root-only operation.

The root container receives `BASE_DIR` read-only. The selected restore target
and persistent results directory are mounted back read-write as narrow
overlays. Before extraction, the harness validates that the target is exactly
the current run's `RESTORE_DIR` or `FULL_RESTORE_DIR`, rejects symlinks, empties
it through a root container, and makes the empty target root-owned to satisfy
manager's restore safety policy. Automatic cleanup uses the same scoped path.
With `--keep`, faithfully restored ownership is retained and some entries may
require root or a root container to remove later.

The Docker daemon must permit container root to apply host numeric ownership
on bind-mounted files. Prove that path before a large run with the two-case,
few-second regression test:

```bash
IMAGE=dar-backup:dev pytest -q tests/test_restore_ownership.py -vv
```

The positive case archives a tiny file with an alternate numeric GID and
proves that root manager extraction restores it exactly. The negative case
proves that the same `--preserve-ownership` request cannot satisfy the contract
through the previous unprivileged extraction model.

## Quick start

```bash
./run_large_scale_test.sh
```

With no environment variables set, this builds `dar-backup:dev` and runs the
full test against the author's own personal photo folder default
(`SOURCE_GLOB=billeder/2013`, under `/data`) — which won't exist on
your machine. Read on to point it at your own data.

## Pointing it at your own data

Every value the script uses is an environment variable with the shown default
— set any of them to override:

| Variable | Default | Purpose |
|---|---|---|
| `BASE_DIR` | `/data/tmp/image-large-scale-test` | Working directory for this run's archives, par2 files, restore output, and results. Must be at least two directories deep. |
| `SOURCE_GLOB` | `billeder/2013` | Real data to back up, **relative to `BASE_DIR`'s own top-level directory** (see below) |
| `IMAGE` | `dar-backup:dev` | Docker image under test |
| `BUILD_IMAGE` | `true` | Set `false` to skip `make dev` — e.g. when `IMAGE` already points at a pulled/pre-built image |
| `SLICE_SIZE` | `10G` | dar `-s` slice size; a positive integer with an explicit `k`, `M`, `G`, `T`, `E`, `Z`, or `Y` unit |
| `COMPRESSION` | `6` | dar `-z` compression level (1-9) |
| `BITROT` | `true` | Set `false` to skip the corrupt/detect/repair phases |
| `BITROT_SEED` | *(generated)* | Optional unsigned 64-bit seed that exactly replays the random bitrot selections |
| `BITROT_MODE` | `contiguous` | `contiguous` for one random 2% range, `fragmented` for the same budget across 2–10 separated regions, or `edges` for bounded windows at the start of slice 1 and end of the numerically final slice |
| `ADVERTISE` | `false` | Set `true` to request badge publication; the harness still requires a successful run whose measured source is at least 100 GiB |
| `TEST_NAME` | `Large scale torture test` | Human-readable public badge label stored with the result |
| `ADVERTISE_CLASS` | *(image version or revision)* | Public tested version/class; set explicitly for specialized engineering tests |
| `FULL_RESTORE_MODE` | `auto` | `auto` restores sources at or below the threshold, `forced` restores at any size, and `disabled` skips the complete restore |
| `FULL_RESTORE_THRESHOLD_GIB` | `25` | Inclusive source-size threshold in GiB used only by `auto` mode |
| `DEFINITION` | *(unset)* | Full backup-definition body — see [Full backup-definition control](#full-backup-definition-control) |

**The one thing that trips people up**: `BASE_DIR`'s top-level directory
doubles as the read-only mount point for your real source data, and the
generated backup definition's `-R` is derived from it automatically. That
means `SOURCE_GLOB` must resolve to a real path *under that same top-level
directory* — not just anywhere on disk.

Concretely: suppose your photos live at `/home/alice/Pictures/vacation2025`.

```bash
BASE_DIR=/home/alice/dar-backup-test \
SOURCE_GLOB=alice/Pictures/vacation2025 \
./run_large_scale_test.sh
```

`BASE_DIR`'s top-level directory is `/home`, so the script mounts `/home`
read-only into every container and derives `-R /home` for the backup
definition — `SOURCE_GLOB` is then the path to your photos *relative to
`/home`*, i.e. `alice/Pictures/vacation2025` (which resolves back to the real
absolute path `/home/alice/Pictures/vacation2025`).

If `BASE_DIR` and your real data don't share a top-level directory, the script
fails fast during preflight rather than silently backing up the wrong thing —
see `scripts/large_scale_test.sh` for the full validation logic.

For the complete-restore verification, the source tree and restore directory
must also be on the same filesystem device. A nested mount beneath `BASE_DIR`
does not provide a cross-filesystem escape hatch: if a compared source or
restore entry has another `st_dev`, the run fails the explicit metadata
contract.

### This is a test-script artifact, not a dar-backup limitation

Nothing about `dar-backup` or the Docker image requires your data and your
backup destination to live under a shared top-level directory. In normal
usage, `data`, `backups`, `backup.d`, and `restore` are four completely
independent bind mounts — your source data can be on your laptop's disk while
`backups` lands on a USB drive, a NAS mount, or anywhere else entirely
unrelated. See [demo-containerized-dar-backup.md](demo-containerized-dar-backup.md)
and [dar-backup-mount-scenarios.md](dar-backup-mount-scenarios.md) for how
real invocations mount these independently.

The shared-top-level-directory constraint exists purely because this is a
*test harness*, not a backup tool invocation: `large_scale_test.sh` needs a
single read-only bind mount that covers both your real source data **and**
its own synthetic "diff-primer" fixture (created under `BASE_DIR`, to exercise
DIFF/INCR/hard-link/deletion logic deterministically) — so that one `-R` root
can reach both without translating paths between host and container. That's a
convenience for keeping the test script itself simple, not a property of
`dar-backup` or of how the image is meant to be run day to day.

## Full backup-definition control

`SOURCE_GLOB`/`SLICE_SIZE`/`COMPRESSION` cover the common case. Use `DEFINITION`
when a run needs several literal source paths or literal pruned subtrees. The
body is passed to DAR, but the harness deliberately supports only a small,
measurable path-selection contract; it does not attempt to parse every DAR
selection mode.

```bash
DEFINITION="$(cat <<'EOF'
-R /data
-s 10G
-z6
-am
--cache-directory-tagging
-g billeder/2013
-P billeder/2013/.recycle
EOF
)" ./run_large_scale_test.sh
```

Its own `-R` must still match `BASE_DIR`'s derived mount root, for the same
reason as above.

### `DEFINITION` path-selection contract

The harness accepts:

- exactly one `-R PATH` or `--fs-root PATH`; it must be absolute and equal the
  mount root derived from `BASE_DIR`
- one or more `-g PATH` or `--go-into PATH` entries
- zero or more `-P PATH` or `--prune PATH` entries
- optional `-am`/`--alter=mask` and optional `--cache-directory-tagging`
- shell-style single or double quotes around a path containing spaces

Every `-g` and `-P` value must be a literal path relative to `-R`: no absolute
path, `..`, wildcard, regular expression, or attached option form is accepted.
Each path must exist when source measurement runs, and each `-P` must intersect
at least one user `-g`. Repeated identical paths are harmless and measured once.

With `-am`, ordering is intentionally simpler than DAR's complete ordered-mask
language: `-am` must precede the path rules, all user `-g` entries must precede
all `-P` entries, and user re-inclusion (`-g` after `-P`) is rejected. The
harness appends its mandatory diff-primer as the final `-g`, separately from
the user contract, so ordered mode re-includes that fixture if a broad prune
would otherwise cover it. Without `-am`, a `-P` that removes any primer file
causes preflight to fail.

Selection features outside this contract are rejected, including `-I`/`-X`
masks, include/exclude list files, regex/glob/case alter modes, mount-point
filters, wildcards inside `-g`/`-P`, and attached `-gPATH`/`-PPATH` forms.
Ordinary non-selection settings such as slicing and compression continue to be
passed through. Adding another selection language requires an explicit harness
contract and measurement tests; there is no fallback interpretation.

Before backup, the harness walks the literal `-g` roots plus its primer without
following symlinks, deduplicates overlapping roots, subtracts literal `-P`
subtrees and valid cache-tagged directories, and reports candidate, pruned, and
selected regular-file counts and apparent bytes. The selected byte total drives
both disk-space preflight and the automatic complete-restore threshold. A
Docker-backed regression test compares this model with a real DAR
archive/restore selection.

## Other options

Anything you pass on the command line is forwarded straight through to
`scripts/large_scale_test.sh`, in addition to the environment variables above:

| Flag | Effect |
|---|---|
| `--keep` | Don't delete the run directory (archives, par2 files, restore output) afterward |
| `--smoketest` | Don't mirror this run's JSONL result into the tracked repo history file |
| `--advertise` | Request badge publication; cannot override failed, incomplete, or source-size-ineligible results |
| `--test-name NAME` | Override the human-readable public test name |
| `--advertise-class CLASS` | Override the tested public version/classification |
| `--par2-ratio N` | PAR2 error-correction percentage (default 5) |
| `--bitrot-seed N` | Replay the random bitrot selections made with seed N |
| `--bitrot-mode MODE` | Select `contiguous` (default), `fragmented`, or `edges` corruption |
| `--min-free-multiplier N` | Required free space as a multiple of source size (default 2) |
| `--full-restore-mode MODE` | Select `auto`, `forced`, or `disabled` complete-restore behavior |
| `--full-restore-threshold-gib N` | Set the inclusive `auto` threshold in GiB (default 25) |
| `--timeout N` | Per-command timeout in seconds (default 86400) |

Example — keep the archives around and use a lighter par2 ratio:

```bash
./run_large_scale_test.sh --keep --par2-ratio 3
```

Example — deliberately run a complete restore for a 400 GiB source:

```bash
FULL_RESTORE_MODE=forced ./run_large_scale_test.sh
```

The automatic threshold is ignored in `forced` mode, but remains recorded in
the structured result for context. `disabled` skips only the complete restore;
the targeted primer PITR restore remains mandatory in every mode.

## What a run looks like

```
══════════════════════════════════════════
  Phase 1 — FULL backup
══════════════════════════════════════════
  PASS  FULL backup completed in 4050s
  INFO  Running dar -t on FULL...
  PASS  dar -t passed: FULL
  PASS  Manifest present
  PASS  par2 verify passed all slices: FULL

══════════════════════════════════════════
  Bitrot test on large-scale-test_FULL_2026-07-07
══════════════════════════════════════════
  INFO  Injecting bitrot mode=contiguous, seed=123456789, segments=2...
  INFO  Corrupting large-scale-test_FULL_2026-07-07.4.dar: region=0, offset=10600000000, bytes=137418240, slice_bytes=10737418240
  INFO  Corrupting large-scale-test_FULL_2026-07-07.5.dar: region=0, offset=0, bytes=77330124, slice_bytes=10737418240
  PASS  dar -t correctly detected corruption
  INFO  Repairing 2 affected slice(s) with PAR2...
  PASS  par2 repair succeeded for 2 affected slice(s)
  PASS  dar -t passed after repair

  ...(DIFF and INCR repeat the same cycle)...

══════════════════════════════════════════
  Phase 3a — Point-In-Time Restore Validation (latest state)
══════════════════════════════════════════
  PASS  Restore sequence completed execution via manager
  PASS  link_original.txt correctly absent from latest-state restore
  PASS  link_target1.txt correctly absent from latest-state restore
  PASS  Hard Link Inodes match (1022305)
  PASS  INCR-tier new file present in latest-state restore

══════════════════════════════════════════
  Phase 3a — Content checksum verification
══════════════════════════════════════════
  PASS  All 119 restored file(s) match source sha256 checksums

══════════════════════════════════════════
  Phase 3b — Complete Point-In-Time Restore Validation
══════════════════════════════════════════
  INFO  Restoring the complete archive root via manager...
  PASS  Complete archive-root restore executed successfully
  PASS  All 741 restored regular-file path(s) (7855568881 byte(s)) match the live source

══════════════════════════════════════════
  Summary
══════════════════════════════════════════
FULL elapsed: 4050s (~116.23 GB)
DIFF elapsed: 8s (~0.58 GB)
INCR elapsed: 6s (~0.59 GB)
Peak Engine Memory Consumption:
  ├── dar-backup : 33.2 MB
  ├── dar backend: 34.1 MB
  ├── par2 engine: 146.9 MB
  └── db manager : 40.6 MB
Failures:      0

✓ ALL TESTS PASSED SUCCESSFULLY
```

(Taken from a real run against a 116GB photo collection; your own numbers will
scale with however much data you point `SOURCE_GLOB` at.)

## Output

- **`BASE_DIR/results/large-scale-results.jsonl`** — one JSON line per run:
  immutable image identity, source scale, elapsed time and exact archive size
  per phase, peak memory per engine, individual lifecycle-check outcomes, and
  overall pass/fail. Once the run workspace has been initialized, an `EXIT`
  handler writes exactly one result for both completed and aborted runs. Input
  or preflight failures that happen before a writable results directory exists
  cannot be recorded.
- **`BASE_DIR/results/summary-<timestamp>.txt`** — the full run transcript.
- **`doc/test-report/large-scale-results.jsonl`** — the same JSONL line
  mirrored into this repo, if that directory exists and `--smoketest` wasn't
  used. Untracked until you `git add` it, so you decide what history to keep.
- **`BASE_DIR/runs/<timestamp>/`** — archives, par2 files, and restore output
  for this specific run. Deleted automatically unless `--keep` is given.

New records use additive schema version 8. All schema-version-2 through -7
fields remain present for existing consumers and the older lines in the history
remain valid. Additional provenance includes the full harness commit and dirty
state, the requested image reference, immutable local image ID, registry digest
when available, OCI image revision/version labels, harness script version, and
the sha256 of the effective generated backup definition.

Schema v4 adds `bitrot_seed` and `bitrot_evidence`. Each completed bitrot phase
records the mode, region count, exact slice names, region indexes, offsets and
lengths, its 1 MiB injection buffer, injection and repair durations, whether
DAR detected the damage and validated the repair, plus PAR2 data blocks found,
total, and damaged for every affected slice. Multiple regions in one slice
share the result of its single PAR2 repair. Evidence is updated incrementally,
so an interrupted run retains the last completed bitrot step. Use the recorded
seed as `BITROT_SEED` (or `--bitrot-seed`) and the recorded mode as
`BITROT_MODE` (or `--bitrot-mode`) to reproduce the same choices against an
identical archive layout.

Archive-edge mode corrupts exactly 1% of the first slice from byte zero and 1%
of the final slice through EOF. A single-slice archive receives two separate
1% regions. The evidence records both the aggregate `corruption_percent: 2`
and the per-boundary `edge_percent: 1`.

Schema v5 adds the intentionally small publication envelope: `advertise`,
`test_name`, and `advertise_class`. `advertise` becomes true only when
publication was explicitly requested, the run completed successfully with no
failures, and `source_bytes` is at least 100 GiB. The remaining
engineering fields may continue evolving independently; badge presentation
uses them only when their recognized values are available and valid.

Schema v6 adds `checks.full_restore`. It records the requested mode, threshold,
measured source size, whether execution was actually reached, the decision
reason, execution/content/overall statuses, and the restored regular-file
count and byte total. This makes an automatic size skip, explicit disablement,
interrupted attempt, failed restore, and successful complete restore distinct.

Schema v7 adds `checks.pitr_restore.permission_modes`. The mandatory primer
restore now proves POSIX permission bits for deliberately varied `0600`, `0440`,
`0755`, and directory-mode fixtures on every run. Permission mismatches fail
the overall PITR result independently of content checks. This mandatory,
small PITR check remains limited to permission modes; the wider metadata
profile below is part of the optional complete restore.

Schema v8 adds the `portable-posix-v1` complete-restore metadata profile. It is
the deliberately conservative intersection supported by Linux ext4, Btrfs,
and ZFS, and verifies:

- numeric UID/GID ownership for every restored entry, including symlinks
- POSIX permission bits for every non-symlink entry
- POSIX access ACLs and directory default ACLs
- byte-exact `user.*` extended attributes, including empty and binary values
- hard-link relationships without requiring source and restore inode numbers
  themselves to match

The primer contains deterministic ownership (the invoking UID plus an available
supplemental GID, with the primary GID as fallback), access/default ACL,
three-xattr, hard-link, file-mode, and directory-mode fixtures. A successful
schema-v8 record must prove that these fixtures were actually encountered;
zero or missing evidence cannot produce a verified complete-restore claim.

The schema-v8 contract is explicitly **same filesystem**. `MOUNT_ROOT`, every
source entry selected for complete comparison, `FULL_RESTORE_DIR`, and every
restored entry must have the same `st_dev` value. The harness checks this before
the backup and again during comparison, records both filesystem types and
device numbers, and fails rather than presenting a cross-filesystem run as
equivalent evidence. Pointing `FULL_RESTORE_DIR` at a separate ext4, Btrfs, or
ZFS mount is not supported by this profile. Filesystem types outside `ext4`,
`btrfs`, and `zfs` are rejected rather than implicitly receiving the same
claim.

The profile intentionally excludes inode numbers, physical allocation,
filesystem-specific flags and properties, ZFS NFSv4 ACLs, `security.*`,
`trusted.*`, and implementation-owned `system.*` xattrs other than the two
POSIX ACL attributes. It also excludes `atime`, `ctime`, birth time, and symlink
mode bits. These values are mutable during verification, cannot be restored
portably, or do not have common semantics across the three filesystems.

The complete restore selects archive root `.` and therefore asks `manager` to
reconstruct every path represented by the latest FULL → DIFF → INCR chain.
The generated configuration sets `RESTORE_OWNERSHIP = yes`, and both PITR
invocations also pass `--preserve-ownership` explicitly so the test contract is
visible in command traces and cannot silently inherit a weaker image default.
Every restored regular file is SHA-256 compared with its live source path;
symlink targets, filesystem entry types, POSIX modes, numeric ownership, POSIX
ACLs, portable extended attributes, and hard-link topology are compared as
well. Because a custom DAR definition may intentionally exclude source files,
the restored archive tree—not the unfiltered source root—is the general
comparison boundary. The harness-owned primer has no intentional omissions and
is also checked in the source-to-restore direction so missing fixture
extraction is detected. A definition that intentionally filters ACL or
`user.*` extended-attribute data cannot satisfy `portable-posix-v1`.

The badge adds `Full restore verified ✓` only for internally consistent
schema-v6-or-later evidence: the complete restore must have been performed,
execution, content comparison, and overall status must all have passed,
restored file and byte counts must be positive, and the recorded mode and
decision must agree. Schema-v8 records must additionally contain passed,
internally consistent `portable-posix-v1` evidence, matching filesystem types
and device numbers, and positive fixture counts. Older, skipped, failed,
incomplete, or contradictory records remain publishable when otherwise
eligible but do not receive the full-restore claim.

`source_file_count` and `source_bytes` measure regular files in the effective
literal selection immediately before the FULL backup: user `-g` roots plus the
mandatory primer, minus supported `-P` pruning and cache tags. Overlapping
roots are deduplicated by absolute path and symlink targets are not followed.
The definition hash identifies the exact selection and archive options without
publishing private source paths; it is not a checksum of the source data.

Individual checks use `passed`, `failed`, `skipped`, or `not_run`. This makes a
disabled bitrot test distinguishable from a run that aborted before reaching
it. Aborted records also contain `completed: false`, `aborted_phase`, and the
original process `exit_code`.

`overall_elapsed_s` starts when `scripts/large_scale_test.sh` starts, so it
includes preflight and every lifecycle phase but excludes an optional image
build performed earlier by the wrapper.

## Notes

- **Runtime scales with data size.** A 116GB FULL backup takes roughly an
  hour; DIFF/INCR are fast since only the synthetic "diff-primer" fixture
  changes between them. Complete restore and checksum comparison add another
  full-data read/write cycle when selected. There's also a deliberate ~2-3
  minute pause before the INCR phase, to keep file mtimes cleanly separated in
  the log.
- **Peak-memory numbers are scoped to this run's own containers** (via `docker
  top` against each container's own ID) — they won't be polluted by unrelated
  `dar`/`par2`/`manager` processes elsewhere on the host, including your own
  scheduled backup jobs.
- The disk-space preflight check measures the supported definition's effective
  `-g` minus `-P`/cache-tag selection and refuses to start if `BASE_DIR`'s
  filesystem doesn't have `--min-free-multiplier` (default 2x) that many
  selected apparent bytes free.

---

Back to [README](../README.md).
