# Large-scale metrics dashboard

The repository includes a read-only [Datasette](https://datasette.io/)
dashboard for exploring large-scale test history. It works immediately from a
checkout using the tracked `doc/test-report/large-scale-results.jsonl` file; a
local large-scale test environment is not required.

## Quickstart

Requirements:

- Python 3.10 or newer
- Docker with a running daemon

From the repository root:

```bash
./run_metrics_dashboard.sh
```

The launcher rebuilds a disposable SQLite database, builds the pinned
Datasette image using Docker's normal layer cache, and serves the dashboard at:

```text
http://127.0.0.1:8001/-/dashboards/large-scale
```

Press `Ctrl-C` to stop it. Datasette is published only on the IPv4 loopback
interface. The container runs without Linux capabilities, with a read-only
root filesystem, and opens the generated database as immutable.

## Data sources

The dashboard database is derived from, and never replaces, its sources:

1. `doc/test-report/large-scale-results.jsonl` supplies the tracked run
   history. Schema versions 2 through 10 are supported. Older records retain
   their available top-level timing and memory values; schema-v10 records add
   normalized phase, workload, artifact, mutation, check, and bit-rot tables.
2. `/data/tmp/image-large-scale-test/results/dar-backup-metrics.db` is imported
   automatically when it exists. Its `backup_runs`, `restore_test_samples`, and
   `restore_test_fail_reasons` data becomes the `engine_*` dashboard tables.
   A checkout on another machine still works; those optional tables are simply
   empty.

The default generated file is:

```text
.cache/dar-backup-dashboard/large-scale-dashboard.db
```

`.cache/` is ignored by Git. Construction uses a fresh temporary database in
the destination directory and an atomic replacement, so invalid source data
cannot partially overwrite the previous dashboard.

## Configuration

Environment variables customize the one-command launcher:

| Variable | Default | Purpose |
|---|---|---|
| `RESULTS_JSONL` | `doc/test-report/large-scale-results.jsonl` | JSONL history to normalize |
| `BACKUP_METRICS_DB` | Auto-detected `/data/.../dar-backup-metrics.db` | Operational SQLite source; set to an empty string to disable importing it |
| `DASHBOARD_OUTPUT` | `.cache/dar-backup-dashboard/large-scale-dashboard.db` | Disposable generated SQLite database |
| `DASHBOARD_PORT` | `8001` | Local TCP port, from 1 through 65535 |
| `DASHBOARD_IMAGE` | `dar-backup-metrics-dashboard:dev` | Local dashboard image tag |
| `DOCKER` | `docker` | Docker-compatible executable name without extra arguments |

For example:

```bash
RESULTS_JSONL=/srv/results/large-scale-results.jsonl \
BACKUP_METRICS_DB=/srv/results/dar-backup-metrics.db \
DASHBOARD_PORT=9000 \
./run_metrics_dashboard.sh
```

If `BACKUP_METRICS_DB` is explicitly set to a nonexistent or incompatible
database, the build fails with a schema diagnostic. It does not silently omit
an explicitly requested source.

## Database layout

The generated database exposes these main tables and views:

- `runs` and `run_performance`: normalized history and derived throughput
- `phases` and `phase_process_memory`: lifecycle duration and coarse RSS data
- `artifacts` and `artifact_summary`: archive slices and PAR2 overhead
- `mutations`: deliberate DIFF/INCR workload changes
- `check_results`: flattened lifecycle result evidence
- `bitrot_phases` and `bitrot_segments`: injection and repair evidence
- `engine_backup_runs` and `engine_run_performance`: optional operational
  backup metrics
- `engine_restore_samples`: optional sampled restore checks

The dashboard is intended for engineering comparison, not as a source of new
canonical metrics. The JSONL history and operational database remain the
authoritative inputs.
