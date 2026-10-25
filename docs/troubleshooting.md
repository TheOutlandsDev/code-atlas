# Troubleshooting

## The map is empty

Check that you configured at least one existing canonical source root and launched VS Code with the same `CODE_ATLAS_HOME` used during setup. Configuration intentionally starts without broad default roots. Use **Refresh map** and inspect the coverage information.

A folder can be excluded, unreadable, outside the allowed roots, or beyond a scan budget. The map is not guaranteed to contain every file on a system.

## A separate instance reuses state or the wrong environment

Use the complete [revision 2 setup commands](setup-r2.md), including `--shared-data-dir` on both installation and launch. VS Code 1.143.0 can otherwise use shared state outside its user-data directory. Keep all six state-directory paths and `CODE_ATLAS_HOME` consistent and close an existing instance using those exact paths before changing them. The recipe is verified on 1.143.0; stop on unknown-option warnings rather than dropping isolation options.

## No workspace trust prompt appears

Keep workspace trust enabled. The generated dashboard has no editable source folders and can already be trusted. To test the ordinary prompt, use an explicitly chosen synthetic folder in a separate test workspace. Declining trust leaves Code Atlas inactive. Revoking trust can leave a cached map visible, but it does not permit further scanning or source navigation.

## Configuration already exists

The configuration tool refuses to overwrite an existing setup. Inspect and back up your local policy before editing it. For a separate experiment, choose another private `CODE_ATLAS_HOME` rather than deleting state or replacing an active configuration blindly.

## A source file will not open

Code Atlas rejects excluded paths, unsupported files, symlinks, invalid virtual URIs, unreadable files, and files above its read limit. Refresh the map after moving or deleting files. Open the project directly if you need normal editor access and are authorized to use it.

## I cannot edit a file

Tabs opened through Code Atlas's virtual filesystem are read-only. Use a separately reviewed development workspace or open the original project directly for editing. That choice is outside the read-only navigation boundary.

## The catalog is marked limited

A configured root may be only partially visited because a directory, file, project, byte, or time budget was reached. Missing permissions can also limit coverage. Reduce the configured roots or review limits deliberately. Increasing limits does not grant permissions or establish complete system coverage.

## A reviewed shortcut is unavailable

Check the exact source-root and workspace paths in the local policy. The workspace must exist at its canonical path. Unconfigured projects remain browse-only. No test workflow is inferred from a filename such as `Makefile` or a package manifest.

## Run all reviewed tests is unavailable

The portable release does not ship an aggregate runner. Open a configured reviewed workspace and use its manually configured tools. See [reviewed workspaces](reviewed-workspaces.md).

## Reporting a bug

Use a small synthetic reproduction and include tool versions. Replace personal paths and project names with placeholders. Do not attach your real policy, catalog, workspace, environment files, or private test receipts without reviewing and redacting them first.
