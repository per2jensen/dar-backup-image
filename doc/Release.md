# Development notes

## Release flow

Update the files:

- `IMAGE_VERSION` — set to the new release version (e.g. `0.5.23`)
- `DAR_BACKUP_VERSION` — if dar-backup version has changed
- `DAR_VERSION` — if DAR version has changed
- `Changelog.md` — document what changed

Commit and push to main.

The Makefile keeps `FINAL_VERSION=dev` as its development default, but
release-related targets require `FINAL_VERSION` to equal the committed
`IMAGE_VERSION` exactly. For example:

```bash
make FINAL_VERSION="$(cat IMAGE_VERSION)" dry-run-release
```

### Local sanity check (optional but recommended)

```bash
DAR_BACKUP_IMAGE_VERSION=$(cat IMAGE_VERSION)

# Start from scratch, no dev images to interfere
make dev-nuke

# Build and test
make  dev
make  test

# Confirm the saved image is self-documenting and its bundle is intact
docker run --rm dar-backup:dev docs --list
docker run --rm dar-backup:dev docs --verify
docker run --rm dar-backup:dev info

```

### Release

Trigger the **Manual Docker Release** workflow via GitHub Actions `workflow_dispatch`.

The workflow will:

1. Require a dispatch from `main` and lock the source to the full dispatch SHA
2. Validate `IMAGE_VERSION` and abort if either the Git or Docker tag exists
3. Build the dev image and run the test suite from the immutable source checkout
4. Create the final release image and verify its CLI version, OCI labels, source
   revision, and embedded license
5. Generate a CycloneDX SBOM and scan with Grype — hard gate on High/Critical
6. Revalidate that `main` still points to the selected source commit
7. Invoke the shared publisher to push only
   `per2jensen/dar-backup:VERSION` as a candidate
8. Sign the candidate digest with cosign and attach the SBOM attestation
9. Pull that immutable digest from Docker Hub, execute `dar-backup --version`,
   and verify both the CLI version and OCI image-version label exactly
10. Roll back an attempted but unverified version tag and publish a failure
    badge if publication or remote verification fails; the previous `:latest`
    remains untouched
11. Promote the remotely verified digest to `:latest`, pull `:latest`, and
    require it to resolve to the same signed digest
12. Update `build-history.json`, README, cosign badge, and clonepulse annotation
    in the separate housekeeping checkout
13. Create the annotated `vVERSION` tag on the exact source SHA and push it
14. Create a GitHub Release with the SBOM and SARIF as assets

The README release table is regenerated entirely from `doc/build-history.json`
during the workflow. It can also be refreshed or verified independently:

```bash
python3 scripts/update_readme_releases.py
python3 scripts/update_readme_releases.py --check
```

> **Note:** Do NOT manually create the git tag before triggering the workflow —
> the workflow creates it at the right moment after all steps have succeeded.

### Immutable release-source policy

Manual releases use two separate checkouts. They must never be combined by
copying source or orchestration files between revisions.

- The workflow may only be dispatched from `refs/heads/main`.
- `SOURCE_SHA` is the full 40-character `${{ github.sha }}` selected by the
  dispatch. Operators do not enter a SHA manually.
- The source checkout is detached explicitly at `SOURCE_SHA`. All application
  source, tests, build scripts, scans, and image inputs come from that checkout.
- At initial checkout and again immediately before the first Docker push,
  `SOURCE_SHA` must equal `refs/remotes/origin/main`. If `main` advances, the
  release stops and must be restarted from the newer commit.
- Release housekeeping uses a second checkout that initially matches
  `SOURCE_SHA`. Only generated SBOM/SARIF artifacts cross from the source
  checkout into it.
- The annotated `vVERSION` tag points directly to `SOURCE_SHA`, not to a later
  housekeeping commit. The tag therefore identifies exactly what was built.
- The complete source SHA is recorded in the OCI revision label, build history,
  GitHub Release metadata, and job summary.
- External GitHub Actions are pinned to full immutable action commit SHAs; the
  human-readable version remains in an adjacent comment for update tooling.
- Release and refresh publication use the same concurrency group, preventing
  either workflow from racing the other's update of `:latest`. Git pushes
  remain non-forced so a concurrent `main` update cannot be overwritten.

The shared local composite action at `.github/actions/publish-image` defines
the Docker publication boundary for both workflows. It logs in, pushes the
versioned candidate, captures its immutable digest, signs and attests it, pulls
that digest back from Docker Hub, runs its CLI version check, verifies its OCI
version, promotes it to `:latest`, and finally pulls and checks `:latest`.

Promotion of the remotely verified digest to `:latest` is the publication
boundary. A failure before remote verification removes the attempted candidate
version tag. A failure after the candidate has been verified does not delete
that valid signed version. A failure in later Git or GitHub housekeeping also
does not delete a valid signed image; housekeeping must instead be repaired
against the already-published digest.

### Weekly refresh source policy

The weekly refresh uses three independent checkouts:

- `source/` is the immutable application commit recorded by the latest
  `doc/build-history.json` entry. Its own Makefile, application files, and tests
  are used together; files from `main` are never overlaid.
- `orchestration/` is the full workflow commit from `main`. The shared
  publisher and its focused tests run from this exact revision.
- `housekeeping/` starts at that same orchestration commit and is the only tree
  allowed to receive generated SBOM/SARIF evidence and metadata changes.

The latest build-history record is authoritative for both the image version and
its application source. The workflow validates its `tag` and `git_revision`,
resolves the recorded revision to a full commit SHA, and checks out that exact
commit. It also resolves `vBASE_VERSION` and reports a warning when a historical
release tag points to a later housekeeping commit instead of the recorded build
source. An invalid or unresolvable recorded revision is fatal; the workflow
never silently falls back to the tag.

The workflow verifies clean checkouts and exact commits before building, then
revalidates the application commit and current `main` immediately before
publication. The application and orchestration SHAs are included in the job
summary, while the full application SHA is stored in build history. The
annotated refresh tag targets the housekeeping commit containing that history
record and records both the application SHA and signed image digest in its
message. The housekeeping branch and tag are pushed atomically, so neither can
become visible without the other. Generated SBOM and SARIF evidence is
force-staged only at this controlled boundary despite the repository's general
ignore rules.

Release tags created by the current release workflow point directly to their
source SHA. Historical stable release tags may instead point to housekeeping;
the mismatch warning exists for those older tags. The cosign badge is changed
to `failed` only when the shared publication transaction itself fails, not when
later Git housekeeping encounters a problem.

Refresh finalization uses a dedicated Make target that permits only a positive
numeric `BASE_VERSION-N` output. `BASE_VERSION` comes from the latest
`doc/build-history.json` entry, while that same record's `git_revision` selects
the immutable application checkout. Refresh intentionally does not consult
`IMAGE_VERSION`, which may already describe a future release. Source revisions
predating the dedicated target use the same tested validator from the isolated
orchestration checkout as an explicit compatibility path; the recorded
application tree is still never modified.

### After release

The weekly image refresh (every Saturday 04:17 UTC) will automatically pick up
the new version from `build-history.json` and publish `VERSION-1`, `VERSION-2`
etc. as `:latest` going forward.

To archive the Docker image locally alongside the dar archives:

```bash
~/.local/bin/save-dar-backup-image.sh
```

This checks `build-history.json` on GitHub and saves the latest image as a
compressed tar to `$DOCKER_ARCHIVE_DIR` (default: `~/docker-archives`) if not
already archived.
