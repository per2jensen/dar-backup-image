# Development notes

## Release flow

1. Commit all changes
git add . && git commit -m "Prepare release v0.5.1"

2. Run integration test
make test

3. Build and inspect the image locally
make DAR_BACKUP_IMAGE_VERSION=0.5.1 final
make DAR_BACKUP_IMAGE_VERSION=0.5.1 show-labels  # Optional sanity check

4. Tag the release in Git
git tag -a v0.5.1 -m "Release dar-backup image v0.5.1"
git push origin v0.5.1

5. Build the image again (now includes latest Git commit hash in revision label)
make DAR_BACKUP_IMAGE_VERSION=0.5.1  DAR_BACKUP_VERSION=0.8.0 final

6. Export your Docker Hub token (if not already logged in)
export DOCKER_USER=per2jensen
export DOCKER_TOKEN=your_actual_token

7. Push image to Docker Hub
make DAR_BACKUP_IMAGE_VERSION=0.5.1 push

8. Log image details
make DAR_BACKUP_IMAGE_VERSION=0.5.1 DAR_BACKUP_VERSION=0.8.0 log-pushed-build-json

9. Optionally print the tag layout
make DAR_BACKUP_IMAGE_VERSION=0.5.1 tag
