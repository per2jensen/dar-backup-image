# Development notes

## Release flow

Update the files:

- `IMAGE_VERSION` — set to the new release version (for example, `1.0.0-rc1`)
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
12. Update `build-history.json`, README, cosign badge, clonepulse annotation,
    SBOM, and SARIF in the separate housekeeping checkout
13. Create one audit commit, create the annotated `vVERSION` tag on the exact
    source SHA, and atomically push `main` plus the tag
14. Create a GitHub Release with both SBOM and SARIF assets; missing assets are
    fatal rather than silently producing an incomplete release

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
  Its annotation records the source SHA, housekeeping commit, and signed image
  digest so the source and audit records can be cross-checked.
- The complete source SHA is recorded in the OCI revision label, build history,
  GitHub Release metadata, and job summary.
- External GitHub Actions are pinned to full immutable action commit SHAs; the
  human-readable version remains in an adjacent comment for update tooling.
- Release, refresh, and release finalization use the same concurrency group,
  preventing finalization from inspecting a release while another workflow is
  updating publication state. Git pushes remain non-forced so a concurrent
  `main` update cannot be overwritten.
- Release housekeeping force-stages only the generated SBOM and SARIF, which
  are ignored for ordinary local development. The complete allowlisted audit
  set is committed once. `main` and `vVERSION` are pushed with
  `git push --atomic`, so a rejected branch or tag publishes neither ref.

The shared local composite action at `.github/actions/publish-image` defines
the Docker publication boundary for both workflows. It logs in, pushes the
versioned candidate, captures its immutable digest, signs and attests it, pulls
that digest back from Docker Hub, runs its CLI version check, verifies its OCI
version, promotes it to `:latest`, and finally pulls and checks `:latest`.
Whether publication succeeds or fails, its final best-effort step removes the
Docker Hub credentials from the runner with `docker logout`; cleanup failure is
reported as a warning and cannot mask the publication result.

Promotion of the remotely verified digest to `:latest` is the publication
boundary. A failure before remote verification removes the attempted candidate
version tag. A failure after the candidate has been verified does not delete
that valid signed version. A failure in later Git or GitHub housekeeping also
does not delete a valid signed image; housekeeping must instead be repaired
against the already-published digest.

### Finalize an existing GitHub Release

The **Finalize Existing GitHub Release** workflow is a narrowly scoped recovery
operation. It is not an alternative release workflow and must not be used to
publish a new version. Use it only when the normal **Manual Docker Release** run
successfully completed Docker publication and the atomic Git housekeeping
transaction, but failed while creating the GitHub Release or uploading its
assets.

The expected recoverable state is:

- `per2jensen/dar-backup:VERSION` already exists on Docker Hub
- the image is signed and has a CycloneDX attestation
- `:latest` already points to the published digest
- `doc/build-history.json` contains exactly one matching release record
- the annotated `vVERSION` tag exists and points to the recorded source SHA
- the tag annotation records the housekeeping commit and image digest
- that housekeeping commit contains the SBOM and SARIF
- the GitHub Release is absent, incomplete, or missing an asset

To recover:

1. Open **Actions** in GitHub.
2. Select **Finalize Existing GitHub Release**.
3. Choose **Run workflow** from the `main` branch.
4. Enter the existing version without a leading `v`, for example
   `1.0.0-rc1`.
5. Run the workflow and inspect its verification summary.

Before modifying the GitHub Release, the recovery workflow fails unless all of
the following agree:

- the requested version and its unique build-history record
- the source commit in build history and the target of `vVERSION`
- the housekeeping commit and image digest recorded in the tag annotation
- the current history record, SBOM, and SARIF versus the tagged housekeeping
  commit
- the Docker version tag and recorded immutable digest
- the pulled image's `dar-backup` CLI version and OCI version/revision labels
- the Cosign certificate identity and CycloneDX attestation

Only after those checks does the shared GitHub Release finalizer create or
repair the release. Asset matching is strict, and existing assets with the same
names are replaced so retrying the recovery operation is safe. The workflow
does not build an image, push a Docker tag, sign an image, change `:latest`,
create a Git tag, or commit to `main`.

Do not use this workflow when the Docker image exists but the atomic Git
housekeeping transaction did not complete. There is no committed evidence set
from which the recovery workflow can safely create a GitHub Release, so it will
stop with an error. Do not rerun the full release blindly because its immutable
Docker and Git tag checks are expected to reject an already-used version.

### Release failure states

