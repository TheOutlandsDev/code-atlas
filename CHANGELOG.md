# Changelog

## 0.1.2

- Show bounded physical source line counts in the map and project details. Mark totals as partial when the read budget leaves files pending.
- Include the line-count guide in the VSIX. Keep the pinned revision 2 first-time setup bundle and earlier release assets unchanged.
- Check each pull request's candidate VSIX in an isolated Linux VS Code profile with generated fixtures, including complete and partial counts, restart persistence and Restricted Mode. Local native runs keep screenshots off by default.

## 0.1.1

- Queue one follow-up refresh when a request arrives during an active scan, so the map sees changes made while that scan was running.

- Exercise setup and scanner refresh end to end with temporary multilingual fixtures, source-preservation checks and configuration refusal cases; repeat against pinned public release artifacts in CI without opening VS Code.
- Align the README/configuration/troubleshooting docs with release setup revision 2 and its explicit shared-data/agent state directories.
- Add a pinned public release lock, ZIP/checksum/setup-command validation, synthetic regression tests and read-only GitHub Actions checks.
- Include the current setup and release-check documentation in the new VSIX. Previously published v0.1.0 release assets remain unchanged.

## 0.1.0

Initial portable Linux release of Code Atlas.

- Interactive local language map and searchable source-root list.
- Read-only source navigation through the VS Code filesystem provider.
- Explicit local configuration with bounded discovery and visible coverage limits.
- Optional navigation to exact, reviewed local workspaces.
- Dependency-free runtime and synthetic public QA fixtures.

The portable release excludes deployment-specific source inventories, profiles, credentials, test adapters, isolated runners, run receipts, and aggregate test execution. It does not change an existing private installation.
