# Grype scan evidence

Manual releases and weekly refreshes scan their generated SBOM with Grype and
write the SARIF result to this directory. The publication gate rejects any
detected High or Critical vulnerability. Lower-severity and informational
findings may remain and are summarized in
[`doc/build-history.json`](../build-history.json).

Manual-release SARIF files are also attached to the corresponding GitHub
Release. Refresh evidence is committed without creating a GitHub Release.
Generated evidence is ignored during ordinary development and force-staged only
by the release or refresh housekeeping script. Do not edit generated SARIF.
