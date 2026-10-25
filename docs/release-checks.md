# Automated release checks

The revision 2 setup guide and public release artifacts are pinned in `release/setup-r2.json`. This lock records public filenames, sizes, SHA-256 digests, exact ZIP payloads and source provenance. It contains no real source roots or local inventory.

## Offline checks

```sh
python3 -I -B tools/check.py
```

This runs the existing synthetic suites, release-check regression tests and offline documentation validation. The release checker verifies:

- The committed [current guide](setup-r2.md) matches the published guide's pinned bytes.
- Install and launch commands include the complete revision 2 state-directory options, preserve workspace trust and disable settings sync on the separate launch.
- The README points to the current guide, ZIP and checksum manifest; configuration/troubleshooting references agree.
- The helper, empty-root example policy and MIT license still match the locked release inputs.

It does not start VS Code, discover project roots or run a downstream project's tests.

## Check downloaded artifacts

Put the four public files in one directory: `code-atlas-0.1.0.vsix`, `code-atlas-0.1.0-setup-r2.zip`, `SETUP-r2.md` and `SHA256SUMS-r2`. Then run:

```sh
python3 -I -B tools/check_release.py --assets-dir /absolute/path/to/public-release-downloads
```

Only those four fixed names are read; the directory is not walked. The check validates pinned sizes/hashes, the outer checksum manifest, exactly seven unique regular ZIP entries, all six inner payload checksums, public provenance and equality of the bundled/standalone installer and guide. ZIP contents are read in memory, with size limits, and are never extracted to an arbitrary destination. Extra, duplicate, symlink, encrypted or unsupported ZIP entries fail.

To download those same pinned public assets into a temporary directory and check them:

```sh
python3 -I -B tools/check_release.py --download
```

This opt-in mode contacts only the fixed public GitHub release URLs and GitHub HTTPS redirect hosts, sends no authentication token or local files, and removes its temporary copies afterward. A missing download, network failure, changed digest or content discrepancy fails the command rather than reporting a skipped success.

## GitHub Actions

The **Release checks** workflow runs on pushes, pull requests and manual dispatch, on a GitHub-hosted Ubuntu runner. It runs the offline suites, then verifies the pinned public downloads. The job has `contents: read`, no user-provided secrets or publishing step, a timeout, and a commit-pinned official checkout action with credential persistence disabled. It does not connect to a developer's IDE or infrastructure.

The workflow checks release artifacts; it does not publish them, change tags or provide native UI acceptance. Keep the Linux/VS Code version scope of manual acceptance results clear.

## Intentional release changes

Do not update lock hashes just to silence a failure. Review the exact new artifact allowlist, notices, source identity, guide commands and checksum manifests first. Publish an explicitly reviewed revision, then update the lock and guide together. Existing released VSIX bytes stay pinned even when a development checkout's documentation changes. Build output is not uploaded by these checks.
