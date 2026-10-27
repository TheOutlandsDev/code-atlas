#!/usr/bin/env python3
"""Run the published VSIX in an isolated Linux VS Code 1.143.0 test host.

Only generated projects are scanned. The downloaded VSIX/runtime stays unchanged.
Native API checks, rendered captures and manual UI acceptance are distinct.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_release as release

FIXTURES = {
    'python-demo/pyproject.toml': '[project]\nname="atlas-acceptance-python"\nversion="0.0.0"\n',
    'python-demo/main.py': 'def answer():\n    return 42\n',
    'python-demo/config.json': '{"sample": true}\n',
    'rust-demo/Cargo.toml': '[package]\nname="atlas-acceptance-rust"\nversion="0.0.0"\n',
    'rust-demo/src/lib.rs': 'pub fn answer() -> u32 { 42 }\n',
    'typescript-demo/package.json': '{"name":"atlas-acceptance-typescript","private":true}\n',
    'typescript-demo/src/index.ts': 'export const answer: number = 42;\n',
}
STATE = [('user-data-dir', 'vscode-user'), ('extensions-dir', 'vscode-extensions'),
         ('shared-data-dir', 'vscode-shared'), ('agent-plugins-dir', 'agent-plugins'),
         ('agents-user-data-dir', 'agents-user'), ('agents-extensions-dir', 'agents-extensions')]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def new_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as target:
        json.dump(value, target, indent=2)
        target.write('\n')


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def hashes(root):
    return {p.relative_to(root).as_posix(): file_sha(p)
            for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}


class MicrosoftRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        parsed = urllib.parse.urlsplit(url)
        require(parsed.scheme == 'https' and not parsed.username and not parsed.password and
                parsed.hostname in {'update.code.visualstudio.com', 'vscode.download.prss.microsoft.com'},
                'IDE redirect left the reviewed Microsoft HTTPS hosts')
        return super().redirect_request(request, fp, code, message, headers, url)


def ide_archive(work, supplied, lock):
    archive = supplied.resolve() if supplied else work / 'vscode-linux-x64.tar.gz'
    if not supplied:
        opener = urllib.request.build_opener(MicrosoftRedirects())
        request = urllib.request.Request(lock['url'], headers={'User-Agent': 'Code-Atlas-native-check'})
        size = 0
        with opener.open(request, timeout=60) as response, archive.open('xb') as target:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                require(size <= lock['bytes'], 'IDE download exceeded its pinned size')
                target.write(chunk)
    require(archive.is_file() and not archive.is_symlink() and archive.stat().st_size == lock['bytes'] and
            file_sha(archive) == lock['sha256'], 'IDE size or SHA-256 mismatch')
    with tarfile.open(archive, 'r:gz') as bundle:
        package = json.load(bundle.extractfile('VSCode-linux-x64/resources/app/package.json'))
        require(package['version'] == lock['version'], 'IDE package version differs from its lock')
    return archive



def provision_fixture_trust(state, workspace):
    """Seed only this generated workspace in a stopped, disposable 1.143 profile.

    This is a pinned CI fixture, not a user-profile migration. The reviewed IDE
    stores content.trust.model.key in APPLICATION_SHARED/sharedStorage/state.vscdb.
    A fresh untrusted run must pass before this function is called.
    """
    database = state / 'vscode-shared/sharedStorage/state.vscdb'
    require(database.is_file() and not database.is_symlink(), 'Expected isolated trust store missing')
    require(workspace == state / 'Atlas.code-workspace' and workspace.is_file() and
            not workspace.is_symlink(), 'Trust target must be the generated workspace file')
    key = 'content.trust.model.key'
    value = {'uriTrustInfo': [{'uri': {'scheme': 'file', 'authority': '',
                                      'path': workspace.as_posix()}, 'trusted': True}]}
    with sqlite3.connect(database, timeout=10) as db:
        require(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ItemTable'").fetchone(),
                'Unexpected pinned IDE storage schema')
        prior = db.execute('SELECT value FROM ItemTable WHERE key=?', (key,)).fetchone()
        require(prior is None or json.loads(prior[0]).get('uriTrustInfo') == [],
                'Refusing to replace pre-existing trusted locations')
        db.execute('INSERT OR REPLACE INTO ItemTable(key,value) VALUES(?,?)', (key, json.dumps(value)))
        require(json.loads(db.execute('SELECT value FROM ItemTable WHERE key=?', (key,)).fetchone()[0]) == value,
                'Narrow fixture trust provisioning failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ide-archive', type=Path, help='Use the same hash-pinned official archive already downloaded')
    parser.add_argument('--work-dir', type=Path, help='New absolute external working directory; retained for diagnosis')
    parser.add_argument('--artifacts-dir', type=Path, help='New absolute directory for sanitized public test evidence')
    parser.add_argument('--verify-inputs', action='store_true', help='Check public artifacts only; do not install or start VS Code')
    args = parser.parse_args()
    require(args.verify_inputs or (sys.platform == 'linux' and Path('/proc/self/fd').is_dir()),
            'Native execution requires Linux with /proc')
    require(args.verify_inputs or (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')),
            'Native execution requires an existing graphical session or a CI virtual display')
    os.umask(0o077)
    work = args.work_dir
    if work:
        require(work.is_absolute() and not work.exists() and ROOT not in work.parents,
                'Choose a new absolute work directory outside the source checkout')
        work.mkdir(mode=0o700)
    else:
        work = Path(tempfile.mkdtemp(prefix='atlas-native-', dir=os.environ.get('RUNNER_TEMP')))
    work = work.resolve()
    artifacts = args.artifacts_dir or work / 'public-artifacts'
    require(artifacts.is_absolute() and not artifacts.exists(), 'Choose a new absolute artifact directory')
    artifacts.mkdir(mode=0o700)
    report = {'status': 'RUNNING', 'synthetic_only': True, 'native_executed': False,
              'manual_ui_acceptance': 'NOT_RUN', 'phases': []}
    def phase(name):
        report['phase'] = name
        print('Native acceptance:', name, flush=True)
    try:
        phase('Verify pinned published release inputs')
        lock = release.check_repository(ROOT)
        downloads = work / 'downloads'
        downloads.mkdir()
        release.download_assets(downloads, lock)
        release.check_assets(downloads, lock)
        ide_lock = json.loads((ROOT / 'tests/native/ide-lock.json').read_text())
        require(ide_lock['version'] == '1.143.0' and ide_lock['platform'] == 'linux-x64' and
                ide_lock['url'] == 'https://update.code.visualstudio.com/1.143.0/linux-x64/stable',
                'Unsupported IDE lock identity')
        archive = ide_archive(work, args.ide_archive, ide_lock)
        report.update(vscode=ide_lock['version'], ide_sha256=ide_lock['sha256'],
                      vsix_sha256=lock['assets']['code-atlas-0.1.0.vsix']['sha256'])
        report['phases'].append('PUBLISHED_INPUT_HASHES_VERIFIED')
        if args.verify_inputs:
            report['status'] = 'INPUTS_VERIFIED_NATIVE_NOT_RUN'
            print('Published inputs verified. Native execution was not run.', flush=True)
            return
        phase('Extract the reviewed official IDE into new private state')
        ide_root = work / 'ide'
        ide_root.mkdir()
        with tarfile.open(archive, 'r:gz') as bundle:
            members = bundle.getmembers()
            require(len(members) < 50000 and sum(m.size for m in members) < 4 * 1024**3 and
                    all(m.name == 'VSCode-linux-x64' or m.name.startswith('VSCode-linux-x64/') for m in members),
                    'Unexpected IDE archive structure or size')
            bundle.extractall(ide_root, filter='data')
        code = ide_root / 'VSCode-linux-x64/bin/code'
        require(code.is_file(), 'Official Linux CLI is missing')
        payload = work / 'setup'
        payload.mkdir()
        with zipfile.ZipFile(downloads / 'code-atlas-0.1.0-setup-r2.zip') as bundle:
            for name in ['tools/configure.py', 'examples/policy.example.json', 'code-atlas-0.1.0.vsix']:
                target = payload / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(lock['prefix'] + name))
        session = work / 'session'
        session.mkdir()
        fixtures, state = session / 'fixtures', session / 'state'
        for name, content in FIXTURES.items():
            target = fixtures / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8', newline='\n')
        baseline = hashes(fixtures)
        private_home = work / 'home'
        private_home.mkdir()
        keep = ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR']
        env = {name: os.environ[name] for name in keep if name in os.environ}
        env.update(PATH=os.defpath + ':/usr/local/bin', HOME=str(private_home), USER='atlas-fixture',
                   LOGNAME='atlas-fixture', LANG='C.UTF-8', CODE_ATLAS_HOME=str(state),
                   PYTHONDONTWRITEBYTECODE='1')
        flags = [piece for option, child in STATE for piece in ('--' + option, str(state / child))]
        logs = work / 'logs'
        logs.mkdir()
        def checked(name, command, timeout=120):
            result = subprocess.run(command, cwd=work, env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=timeout, check=False)
            new_json(logs / (name + '.json'), {'arguments': command, 'returncode': result.returncode,
                     'stdout': result.stdout, 'stderr': result.stderr})
            if result.returncode:
                excerpt = (result.stderr + '\n' + result.stdout)[-6000:]
                excerpt = excerpt.replace(str(work), '<FIXTURE>').replace(str(ROOT), '<SOURCE>')
                excerpt = re.sub(r'https?://\S+', '<URL>', excerpt)
                (artifacts / (name + '-diagnostic.txt')).write_text(excerpt, encoding='utf-8')
            require(result.returncode == 0, 'Native command failed: ' + name)
            require(not any(word in result.stderr.lower() for word in
                    ['unknown option', 'not a known option', 'unrecognized option']),
                    'Unsupported IDE option: ' + name)
            return result
        phase('Probe the exact IDE and all six separate-state options')
        version = checked('version', [str(code), *flags, '--version'])
        require(version.stdout.splitlines()[0].strip() == '1.143.0', 'Unexpected native IDE version')
        checked('help', [str(code), *flags, '--help'])
        phase('Configure only new fictional source roots')
        checked('configure', ['/usr/bin/python3', '-I', '-B', str(payload / 'tools/configure.py'),
                             '--root', str(fixtures)])
        policy_hash = file_sha(state / 'policy.json')
        workspace_hash = file_sha(state / 'Atlas.code-workspace')
        settings = state / 'vscode-user/User'
        settings.mkdir(parents=True)
        new_json(settings / 'settings.json', {'workbench.startupEditor': 'none',
                 'window.newWindowDimensions': 'maximized', 'window.restoreWindows': 'none'})
        new_json(session / 'session.json', {'kind': 'code-atlas-native-acceptance-v1',
                 'session': str(session), 'fixtures': str(fixtures), 'state': str(state)})
        new_json(session / 'fixture-baseline.json', baseline)
        phase('Install the unchanged published VSIX')
        checked('install', [str(code), *flags, '--install-extension', str(payload / 'code-atlas-0.1.0.vsix')])
        listed = checked('extensions', [str(code), *flags, '--list-extensions', '--show-versions'])
        require('theoutlandsdev.code-atlas@0.1.0' in listed.stdout.lower(), 'Published VSIX not registered')
        env['ATLAS_ACCEPTANCE_SESSION'] = str(session)
        untrusted = session / 'untrusted/Untrusted.code-workspace'
        untrusted.parent.mkdir()
        new_json(untrusted, {'folders': [], 'settings': {'security.workspace.trust.enabled': True}})
        for launch in ['untrusted-before', 'first', 'restart', 'untrusted-after']:
            if launch == 'first':
                phase('Provision trust for the exact generated workspace file only')
                require(hashes(fixtures) == baseline, 'Generated sources changed before trust review')
                provision_fixture_trust(state, state / 'Atlas.code-workspace')
                report['trust_setup'] = 'Exact generated workspace file in a disposable pinned-version profile only'
            workspace = untrusted if launch == 'untrusted-after' else state / 'Atlas.code-workspace'
            phase('Real native extension host: ' + launch)
            env['ATLAS_ACCEPTANCE_PHASE'] = launch
            checked('native-' + launch, [str(code), *flags, '--sync', 'off', '--new-window', '--wait',
                    '--extensionDevelopmentPath=' + str(ROOT / 'tests/native/harness'),
                    '--extensionTestsPath=' + str(ROOT / 'tests/native/harness/native-check.cjs'),
                    str(workspace)], 180)
            result = json.loads((session / ('native-' + launch + '.json')).read_text())
            report['last_native_result'] = {'launch': launch, 'status': result.get('status'),
                    'last_passed_check': result.get('checks', [{}])[-1].get('name'),
                    'failed_check': result.get('failedCheck')}
            require(result['status'] == 'PASS' and result['platform'] == 'linux', 'Native assertions failed')
            require(hashes(fixtures) == baseline and file_sha(state / 'policy.json') == policy_hash and
                    file_sha(state / 'Atlas.code-workspace') == workspace_hash,
                    'Fictional source bytes or configuration changed')
            report['phases'].append({'launch': launch, 'assertions': len(result['checks']), 'result': 'PASS'})
            report['native_executed'] = True
        report.update(status='PASS', fixture_bytes_restored=True, setup_configuration_preserved=True,
                      isolated_setting_and_catalog_persisted=True, unrelated_workspace_remained_untrusted=True,
                      capture_scope='Actual IDE on a private CI virtual display; manual UI input remains separate')
        print('Native API acceptance passed on first launch and restart. Manual UI input remains separate.', flush=True)
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__)
        raise
    finally:
        session = work / 'session'
        if session.exists():
            for name in ['native-untrusted-before.json', 'native-untrusted-after.json',
                         'native-first.json', 'native-restart.json', 'first-map.png', 'first-readonly-source.png',
                         'restart-map.png', 'restart-readonly-source.png']:
                source = session / name
                if source.is_file():
                    shutil.copyfile(source, artifacts / name)
        (artifacts / 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STOP:', type(error).__name__, str(error)[:300], file=sys.stderr)
        sys.exit(1)
