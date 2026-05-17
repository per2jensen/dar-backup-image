# Development notes

## Release flow

Update the files:

- `IMAGE_VERSION` — set to the new release version (e.g. `0.5.23`)
- `DAR_BACKUP_VERSION` — if dar-backup version has changed
- `DAR_VERSION` — if DAR version has changed
- `Changelog.md` — document what changed

Commit and push to main.

### Local sanity check (optional but recommended)

```bash
DAR_BACKUP_IMAGE_VERSION=$(cat IMAGE_VERSION)

# Start from scratch, no dev images to interfere
make dev-nuke

# Build and test
make FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION} dev
make FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION} test

# Optional: inspect labels
make FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION} show-labels
```

### Release

Trigger the **Manual Docker Release** workflow via GitHub Actions `workflow_dispatch`.

The workflow will:

1. Validate `IMAGE_VERSION` and abort if the git tag already exists
2. Build the dev image and run the test suite
3. Create the final release image
4. Verify CLI version and OCI labels
5. Generate SBOM (CycloneDX) and scan with Grype — hard gate on High/Critical
6. Push `per2jensen/dar-backup:VERSION` and `:latest` to Docker Hub
7. Sign the image with cosign (keyless, via GitHub OIDC → Sigstore/Rekor)
8. Attach the SBOM as a signed in-toto attestation
9. Update `build-history.json`, README, cosign badge, clonepulse annotation
10. Create the annotated git tag `vVERSION` and push it
11. Create a GitHub Release with SBOM and SARIF as assets

> **Note:** Do NOT manually create the git tag before triggering the workflow —
> the workflow creates it at the right moment after all steps have succeeded.

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
