# Reviewed workspace navigation

Code Atlas distinguishes read-only source browsing from development and test execution. Its optional reviewed-workspace shortcut opens a local workspace you have already inspected.

Start without reviewed entries. Configure and validate the map first. Then create a separate `.code-workspace` file with only the folders and tools you intend to use. For an isolated test workflow, make its editable copies, dependencies, tasks, and runner isolation explicit in that workspace's own documentation.

Before enabling a shortcut, inspect:

- Workspace folders and whether each points to original source or a disposable copy.
- Tasks, launch configurations, required extensions, and any automatic execution settings.
- Dependency sources and interpreter/tool versions.
- Filesystem and network access of the tools you will run.
- Test scope, expected results, coverage gates, timeouts, and cleanup behavior.

Use canonical absolute paths for the source root and reviewed workspace. The source root must already be authorized by the Code Atlas policy. The exact configuration format is in [configuration](configuration.md).

Select the shortcut in the map or project tree to open the workspace. In that window, invoke its existing VS Code Testing integrations or **Terminal → Run Task** manually. Code Atlas does not install them or make them safe automatically.

## Aggregate test action

The public portable release has no configured aggregate runner. Its aggregate test button remains unavailable. There is no bundled list of projects, fixed expected test count, or claim of universal project-test support.

If you develop an aggregate integration, keep it a separately reviewed feature. Define an explicit command allowlist and result schema; prevent source-derived command execution; enforce bounded output, timeouts, cancellation and cleanup; bind results to a fresh run; and verify original-source preservation if that is part of the workflow's promise. These are design requirements for that future integration, not features claimed by this release.
