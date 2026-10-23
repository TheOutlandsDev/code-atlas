# Security boundaries

Code Atlas is a local project navigator. Its source view is read-only, and discovery is limited to explicit roots and configured budgets. These controls reduce accidental editing and unwanted indexing; they are not an operating-system sandbox.

## What the extension can access

The VS Code extension host and scanner run with the current user's permissions. Code Atlas authorizes source navigation against its local policy, rejects symlink-based paths, limits supported files and reads, and validates catalog and webview inputs. Other extensions, terminals, tasks, and processes keep their own access.

Keep source roots narrow. Do not configure your filesystem root, an entire home directory, credential directories, database storage, model caches, or personal-document collections. Exclusions are a navigation policy, not a guarantee that every sensitive file has a recognizable name.

## Local metadata is sensitive

Configuration, the generated workspace, and scan state can contain absolute paths, project labels, language information, file metadata, and fingerprints. Keep `CODE_ATLAS_HOME` outside public repositories and restrict access to it. Review any diagnostics before sharing them. The supplied `.gitignore` is a convenience; it cannot detect every private file you might add.

The portable runtime does not include a network client or telemetry service. VS Code, installed extensions, and commands you run separately can still communicate over the network.

## Reviewed workspaces and tests

A reviewed shortcut opens an explicitly configured local workspace. It does not make that workspace or its tasks safe. Inspect its folders, tasks, launch configuration, extensions, and trust state before use.

The portable release does not provide project isolation, install dependencies, validate arbitrary external test results, or run a universal aggregate suite. If you add a separate test runner, its author must define and verify its filesystem, process, network, credential, timeout, cancellation, and result-reporting boundaries. Code Atlas browsing alone provides none of those guarantees.

Do not treat syntax metadata as a passing build or test result. Do not treat a limited catalog as a complete system inventory.

## Reporting an issue

For a suspected vulnerability, use the repository's private vulnerability reporting feature if it is enabled. If no private channel is available, open an issue requesting a private contact method and omit exploit details, credentials, personal paths, and source inventories. Do not publish sensitive evidence in a public issue.

Describe the affected version, the boundary involved, the expected and observed behavior, and a minimal synthetic reproduction. There is no promised response time or formal support window for this initial release.
