# Configuration

Code Atlas reads its private local setup from `CODE_ATLAS_HOME`, defaulting to `~/.code-atlas`. The environment variable must be an absolute, normalized path with no symlink components. Linux `/proc` support is required for the descriptor checks used by this release.

No source roots are enabled by the repository's example policy. Create a setup with explicit directories:

```sh
python3 -I -B tools/configure.py \
  --root /absolute/path/to/projects \
  --root /absolute/path/to/another/project
```

Each root must already exist and be canonical. The setup tool rejects broad system locations and the current user's home directory. Choose project folders or narrow project parents. It also rejects placing Atlas state inside an indexed source root.

The tool creates a private directory with mode `0700`, a `state` directory, and two files with mode `0600`:

| File | Purpose |
| --- | --- |
| `policy.json` | Explicit roots, exclusion rules, language mappings, budgets, and optional reviewed workspace paths. |
| `Atlas.code-workspace` | An empty-folder dashboard workspace; it does not add source roots as editable folders. |
| `state/` | Generated local catalog and discovery state. Treat its contents as private metadata. |

The tool refuses to overwrite an existing setup, including an existing empty target directory. Its parent directory must exist. If creation fails partway through, inspect the partial setup before removing or replacing anything.

## Use another private directory

Set the variable for setup and for the VS Code process:

```sh
export CODE_ATLAS_HOME="/absolute/path/to/private-atlas"
python3 -I -B tools/configure.py --root /absolute/path/to/projects
code --new-window "$CODE_ATLAS_HOME/Atlas.code-workspace"
```

Use a fresh VS Code process when changing this environment variable. An already running VS Code process can keep its original environment. Do not point multiple concurrent setups at the same state directory.

The configuration directory is independent of the repository checkout. Keep it out of source control, and review its contents before sharing diagnostics.

## Policy fields

The complete starting policy is [examples/policy.example.json](../examples/policy.example.json). Inspect and back up your private policy before editing it.

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Configuration schema; currently `1`. |
| `bases` | Authorized canonical parent directories below which roots may be discovered. |
| `seedRoots` | Explicit source roots included in discovery. Setup initially uses the supplied `--root` values for both roots and bases. |
| `seedLabels` | Optional labels keyed by exact source-root path. |
| `reviewedTests` | Optional exact source-root/workspace pairs; navigation only. |
| `excludedDirectoryNames` | Case-insensitive component names omitted from navigation and discovery. |
| `excludedDirectoryPatterns` | Case-insensitive regular-expression exclusions applied to path components. |
| `excludedPathPrefixes` | Absolute paths excluded with their descendants. |
| `codeExtensions` | Recognized suffixes and their display languages. |
| `manifestNames` | Recognized exact filenames and their display languages. |
| `projectMarkers` | Names used to identify potential project roots. Discovery does not run those files. |

Hidden path components, symlinks, unsupported source files, and inaccessible files are excluded by the implementation. The default policy also excludes common dependency, build, data, secret, and document locations. These rules require review for your environment; they are not a general secret detector.

After a policy change, choose **OUTLANDS: Refresh Code Atlas** or **Refresh map**. If a policy or new catalog is invalid, the extension rejects it instead of presenting it as a successful update. Inspect the **Code Atlas** Output channel for status labels.

## Starting budgets

| Field | Default | Purpose |
| --- | ---: | --- |
| `maxDiscoveryDepth` | `8` | Discovery nesting depth. |
| `maxDirectories` | `10000` | Directory traversal budget. |
| `maxScanFiles` | `50000` | Regular-file scanning budget, including unsupported files encountered during traversal. |
| `maxProjects` | `500` | Source-root count budget. |
| `maxFileBytes` | `524288` | Maximum source file size exposed by the starting policy. |
| `maxDirectoryEntries` | `5000` | Per-directory entry budget. |
| `maxSeconds` | `20` | Scanner time budget in seconds. |

The extension applies its own upper bounds to source reads and directory listings. Its scanner process also has a deadline. Treat the values above as deliberate starting limits, not a promise of performance or a guarantee that every configured file will be indexed. Narrow roots before considering larger budgets.

In the trusted dashboard workspace, the map opens automatically and requests a metadata scan. It refreshes about every 60 seconds while that workspace stays open. Open read-only source tabs are polled about once a second. These refreshes do not execute project builds, tests, or services.

The portable scanner parses Python with the Python runtime's AST parser and JSON with the standard JSON parser. Other recognized languages remain available for browsing without bundled syntax validation. Python syntax support follows the installed scanner interpreter; JSON parsing does not add JSON-with-comments support. Use the project's own tools for authoritative language, lint, type, build, and test checks.

## Optional reviewed workspace

Add an entry only after inspecting the target workspace:

```json
{
  "reviewedTests": [
    {
      "rootPath": "/absolute/path/to/projects/example",
      "workspace": "/absolute/path/to/reviewed/Example.code-workspace"
    }
  ]
}
```

This is a fragment to merge into your existing private policy, not a replacement policy. The root must be authorized and the workspace must be an existing canonical regular `.code-workspace` file. No command, shell text, task label, or interpreter is accepted in this entry.

The shortcut opens the exact file in a new VS Code window. It does not execute a test or validate the target's tasks. See [reviewed workspace navigation](reviewed-workspaces.md) for the boundaries to inspect.
