#!/usr/bin/env python3
"""Exercise setup and refresh using temporary synthetic projects, without VS Code."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('code_atlas_release_check', ROOT / 'tools/check_release.py')
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)
RUNTIME = ('tools/configure.py', 'examples/policy.example.json', 'tools/scan.py')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def runtime_files(assets=None):
    lock = release.check_repository(ROOT)
    if assets is None:
        return {name: release.read_file(ROOT / name) for name in RUNTIME}
    # Verify all pinned bytes before selecting the three files we will execute/use.
    release.check_assets(assets, lock)
    with zipfile.ZipFile(io.BytesIO(release.read_file(assets / 'code-atlas-0.1.0-setup-r2.zip'))) as bundle:
        files = {name: bundle.read(lock['prefix'] + name) for name in RUNTIME[:2]}
    with zipfile.ZipFile(io.BytesIO(release.read_file(assets / 'code-atlas-0.1.0.vsix'))) as vsix:
        entries = [item for item in vsix.infolist() if item.filename == 'extension/tools/scan.py']
        require(len(entries) == 1, 'Released VSIX must contain one scanner')
        item = entries[0]
        require(stat.S_ISREG(item.external_attr >> 16) and not item.flag_bits & 1 and
                item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and
                0 < item.file_size <= release.MAX_BYTES, 'Released scanner entry is unsafe')
        files['tools/scan.py'] = vsix.read(item)
    return files


def write_new(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as target:
        target.write(data)


def snapshot(root):
    """Read only our tiny fixture; never follow its deliberate escape symlink."""
    result = {}
    for directory, names, files in os.walk(root, followlinks=False):
        for name in sorted(names + files):
            path = Path(directory) / name
            info = path.lstat()
            metadata = (stat.S_IMODE(info.st_mode), info.st_ino)
            if path.is_symlink():
                value = ('link', metadata, os.readlink(path))
            elif path.is_dir():
                value = ('directory', metadata)
            else:
                require(stat.S_ISREG(info.st_mode), 'Unexpected fixture file type')
                value = ('file', metadata, info.st_mtime_ns, path.read_bytes())
            result[str(path.relative_to(root))] = value
    return result


def invoke(script, arguments, lab, home, expected=0):
    # Do not inherit the owner's tokens, configuration roots or Python environment.
    environment = {'HOME': str(lab / 'empty home'), 'PATH': os.defpath,
                   'CODE_ATLAS_HOME': str(home), 'LANG': 'C.UTF-8'}
    process = subprocess.run([sys.executable, '-I', '-B', str(script), *arguments],
                             cwd=lab, env=environment, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             timeout=30, check=False)
    require(process.returncode == expected,
            script.name + ' returned ' + str(process.returncode) +
            ', expected ' + str(expected) + ': ' + process.stderr.decode(errors='replace')[:500])


def signature(catalog):
    return {row['rootPath']: (row['languages'], row['fileCount'], row['sourceFingerprint'])
            for row in catalog['projects']}


def smoke(files):
    require(sys.platform.startswith('linux') and Path('/proc/self/fd').is_dir(),
            'This setup check requires Linux with /proc')
    require(set(files) == set(RUNTIME), 'Unexpected smoke runtime file set')
    checks = []
    with tempfile.TemporaryDirectory(prefix='code-atlas-setup-smoke-') as temporary:
        lab = Path(temporary).resolve()
        helper = lab / 'release helper'
        for name, data in files.items():
            write_new(helper / name, data)
        sources = lab / 'sample projects'
        fixture = {
            'python-demo/pyproject.toml': b'[project]\nname="synthetic-python"\nversion="0.0.0"\n',
            'python-demo/main.py': b'def answer():\n    return 42\n',
            'python-demo/guard.py': b'from pathlib import Path\nPath.home().joinpath("PROJECT_WAS_EXECUTED").write_text("unexpected")\n',
            'rust-demo/Cargo.toml': b'[package]\nname="synthetic-rust"\nversion="0.0.0"\n',
            'rust-demo/src/lib.rs': b'pub fn answer() -> u32 { 42 }\n',
            'rust-demo/src/util.rs': b'pub const SAMPLE: u32 = 1;\n',
            'typescript-demo/package.json': b'{"name":"synthetic-typescript","private":true}\n',
            'typescript-demo/src/index.ts': b'export const answer: number = 42;\n',
            'typescript-demo/src/extra.ts': b'export const sample: string = "fixture";\n',
            'python-demo/secrets/excluded.py': b'this is deliberately invalid python (\n',
            'python-demo/data/excluded.py': b'this is deliberately invalid python (\n',
            'typescript-demo/node_modules/excluded.js': b'// synthetic excluded dependency\n',
        }
        for name, data in fixture.items():
            write_new(sources / name, data)
        outside = lab / 'unselected sample'
        write_new(outside / 'outside.py', b'def broken(\n')
        (sources / 'python-demo/escape').symlink_to(outside, target_is_directory=True)
        (lab / 'empty home').mkdir(mode=0o700)
        home = lab / 'atlas state'
        before = snapshot(sources)
        outside_before = snapshot(outside)
        invoke(helper / 'tools/configure.py', ['--root', str(sources)], lab, home)
        policy = json.loads((home / 'policy.json').read_text())
        workspace = json.loads((home / 'Atlas.code-workspace').read_text())
        require(policy['bases'] == policy['seedRoots'] == [str(sources)] and
                policy['excludedPathPrefixes'] == [str(home)] and not policy['reviewedTests'],
                'Setup broadened source scope or configured project execution')
        checks.append('explicit synthetic roots and no reviewed test commands')
        require(workspace['folders'] == [] and
                workspace['settings']['security.workspace.trust.enabled'] is True and
                workspace['settings']['files.autoSave'] == 'off', 'Unexpected workspace or trust settings')
        checks.append('empty dashboard workspace with trust enabled and autosave off')
        for path, mode in [(home, 0o700), (home / 'state', 0o700),
                           (home / 'policy.json', 0o600), (home / 'Atlas.code-workspace', 0o600)]:
            require(stat.S_IMODE(path.stat().st_mode) == mode, 'Setup state is not owner-private')
        checks.append('owner-private configuration directories and files')
        configured = snapshot(home)
        invoke(helper / 'tools/configure.py', ['--root', str(sources)], lab, home, 2)
        require(snapshot(home) == configured, 'Repeated setup changed an existing configuration')
        checks.append('existing setup refused without overwrite')
        (lab / 'source link').symlink_to(sources, target_is_directory=True)
        refused = [('/', lab / 'broad refusal'), (str(lab / 'missing root'), lab / 'missing refusal'),
                   (str(lab / 'source link'), lab / 'link refusal'),
                   (str(sources), sources / 'overlap refusal')]
        for root, target in refused:
            invoke(helper / 'tools/configure.py', ['--root', root, '--home', str(target)], lab, home, 2)
            require(not target.exists(), 'Refused setup created state')
        checks.append('broad, missing, symlink and source-overlapping roots refused')

        def scan_fixture():
            source_snapshot = snapshot(sources)
            invoke(helper / 'tools/scan.py', [], lab, home)
            require(snapshot(sources) == source_snapshot and snapshot(outside) == outside_before,
                    'Scanner changed a synthetic source file')
            catalog = json.loads((home / 'state/catalog.json').read_text())
            require(catalog['coverage']['complete'] and not catalog['coverage']['limited'] and
                    catalog['validation']['errors'] == catalog['validation']['pending'] == 0,
                    'Synthetic scan is incomplete or has unexpected syntax errors')
            require(all(Path(row['rootPath']).is_relative_to(sources) and
                        row['status'] == 'READ_ONLY_SOURCE' and row['scanComplete'] and
                        row['testStatus'] == 'NOT_CONFIGURED' for row in catalog['projects']),
                    'Catalog escaped synthetic scope or enabled execution')
            require(not (lab / 'empty home/PROJECT_WAS_EXECUTED').exists(),
                    'Project code was executed')
            return catalog

        initial = scan_fixture()
        projects = {Path(row['rootPath']).name: row for row in initial['projects'] if row['fileCount']}
        require(set(projects) == {'python-demo', 'rust-demo', 'typescript-demo'},
                'Unexpected discovered projects')
        for name, language in [('python-demo', 'Python'), ('rust-demo', 'Rust'),
                               ('typescript-demo', 'TypeScript')]:
            require(projects[name]['primaryLanguage'] == language and projects[name]['fileCount'] == 3,
                    'Synthetic language grouping or file count differs')
        checks.append('Python, Rust and TypeScript projects grouped correctly')
        require(initial['validation']['checkedThisScan'] == 3 and
                initial['coverage']['codeFiles'] == 9 and initial['coverage']['excludedDirectories'] >= 4,
                'Secret/data/dependency or escape-link exclusions differ')
        checks.append('excluded synthetic secret, data, dependency and symlink entries absent')
        checks.append('Python and JSON statically parsed without executing projects')
        require(signature(scan_fixture()) == signature(initial), 'Unchanged source fingerprints drifted')
        checks.append('repeat scan preserves unchanged fingerprints')
        added = sources / 'new-go'
        write_new(added / 'go.mod', b'module example.invalid/synthetic\n')
        write_new(added / 'main.go', b'package main\nfunc main() {}\n')
        refreshed = scan_fixture()
        added_rows = [row for row in refreshed['projects'] if row['rootPath'] == str(added)]
        require(len(added_rows) == 1 and added_rows[0]['primaryLanguage'] == 'Go' and
                added_rows[0]['fileCount'] == 1, 'Refresh missed newly created project')
        require({key: value for key, value in signature(refreshed).items() if key != str(added)} ==
                signature(initial), 'Adding a fixture changed existing source fingerprints')
        checks.append('refresh discovers a newly created Go project')
        # These are the two known synthetic files created immediately above.
        (added / 'main.go').unlink()
        (added / 'go.mod').unlink()
        added.rmdir()
        require(signature(scan_fixture()) == signature(initial), 'Refresh retained a deleted synthetic project')
        checks.append('refresh removes the deleted synthetic project')
        require(snapshot(sources) == before and snapshot(outside) == outside_before,
                'Original synthetic source bytes or metadata changed')
        require((home / 'policy.json').read_bytes() == configured['policy.json'][3] and
                (home / 'Atlas.code-workspace').read_bytes() == configured['Atlas.code-workspace'][3],
                'Scanning changed setup policy or workspace')
        checks.append('original sample files, policy and workspace preserved')
        for name in ['state/catalog.json', 'state/scan.lock']:
            require(stat.S_IMODE((home / name).stat().st_mode) == 0o600, 'Scan output is not owner-private')
        require(not list((home / 'state').glob('*.tmp')), 'Temporary catalog remained after refresh')
        checks.append('owner-private atomic scan outputs without leftover temporary catalogs')
    require(not lab.exists(), 'Temporary setup was not removed')
    checks.append('temporary synthetic setup cleaned up')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--assets-dir', type=Path, help='Verify four pinned public assets and use their helper/scanner')
    group.add_argument('--download', action='store_true', help='Download and check pinned public assets before the synthetic smoke')
    args = parser.parse_args()
    try:
        if args.download:
            with tempfile.TemporaryDirectory(prefix='code-atlas-smoke-download-') as temporary:
                directory = Path(temporary)
                release.download_assets(directory, release.check_repository(ROOT))
                checks = smoke(runtime_files(directory))
        else:
            checks = smoke(runtime_files(args.assets_dir))
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        parser.exit(1, 'Setup smoke failed: ' + str(error) + '\n')
    for check in checks:
        print('PASS: ' + check)
    mode = 'pinned release' if args.download or args.assets_dir else 'public checkout'
    print(str(len(checks)) + ' setup/scan checks passed (' + mode + '). No VS Code window or project tests started.')


if __name__ == '__main__':
    main()
