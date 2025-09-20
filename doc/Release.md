# Development notes

## Release flow

Update the files:

- DAR_BACKUP_VERSION
- DAR_VERSION

as they are used in the build pipeline.

Set the version of the envvar `DAR_BACKUP_IMAGE_VERSION`

```bash
DAR_BACKUP_IMAGE_VERSION=0.5.18
```

1. Start from scratch, no dev images to interfere

```bash
make clean-all
```

2. Run integration test

```bash
make test
```

3. Build and inspect the image locally

```bash
make FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION}  final
make FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION}  show-labels  # Optional sanity check
```

4. Tag the release in Git

```bash
git tag -a "v${DAR_BACKUP_IMAGE_VERSION}" -m "Release dar-backup image ${DAR_BACKUP_IMAGE_VERSION}"
git push origin "v${DAR_BACKUP_IMAGE_VERSION}"
```

5. Build the image again (now includes latest Git commit hash in revision label)

```bash
make  FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION} final
```

6. Export your Docker Hub token (if not already logged in)

```bash
export DOCKER_USER=per2jensen
  export DOCKER_TOKEN=your_actual_token #do not put it in history
```

7. Push image to Docker Hub

```bash
make FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION}  push
```

8. Log image details

```bash
make FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION} COMMIT_LOG=yes log-pushed-build-json
```

9. Optionally print the tag layout

```bash
make FINAL_VERSION=${DAR_BACKUP_IMAGE_VERSION} tag
```

10. Commit the logfile

```bash
git tag -d "v${DAR_BACKUP_IMAGE_VERSION}"  # Delete local tag
git tag -a "v${DAR_BACKUP_IMAGE_VERSION}" -m "Move tag to include build-history update"
git push --force origin "v${DAR_BACKUP_IMAGE_VERSION}"
```
