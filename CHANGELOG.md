# Changelog

## Unreleased

- Align the README/configuration/troubleshooting docs with release setup revision 2 and its explicit shared-data/agent state directories.
- Add a pinned public release lock, ZIP/checksum/setup-command validation, synthetic regression tests and read-only GitHub Actions checks.
- Include the current setup and release-check documentation in future development VSIX packages. Published v0.1.0 release assets and runtime code remain unchanged.

## 0.1.0

Initial portable Linux release of Code Atlas.

- Interactive local language map and searchable source-root list.
- Read-only source navigation through the VS Code filesystem provider.
- Explicit local configuration with bounded discovery and visible coverage limits.
- Optional navigation to exact, reviewed local workspaces.
- Dependency-free runtime and synthetic public QA fixtures.

The portable release excludes deployment-specific source inventories, profiles, credentials, test adapters, isolated runners, run receipts, and aggregate test execution. It does not change an existing private installation.
