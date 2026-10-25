# Contributing

Start with a focused issue describing the behavior you want to improve, an example using synthetic data, and the expected result. For a bug, include your Linux distribution, VS Code version, Python version, and a minimal configuration with personal paths replaced by placeholders.

Do not attach a real source catalog, credentials, environment files, private documents, or an unredacted workspace. Local configuration and scan state can reveal project names and filesystem structure even when source contents are absent.

## Local development

Read [the architecture](docs/architecture.md) and [security boundaries](SECURITY.md) before changing filesystem handling, workspace navigation, or webview messages.

Run the public checks from the repository root:

```sh
python3 -I -B tools/check.py
python3 -I -B tools/package.py
```

`tools/check.py` includes offline release/documentation checks, their synthetic regression tests, and an actual setup-helper/scanner workflow using temporary sample projects. The workflow checks language grouping, source preservation, exclusions, create/delete refresh, owner-private state and refusal to overwrite configuration. Before changing a release contract, read [automated release checks](docs/release-checks.md). To verify downloaded public assets explicitly, run:

```sh
python3 -I -B tools/check_release.py --assets-dir /absolute/path/to/public-release-downloads
```

Only four fixed artifact names are read from that directory. Public downloads are opt-in locally (`--download`) and run automatically in the read-only GitHub Actions job.

To repeat the setup/scan workflow with the verified helper and scanner from those released artifacts, run:

```sh
python3 -I -B tools/check_setup.py --assets-dir /absolute/path/to/public-release-downloads
```

With `--download` instead of `--assets-dir`, the checker downloads only the four pinned public assets and removes its temporary downloads afterward. Without either option, it uses the public checkout offline. All modes use newly generated synthetic roots and a temporary configuration home; no VS Code window or downstream tests start.

Use the complete [revision 2 setup guide](docs/setup-r2.md) and a dedicated directory of synthetic projects for manual VS Code checks. Inspect the generated workspace before trusting it. Confirm that the map opens, language filtering works, source tabs reject edits, excluded files are unavailable, and a configured reviewed shortcut opens only its exact workspace.

## Change expectations

- Keep discovery bounded and roots explicit.
- Keep virtual source navigation read-only.
- Preserve canonical-path, symlink, descriptor, size, and schema checks.
- Treat source files, filesystem names, webview messages, and external tools as untrusted input.
- Keep commands and test execution manual and explicit; source discovery must not run project code.
- Add focused regression checks for meaningful policy or behavior changes.
- Document changes to configuration, limits, data written to disk, and supported platforms.

Do not add telemetry, hosted integrations, dependency installation, automatic command execution, or broader filesystem access as an incidental part of another change. Explain any such proposed feature separately so its behavior can be reviewed.

The project uses the [MIT License](LICENSE). Keep contributions compatible with that license and preserve attribution for any material you are authorized to contribute. This document does not transfer ownership or require a separate contributor agreement.
