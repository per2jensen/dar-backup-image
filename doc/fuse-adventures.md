<!--
SPDX-FileCopyrightText: 2025-2026 Per Jensen

SPDX-License-Identifier: GPL-3.0-or-later

This file is part of dar-backup-image:
https://github.com/per2jensen/dar-backup-image

License terms and warranty disclaimer:
https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
-->

# FUSE Adventures: Backing Up pCloud Through Docker

## Status and scope

This is an experimental field note, not a general FUSE-support claim. The
procedure worked on one Ubuntu 24.04 host on 2026-09-09 with:

- Linux `7.0.0-30-generic` on x86-64
- Docker client and server `28.4.0`
- `pCloud.fs` mounted read-only at `/home/pj/pCloudDrive`
- the FUSE mount owned by numeric UID/GID `1000:1000`
- `per2jensen/dar-backup:1.0.0-rc1`, with image digest
  `sha256:4a7e54fca3cd1a1c8fc935f868eed8082322b8ac39bf5cef76cd1c33500f5fe3`

The result may differ with another FUSE implementation, Docker version,
kernel, distribution, user-namespace configuration, or pCloud release. This
setup deliberately does not change `/etc/fuse.conf` or enable FUSE access for
other host users.

## Why the direct bind failed

The original source was:

```text
/home/pj/pCloudDrive/Automatic Upload/Per - iPhone/2026
```

The shell quoted the spaces correctly. The failure happened later, while the
Docker daemon tried to prepare the bind mount. A direct bind test reported:

```text
invalid mount config for type "bind": stat /home/pj/pCloudDrive: permission denied
```

The FUSE mount permitted its owning user to access it, but the system Docker
daemon could not use the FUSE mountpoint itself as a bind source. The
container's `--user 1000:1000` setting could not help because Docker prepares
host bind mounts before it starts the container process.

## The parent-bind experiment

Docker could bind `/home/pj`, which is on the ordinary host filesystem. Its
recursive bind included the already-mounted `pCloudDrive` filesystem below
that directory. Once the container started as UID/GID `1000:1000`, that process
could access the nested FUSE mount as its owner.

The following read-only probe was used:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --entrypoint /usr/bin/stat \
  --mount type=bind,src=/home/pj,dst=/data,readonly \
  per2jensen/dar-backup:1.0.0-rc1 \
  -f -c 'filesystem=%T path=%n' \
  "/data/pCloudDrive/Automatic Upload/Per - iPhone/2026"
```

The observed result was:

```text
filesystem=fuseblk path=/data/pCloudDrive/Automatic Upload/Per - iPhone/2026
```

This confirmed that the container saw the live nested FUSE filesystem rather
than only the underlying mountpoint directory.

## Backup definition

Binding `/home/pj` at `/data` changes the source's container path. Use a
dedicated definition with a narrowly selected root. Do not use the generated
default definition: its `-R /data` would select the complete mounted home
directory.

This setup block refuses to overwrite an existing definition:

```bash
(
  set -euo pipefail

  fuse_workdir=/data/tmp/1.0.0-rc
  fuse_definition="${fuse_workdir}/backup.d/pcloud-2026"

  install -d \
    "${fuse_workdir}/backups" \
    "${fuse_workdir}/backup.d" \
    "${fuse_workdir}/restore"

  if [[ -e "${fuse_definition}" ]]; then
    >&2 echo "ERROR: refusing to overwrite ${fuse_definition}"
    exit 1
  fi

  tee "${fuse_definition}" >/dev/null <<'EOF'
-am
-R "/data/pCloudDrive/Automatic Upload/Per - iPhone/2026"
-z5
-n
--slice 7G
--cache-directory-tagging
EOF
)
```

The quotation marks around the `-R` value are required because the path
contains spaces.

## Running the backup

From the repository root:

```bash
IMAGE=per2jensen/dar-backup:1.0.0-rc1 \
WORKDIR=/data/tmp/1.0.0-rc \
DAR_BACKUP_DATA_DIR=/home/pj \
scripts/run-backup.sh -t FULL -d pcloud-2026
```

In this arrangement:

```text
Host /home/pj
  -> container /data (read-only)
  -> nested container /data/pCloudDrive (pCloud FUSE)
  -> DAR root /data/pCloudDrive/Automatic Upload/Per - iPhone/2026
```

The experiment produced three DAR slices, a catalogue database, and logs under
`/data/tmp/1.0.0-rc/backups`. The first two slices were 7 GiB each and the last
was approximately 3 GiB. They were owned by `pj:pj`, as expected from the
numeric container UID/GID.

Check the recorded result rather than treating the presence of archive slices
alone as proof of success:

```bash
grep -E 'SUCCESS|FAILURE|ERROR' \
  /data/tmp/1.0.0-rc/backups/dar-backup.log |
  tail -n 20

find /data/tmp/1.0.0-rc/backups \
  -maxdepth 1 -type f \
  -printf '%u:%g %s %f\n'
```

## Warnings

- The container can see the entire `/home/pj` tree. The bind is read-only, but
  confidentiality still depends on trusting the selected image. The DAR `-R`
  setting limits what DAR archives; it is not a container security boundary.
- Use a pinned, trusted image. Do not substitute an unfamiliar image into a
  command that exposes a complete home directory.
- The nested FUSE mount must exist before the container starts. Do not assume a
  FUSE mount created later will propagate into an already-running container.
- This result depends on the container's numeric UID/GID matching the FUSE
  mount owner. Docker user-namespace remapping or a rootless setup may behave
  differently.
- Confirm that every source mount is read-only as intended. Recursive
  read-only behavior depends on the kernel and Docker configuration; in this
  experiment the pCloud mount itself was also read-only.
- Cloud-backed files may be fetched on demand. Network failures, remote service
  failures, or files changing during the run can make the backup fail or give
  it a non-snapshot-consistent view.
- Estimate both download volume and archive space before a FULL backup. This
  experiment created roughly 17 GiB of DAR slices.
- A failed run may leave partial archive material. Review the logs and use the
  application's supported cleanup workflow before retrying; do not delete
  slices or catalogue state independently.
- Success on this one Ubuntu 24.04 system on 2026-09-09 does not establish
  portable FUSE support. Retest the read-only probe and a disposable backup
  whenever the OS, kernel, Docker, image, or FUSE client changes.

For routine unattended backups, copying or synchronizing cloud data onto a
regular local filesystem remains the simpler and more predictable boundary.

Another option is to use the [PyPI based `dar-backup`](https://github.com/per2jensen/dar-backup)
installation. This has been used by the author for years to backup pCloud.