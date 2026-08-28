<!--
SPDX-FileCopyrightText: 2025-2026 Per Jensen

SPDX-License-Identifier: GPL-3.0-or-later

This file is part of dar-backup-image:
https://github.com/per2jensen/dar-backup-image

License terms and warranty disclaimer:
https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
-->

# Release SBOM evidence

Manual releases and weekly refreshes generate CycloneDX JSON SBOMs with Syft.
The workflow commits the generated file to this directory as part of the
allowlisted housekeeping transaction and records its filename in
[`doc/build-history.json`](../build-history.json).

Manual-release SBOMs are also attached to the corresponding GitHub Release and
attested to the immutable Docker digest with Cosign. Refresh SBOMs are committed
and attested but do not have a GitHub Release asset.

Generated evidence is ignored during ordinary development and force-staged only
by the release or refresh housekeeping script. Do not edit generated SBOMs.
