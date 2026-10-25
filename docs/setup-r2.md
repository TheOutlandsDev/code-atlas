# Code Atlas v0.1.0 — Linux preview setup

**Setup revision 2 — 23 October 2026.** This is the current release setup guide. It adds explicit shared-storage and agent/plugin state directories to the separate-instance commands. The v0.1.0 VSIX, runtime code and setup helper are unchanged.

A local language map and read-only source browser for VS Code. MIT licensed.

## Requirements and verified CLI version

- Linux with `/proc` available.
- VS Code, with the `code` command available in your terminal. The extension requires **VS Code 1.100+**.
- The complete separate-instance recipe below was verified on **VS Code 1.143.0**. Check `code --version` first. These state-directory CLI options have not been validated here on other builds; do not assume an older build supports them. If a build warns that an option is unknown or rejects it, stop and check that build's CLI support before continuing. Do not remove state-directory options and assume the same separation.
- Python 3.10 or newer at **`/usr/bin/python3`**. Check with `/usr/bin/python3 --version`.
- A project directory that you own and explicitly choose to index.

This preview uses Python's standard library and VS Code's extension host. No npm installation, account or hosted service is required. Node.js 18+ is needed only when developing and running the source test suite.

## Recommended: revision 2 setup ZIP

1. From the [v0.1.0 release](https://github.com/TheOutlandsDev/code-atlas/releases/tag/v0.1.0), download **`code-atlas-0.1.0-setup-r2.zip`** and **`SHA256SUMS-r2`** into the same folder. Earlier unsuffixed setup assets are superseded; use the revision 2 files together.
2. In that download folder, run `sha256sum --check --ignore-missing SHA256SUMS-r2`. Confirm that `code-atlas-0.1.0-setup-r2.zip` is reported **OK**. Stop if it fails.
3. Extract the ZIP with your file manager, or run:

   ```sh
   unzip code-atlas-0.1.0-setup-r2.zip
   cd code-atlas-0.1.0-setup-r2
   sha256sum --check SHA256SUMS
   ```

   All six bundled payload files must be reported **OK**. Read `tools/configure.py`, `examples/policy.example.json` and this guide before running setup. The ZIP's inner manifest is named `SHA256SUMS`; the release's outer revision 2 manifest is named `SHA256SUMS-r2`.
4. Choose a new private configuration home and an existing project directory:

   ```sh
   export CODE_ATLAS_HOME="$HOME/.code-atlas"
   /usr/bin/python3 -I -B tools/configure.py \
     --root "/absolute/path/to/your/projects"
   ```

   Replace the example project path. Repeat `--root` for additional directories. There are no default source roots. Configuration refuses broad system/home roots, symlink paths, a state directory inside a source root, and an existing configuration home. If the home already exists, inspect and reuse its configuration or choose a different new home; do not delete existing data to get past this check.
5. Install and launch with explicit, separate directories for VS Code's user data, extensions, shared storage and agent/plugin state:

   ```sh
   code --user-data-dir "$CODE_ATLAS_HOME/vscode-user" \
     --extensions-dir "$CODE_ATLAS_HOME/vscode-extensions" \
     --shared-data-dir "$CODE_ATLAS_HOME/vscode-shared" \
     --agent-plugins-dir "$CODE_ATLAS_HOME/agent-plugins" \
     --agents-user-data-dir "$CODE_ATLAS_HOME/agents-user" \
     --agents-extensions-dir "$CODE_ATLAS_HOME/agents-extensions" \
     --install-extension ./code-atlas-0.1.0.vsix

   code --user-data-dir "$CODE_ATLAS_HOME/vscode-user" \
     --extensions-dir "$CODE_ATLAS_HOME/vscode-extensions" \
     --shared-data-dir "$CODE_ATLAS_HOME/vscode-shared" \
     --agent-plugins-dir "$CODE_ATLAS_HOME/agent-plugins" \
     --agents-user-data-dir "$CODE_ATLAS_HOME/agents-user" \
     --agents-extensions-dir "$CODE_ATLAS_HOME/agents-extensions" \
     --sync off \
     --new-window "$CODE_ATLAS_HOME/Atlas.code-workspace"
   ```

   `--shared-data-dir` matters: VS Code 1.143 can otherwise use shared state outside the chosen user-data folder. Keep the same complete set of directories on install and launch. Run both commands from the same terminal after setting `CODE_ATLAS_HOME`. If an instance using these exact folders is already running with another environment or state-directory selection, close that instance before reopening it.
6. Inspect the workspace and extension before trusting them. Keep workspace trust enabled; do not add `--disable-workspace-trust`. If prompted, trust only the workspace and source folders you inspected, without adding a broader parent folder. Declining trust keeps Code Atlas inactive. An empty dashboard can already be trusted, so absence of a prompt alone does not mean trust is disabled.
7. In VS Code, choose **OUTLANDS: Open Code Map** from **Ctrl+Shift+P**, or open the **Code Atlas** Explorer view. Select a language, search for a project, and choose **Browse source files**. Use **Refresh map** for a new bounded scan. Source tabs are read-only. The map supports drag to pan, Control + wheel to zoom, arrow-key pan, plus/minus zoom and zero to reset.

The separate instance keeps registration, settings and the selected state stores in their own directories. It is not an operating-system sandbox. The source browser does not change permissions or constrain other tools you run.

## Standalone VSIX

The release also includes the unchanged `code-atlas-0.1.0.vsix` for users who already have a reviewed configuration. A VSIX alone does not choose source roots or create configuration. Use the revision 2 ZIP for the current separate-instance instructions and its bundled setup helper.

To use a normal VS Code instance instead of the recommended separate one, choose **Extensions: Install from VSIX…** from the Command Palette and select the downloaded VSIX. Launch it with the correct `CODE_ATLAS_HOME` environment and open that home's `Atlas.code-workspace`. This registers the extension in that instance; review the effect on your existing profile first.

## Scope and verification

- Scans and source tabs remain local. Only explicitly configured roots are scanned, within published size/time/depth limits.
- Python and JSON receive static syntax checks. Other supported languages are browsable; syntax success is separate from project tests.
- Reviewed workspace shortcuts only open paths you configure. Those workspaces own their tasks, testing integrations, dependency setup and debuggers.
- The portable release does not include a universal aggregate test runner. The aggregate action is unavailable.
- No server inventory, private project code/data, credentials, run receipts, logs, screenshots or host-specific deployment runners are bundled.
- Public source QA passed **70 synthetic/mocked checks**. Subsequent Linux testing of the unchanged VSIX on **VS Code 1.143.0** passed **22 native integration checks and 28 map-control/workspace-trust checks** using synthetic projects. This does not validate private projects, other operating systems or other VS Code builds.

The [tagged documentation](https://github.com/TheOutlandsDev/code-atlas/tree/v0.1.0/docs) remains a runtime/configuration reference; use this revision 2 guide for the corrected separate-instance commands. Runtime and setup-helper source commit: `553e87887e6514238b69c1cdebf6494369968a4a`. This release-only setup guide was revised separately after that source tag.
