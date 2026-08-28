<!--
SPDX-FileCopyrightText: 2025-2026 Per Jensen

SPDX-License-Identifier: GPL-3.0-or-later

This file is part of dar-backup-image:
https://github.com/per2jensen/dar-backup-image

License terms and warranty disclaimer:
https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
-->

# Documentation audit follow-ups

This file records work deliberately left outside the 0.9.1 documentation
remediation performed on 2026-08-25. The user-facing documentation describes
these limitations now, but the underlying capabilities still need
implementation and regression coverage.

## Image preservation bundle

`scripts/save-dar-backup-image.sh` currently preserves image availability only.
A future implementation should:

- validate build-history JSON and select exactly one well-formed newest record
- pull by immutable recorded digest and prove the requested tag resolves to it
- verify the expected Cosign workflow identity and CycloneDX attestation
- preserve the matching history record, SBOM, verification bundle, and other
  recovery evidence beside the image
- generate and subsequently verify a SHA-256 checksum for the compressed image
- validate an existing archive rather than trusting its filename
- record image architecture and add isolated positive and negative tests

## Slice-size and memory evidence

Schema-v10 large-scale results record the resolved slice size, absence of an
explicit PAR2 memory limit, host CPU/memory context, recognized DAR performance
options, coarse phase timing/RSS aggregates, workload shape, and artifact
layout. Docker invocations intentionally have no configured CPU or memory
limit, which is represented explicitly rather than inferred.

Run a controlled same-corpus matrix—holding image,
compression, PAR2 ratio, CPU/thread settings, and memory limits constant—across
representative slice sizes. Publish measured PAR2 create/verify/repair duration
and peak-memory results without presenting them as a universal formula.

The bundled PAR2 0.8.1 invocation currently has no explicit `-m` limit. Evaluate
an upstream `dar-backup` configuration for PAR2 memory, including behavior when
detected physical memory exceeds the container cgroup limit.

## Post-publication refresh recovery

There is no automated recovery path when Docker publication succeeds but the
atomic refresh housekeeping push fails. A full rerun intentionally fails because
the remote refresh tag is already occupied. Design a verification-first recovery
operation that reconciles the exact signed digest, SBOM, SARIF, application SHA,
orchestration SHA, build history, branch commit, and annotated refresh tag
without rebuilding or overwriting the image.

## Backup-definition mount hardening

Source data is now mounted read-only by `scripts/run-backup.sh`, but `/backup.d`
remains writable because the current `dar-backup` preflight rejects a read-only
definition directory. Determine whether runtime state genuinely belongs there.
If it does not, relax the upstream writability check and add an integration test
that completes a real backup with `/backup.d:ro`. If state is required, move it
to a separately documented writable mount before making definitions read-only.

## Documentation validation

The current regression test validates repository-relative Markdown targets and
generated README content. It does not validate Markdown anchors, HTML-local
targets, shell examples, or external URL health. Add deterministic checks for
local anchors and generated HTML. Keep external-link checks informational or
retry-aware so transient network failures cannot block a release incorrectly.
