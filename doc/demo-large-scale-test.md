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
- Bitrot simulation: corrupt a slice, confirm `dar -t` detects it, repair with
  `par2`, confirm `dar -t` passes again
- Point-in-Time Recovery restore of the latest state via `manager
  --restore-path`, with hard-link and deletion-record verification
- sha256 checksum verification of every restored file against the live source
- A structured JSONL result appended to a results directory (and mirrored into
  this repo's `doc/test-report/`, for tracking metrics release over release)

---

## Prerequisites

- Docker installed, and enough free disk space under `BASE_DIR`'s filesystem —
  the script's own preflight check requires roughly 2x the size of the data
  you point it at (archive + par2 redundancy + a restore copy)
- `make`, unless you set `BUILD_IMAGE=false` and point `IMAGE` at an
  already-built or already-pulled image
- Some real data to back up — see [Pointing it at your own data](#pointing-it-at-your-own-data) below

## Quick start

```bash
./run_large_scale_test.sh
```

With no environment variables set, this builds `dar-backup:dev` and runs the
full test against the author's own personal photo folder default
(`SOURCE_GLOB=billeder/2013/2013-06`, under `/data`) — which won't exist on
your machine. Read on to point it at your own data.

## Pointing it at your own data

Every value the script uses is an environment variable with the shown default
— set any of them to override:

| Variable | Default | Purpose |
|---|---|---|
| `BASE_DIR` | `/data/tmp/image-large-scale-test` | Working directory for this run's archives, par2 files, restore output, and results. Must be at least two directories deep. |
| `SOURCE_GLOB` | `billeder/2013/2013-06` | Real data to back up, **relative to `BASE_DIR`'s own top-level directory** (see below) |
| `IMAGE` | `dar-backup:dev` | Docker image under test |
| `BUILD_IMAGE` | `true` | Set `false` to skip `make dev` — e.g. when `IMAGE` already points at a pulled/pre-built image |
| `SLICE_SIZE` | `10G` | dar `-s` slice size |
| `COMPRESSION` | `6` | dar `-z` compression level (1-9) |
| `BITROT` | `true` | Set `false` to skip the corrupt/detect/repair phases |
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

`SOURCE_GLOB`/`SLICE_SIZE`/`COMPRESSION` cover the common case. For anything
more — exclude patterns, several `-g` lines, a different `-am` selection mode —
set `DEFINITION` to a complete backup-definition body; it's used verbatim
instead of the pieced-together one, and the other three variables are ignored:

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

## Other options

Anything you pass on the command line is forwarded straight through to
`scripts/large_scale_test.sh`, in addition to the environment variables above:

| Flag | Effect |
|---|---|
| `--keep` | Don't delete the run directory (archives, par2 files, restore output) afterward |
| `--smoketest` | Don't mirror this run's JSONL result into the tracked repo history file |
| `--par2-ratio N` | PAR2 error-correction percentage (default 5) |
| `--min-free-multiplier N` | Required free space as a multiple of source size (default 2) |
| `--timeout N` | Per-command timeout in seconds (default 86400) |

Example — keep the archives around and use a lighter par2 ratio:

```bash
./run_large_scale_test.sh --keep --par2-ratio 3
```

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
  INFO  Injecting bitrot...
  PASS  dar -t correctly detected corruption
  INFO  Repairing with par2...
  PASS  par2 repair succeeded
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
  versions, elapsed time and size per phase, peak memory per engine, pass/fail.
  Always written, and always kept (unlike the run directory itself).
- **`BASE_DIR/results/summary-<timestamp>.txt`** — the full run transcript.
- **`doc/test-report/large-scale-results.jsonl`** — the same JSONL line
  mirrored into this repo, if that directory exists and `--smoketest` wasn't
  used. Untracked until you `git add` it, so you decide what history to keep.
- **`BASE_DIR/runs/<timestamp>/`** — archives, par2 files, and restore output
  for this specific run. Deleted automatically unless `--keep` is given.

## Notes

- **Runtime scales with data size.** A 116GB FULL backup takes roughly an
  hour; DIFF/INCR are fast since only the synthetic "diff-primer" fixture
  changes between them. There's also a deliberate ~2-3 minute pause before the
  INCR phase, to keep file mtimes cleanly separated in the log.
- **Peak-memory numbers are scoped to this run's own containers** (via `docker
  top` against each container's own ID) — they won't be polluted by unrelated
  `dar`/`par2`/`manager` processes elsewhere on the host, including your own
  scheduled backup jobs.
- The disk-space preflight check estimates source size from the definition's
  `-R`/`-g` lines and refuses to start if `BASE_DIR`'s filesystem doesn't have
  `--min-free-multiplier` (default 2x) that much free.

---

Back to [README](../README.md).