| Last completed boundary | Expected result | Operator action |
|---|---|---|
| Before remote candidate verification | Attempted version tag is rolled back; previous `:latest` remains | Correct the publication failure and run a new release |
| Candidate verified, but `:latest` verification failed | Valid signed version tag is retained; release is incomplete | Investigate Docker state before taking further action |
| Docker publication completed, but atomic Git housekeeping failed | Docker image remains; neither `main` nor `vVERSION` is partially pushed | Preserve the failed run and investigate; the GitHub-only finalizer is not applicable |
| Atomic Git housekeeping completed, but GitHub Release failed | Docker, `main`, and `vVERSION` are authoritative | Run **Finalize Existing GitHub Release** for the existing version |
| GitHub Release and both assets completed | Release is complete | Perform the acceptance checks below |

### Release-candidate acceptance gate

Before declaring the final 1.0 release ready, complete a real prerelease such as
`1.0.0-rc1` and verify:

- the workflow built and tested the full source SHA selected from `main`
- the versioned Docker tag and `:latest` resolve to the recorded signed digest
- a fresh pull passes the CLI version and OCI version/revision checks
- Cosign signature and CycloneDX attestation verification succeed
- `vVERSION` points to the immutable source SHA
- the tag annotation names the matching housekeeping commit and image digest
- the housekeeping commit contains build history, SBOM, SARIF, README, pages,
  badge, and clonepulse updates
- the GitHub Release is marked as a prerelease and contains non-empty SBOM and
  SARIF assets
- the build-history Docker, GitHub Release, SBOM, Rekor, and workflow links are
  valid
- the cosign badge reports success

The weekly refresh selector currently accepts only a stable `x.y.z` release or
its numeric `x.y.z-N` refresh as the newest build-history record. If a
prerelease such as `1.0.0-rc1` is the newest record, scheduled refresh fails
fast rather than treating the RC as a stable refresh base. Plan the RC window
accordingly; changing that policy is separate from GitHub Release recovery.

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

Before building, refresh requires both `vBASE_VERSION-N` and the corresponding
Docker Hub tag to be unused. Docker tag lookup fails closed: an authentication,
network, or registry error is not treated as proof that the tag is available.
After finalization, the image's OCI revision must equal the complete resolved
`APPLICATION_SHA`, and `/LICENSE` must match the release workflow's expected
SHA-256 before the SBOM, scan, or publication steps can proceed.

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

### Refresh failure states

| Last completed boundary | Expected result | Operator action |
|---|---|---|
| Before candidate publication | No remote tag or Git metadata is created | Correct the failure and rerun; tag-availability checks must still pass |
| Before remote candidate verification | Attempted refresh tag is rolled back; previous `:latest` remains | Correct the publication failure and rerun only after confirming the tag is absent |
| Candidate verified, but `:latest` verification failed | Valid signed refresh tag may remain; refresh is incomplete | Preserve the run evidence and reconcile Docker state before any retry |
| Docker publication completed, but atomic Git housekeeping failed | Signed image remains, while neither `main` nor `vVERSION-N` is partially pushed | Do not rerun blindly: the Docker collision guard will reject the used tag; reconcile build history and Git metadata against the published digest |
| Atomic Git housekeeping completed | Refresh image, history, evidence, branch, and annotated tag are authoritative | Perform the digest, signature, history, and `:latest` acceptance checks |

There is not yet an automated recovery workflow for the fourth state. The
failed Actions run, immutable digest, SBOM, SARIF, application SHA, and
orchestration SHA must be retained for a deliberate recovery change.

### After a stable release

After a stable `x.y.z` release, the weekly image refresh (every Saturday 04:17
UTC) selects the newest record from `build-history.json` and publishes
`VERSION-1`, `VERSION-2`, and so on as `:latest`. A prerelease such as
`x.y.z-rc1` is deliberately not eligible: while it is the newest history
record, the scheduled refresh stops without publishing or moving `:latest`.

To archive the Docker image locally alongside the dar archives:

```bash
~/.local/bin/save-dar-backup-image.sh
```

This selects the highest build number in `build-history.json`—a release or
weekly refresh—and saves the image as a compressed tar to
`$DOCKER_ARCHIVE_DIR` (default: `/mnt/dar/docker-archives`) if a file with that
name is not already present.

The current helper does not verify the recorded digest or Cosign identity,
checksum the saved archive, or preserve registry-hosted signatures,
attestations, SBOMs, and history beside it. Treat it as an availability helper,
not a complete provenance bundle, and follow the preservation checks in the
main README.
