# Building Development Images

This is the canonical guide for building and testing local `dar-backup`
development images.

## Prerequisites

Install Docker, GNU Make, Python 3, and `jq`. Run all commands from the
`dar-backup-image` repository root.

Docker BuildKit must be available for local-wheel builds because the Makefile
passes the external distribution directory as a named, read-only build context.
Current Docker installations use BuildKit by default.

## Build from the pinned PyPI release

The default build installs the `dar-backup` version recorded in
`DAR_BACKUP_VERSION` from PyPI:

```bash
make dev
```

This creates `dar-backup:dev`.

Override the pinned version without editing the version file when needed:

```bash
make dev DAR_BACKUP_VERSION=1.1.10
```

## Build from a local dar-backup wheel

Build the wheel in the `dar-backup` source checkout first. Then select local
installation explicitly and pass the directory containing the wheel:

```bash
make dev \
  DAR_BACKUP_INSTALL_SOURCE=local \
  DAR_BACKUP_LOCAL_DIST=/home/pj/git/dar-backup/v2/dist \
  DAR_BACKUP_VERSION=1.1.11.dev42
```

By default, the expected filename is derived from the version:

```text
dar_backup-<DAR_BACKUP_VERSION>-py3-none-any.whl
```

For a wheel with a different valid filename, specify its basename explicitly:

```bash
make dev \
  DAR_BACKUP_INSTALL_SOURCE=local \
  DAR_BACKUP_LOCAL_DIST=/absolute/path/to/dist \
  DAR_BACKUP_LOCAL_WHEEL=dar_backup-1.1.11.dev42-custom-py3-none-any.whl \
  DAR_BACKUP_VERSION=1.1.11.dev42
```

`DAR_BACKUP_LOCAL_WHEEL` must be a basename, not a path. The build validates
that the file is a wheel for the `dar-backup` project and that its embedded
version exactly matches `DAR_BACKUP_VERSION`. The wheel directory is mounted
read-only during the installation step; the artifact is not copied into this
repository's build context.

Only `dar-backup` itself comes from the local wheel. Its Python dependencies
are still resolved from PyPI, so this is not a fully offline build.

## Verify the development image

Check the installed CLI version and package provenance:

```bash
docker run --rm --entrypoint dar-backup dar-backup:dev --version
docker inspect dar-backup:dev \
  --format '{{ index .Config.Labels "org.dar-backup.install-source" }}'
docker inspect dar-backup:dev \
  --format '{{ index .Config.Labels "org.dar-backup.wheel.sha256" }}'
```

The source label is `pypi` for the default build and `local` for a local-wheel
build. The wheel label contains its SHA-256 for local builds and
`not-applicable` for PyPI builds.

### Interactive documentation

The image registers `dar-backup`, `cleanup`, and `manager` completion
system-wide. In an interactive Bash container, documentation topics can be
discovered and selected directly:

```console
dar-backup --doc <TAB><TAB>
dar-backup --doc restoring
```

Running the image without arguments prints the documentation front page. It
also points users to the installed `dar` and `par2` command manuals.

The manuals generated from the verified DAR source are also installed:

```bash
man dar
man dar_manager
man par2
man par2repair
```

DAR manuals are available for `dar`, `dar_cp`, `dar_manager`, `dar_slave`,
`dar_split`, and `dar_xform`. The installed PAR2 commands and manuals are
`par2`, `par2create`, `par2repair`, and `par2verify`.

Run the complete image test suite without rebuilding:

```bash
make test-nobuild IMAGE=dar-backup:dev
```

Or build and test in one operation, repeating the local-wheel variables when
applicable:

```bash
make test
```

## Cache and rebuild targets

`make dev-clean` removes the current development image and dangling layers,
then rebuilds it. `make dev-nuke` also removes all Docker build caches and
images before performing a no-cache build. Pass the same local-wheel variables
to either target when testing a local artifact.

## Publishing boundary

Images built from local wheels are development artifacts. The `push` target
checks the image's `org.dar-backup.install-source` label and refuses to publish
an image unless the value is `pypi`.

Release and dry-run-release workflows therefore continue to use the pinned
PyPI package. Build and test a clean PyPI-sourced development image before
starting a release workflow.
