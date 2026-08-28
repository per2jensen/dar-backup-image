#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
"""
Remove a tag from Docker Hub via the v2 API.

Used by the shared publication action when a candidate push was attempted but
the candidate did not complete signing, attestation, and remote verification.

Credentials are read from environment variables to avoid exposing them
in process listings or log files:

    DOCKERHUB_USER   Docker Hub username
    DOCKERHUB_TOKEN  Docker Hub password or access token

Usage:
    DOCKERHUB_USER=myuser DOCKERHUB_TOKEN=mytoken \\
        python3 scripts/remove_dockerhub_tag.py \\
            --repo per2jensen/dar-backup \\
            --tag 1.2.3
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DOCKERHUB_LOGIN_URL = "https://hub.docker.com/v2/users/login/"
DOCKERHUB_TAG_URL_TEMPLATE = "https://hub.docker.com/v2/repositories/{repo}/tags/{tag}/"


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed namespace with repo and tag.
    """
    parser = argparse.ArgumentParser(
        description="Remove an unverified Docker Hub candidate tag."
    )
    parser.add_argument("--repo", required=True, help="Repository, e.g. per2jensen/dar-backup")
    parser.add_argument("--tag", required=True, help="Tag to remove, e.g. 1.2.3")
    return parser.parse_args()


def get_jwt(user: str, token: str) -> str:
    """
    Authenticate with Docker Hub and return a JWT.

    Args:
        user: Docker Hub username.
        token: Docker Hub password or access token.

    Returns:
        JWT string.

    Raises:
        SystemExit: If authentication fails or the response contains no token.
    """
    payload = json.dumps({"username": user, "password": token}).encode()
    req = urllib.request.Request(
        DOCKERHUB_LOGIN_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        logger.error("Docker Hub login failed: HTTP %s", exc.code)
        raise SystemExit(1) from exc

    jwt = body.get("token")
    if not jwt:
        logger.error("Docker Hub login returned no token")
        raise SystemExit(1)
    return jwt


def remove_tag(repo: str, tag: str, jwt: str) -> None:
    """
    Delete a tag from Docker Hub.

    Args:
        repo: Repository name, e.g. per2jensen/scrubexif.
        tag: Tag name to remove.
        jwt: JWT obtained from get_jwt().

    Raises:
        SystemExit: If the deletion fails.
    """
    url = DOCKERHUB_TAG_URL_TEMPLATE.format(repo=repo, tag=tag)
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"JWT {jwt}"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            logger.info("✅ Removed tag %s from %s (HTTP %s)", tag, repo, resp.status)
    except urllib.error.HTTPError as exc:
        logger.error("❌ Failed to remove tag %s from %s: HTTP %s", tag, repo, exc.code)
        raise SystemExit(1) from exc


def main() -> None:
    """
    Entry point: read credentials from environment, then remove the tag.

    Raises:
        SystemExit: If credentials are missing or any API call fails.
    """
    args = parse_args()

    user = os.environ.get("DOCKERHUB_USER")
    token = os.environ.get("DOCKERHUB_TOKEN")
    if not user or not token:
        logger.error("DOCKERHUB_USER and DOCKERHUB_TOKEN must be set in the environment")
        raise SystemExit(1)

    logger.info(
        "⚠️  Rollback: removing unverified %s:%s from Docker Hub",
        args.repo,
        args.tag,
    )
    jwt = get_jwt(user, token)
    remove_tag(args.repo, args.tag, jwt)


if __name__ == "__main__":
    main()
