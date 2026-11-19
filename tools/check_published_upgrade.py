#!/usr/bin/env python3
"""Run a checksum-pinned Code Atlas 0.1.2 to 0.1.3 upgrade on synthetic files."""
import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tarfile
import tempfile
from time import monotonic
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_native as native
import check_release as release

RELEASE_URL = 'https://github.com/TheOutlandsDev/code-atlas/releases/download'
VERSIONS = {
    '0.1.2': {
        'code-atlas-0.1.2.vsix': {
            'bytes': 58272,
            'sha256': '76b884f103147ac1b684241a11fc07592163615cabe31d8fa292f0625393cce9',
        },
        'SHA256SUMS-0.1.2': {
            'bytes': 88,
            'sha256': '1f47cb8e1275c83a085552097e3abcb3363b2ea27cf6b8ecee589b0834c9d049',
        },
    },
    '0.1.3': {
        'code-atlas-0.1.3.vsix': {
            'bytes': 59938,
            'sha256': '5abfcb5e085e847da74bd76cd2a19cf0323e8c17741f8a185c7443b16b9df1df',
        },
        'SHA256SUMS-0.1.3': {
            'bytes': 88,
            'sha256': 'da2179d0cbf4b523d6603f6e912a2a9b2871996daee90b5f9201a0fb85f4c656',
        },
    },
}
BASELINE, UPGRADE = VERSIONS
FIXTURES = {
    'pyproject.toml': '[project]\nname = "atlas-orchard"\nversion = "0.0.1"\n',
    'main.py': 'answer = 42\n',
    'legacy.PY': 'legacy = 17\n',
    'mixed.pY': 'fruit = "pear"\n',
    'settings.JsOn': '{"fruit": "apple"}\n',
    'node_modules/ignored.pY': 'excluded = True\n',
}


def stage_releases(destination, supplied, report):
    """Validate each release before copying verified bytes to the private session."""
    destination.mkdir()
    opener = urllib.request.build_opener(release.GithubRedirects())
    for version, entries in VERSIONS.items():
        payload = {}
        for name, spec in entries.items():
            if supplied:
                data = release.read_file(supplied / name)
            else:
                request = urllib.request.Request(
                    f'{RELEASE_URL}/v{version}/{name}',
                    headers={'User-Agent': 'Code-Atlas-release-upgrade-check'},
                )
                with opener.open(request, timeout=30) as response:
                    data = response.read(spec['bytes'] + 1)
            release.verify_bytes(data, spec, name)
            payload[name] = data
        vsix = f'code-atlas-{version}.vsix'
        checksum = f'SHA256SUMS-{version}'
        native.require(
            release.checksums(payload[checksum], {vsix})[vsix] == entries[vsix]['sha256'],
            'Published checksum disagrees with the pinned VSIX',
        )
        with zipfile.ZipFile(io.BytesIO(payload[vsix])) as package:
            manifest = json.loads(package.read('extension/package.json'))
        native.require(
            manifest['name'] == 'code-atlas' and manifest['publisher'] == 'TheOutlandsDev'
            and manifest['version'] == version,
            'Unexpected published extension identity',
        )
        (destination / vsix).write_bytes(payload[vsix])
        report['versions'][version] = entries


def extract_ide(work, supplied, report):
    lock = json.loads((ROOT / 'tests/native/ide-lock.json').read_text())
    native.require(
        (lock['version'], lock['platform'], lock['url']) ==
        ('1.143.0', 'linux-x64', 'https://update.code.visualstudio.com/1.143.0/linux-x64/stable'),
        'Unsupported IDE lock identity',
    )
    archive = native.ide_archive(work, supplied, lock)
    ide = work / 'ide'
    ide.mkdir()
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        native.require(
            len(members) < 50000 and sum(member.size for member in members) < 4 * 1024**3
            and all(member.name == 'VSCode-linux-x64'
                    or member.name.startswith('VSCode-linux-x64/') for member in members),
            'Unexpected IDE archive structure or size',
        )
        bundle.extractall(ide, members=members, filter='data')
    report['ide'] = {key: lock[key] for key in ('version', 'platform', 'sha256')}
    return ide / 'VSCode-linux-x64'


def run_command(work, env, label, command, timeout=90):
    """Keep raw process output private and terminate only the owned process group on timeout."""
    log = work / f'{label}.log'
    with log.open('xb') as output:
        process = subprocess.Popen(
            command, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=output,
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            status = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
            raise RuntimeError(f'{label} timed out') from None
    native.require(status == 0, f'{label} exited {status}')
    content = log.read_text(errors='replace')
    native.require(
        not any(message in content.lower() for message in
                ('unknown option', 'not a known option', 'unrecognized option')),
        f'{label} reported an unsupported IDE option',
    )
    return content


def prepare_session(work, cli):
    state = work / 'state'
    root = work / 'fixtures' / 'orchard'
    for name, content in FIXTURES.items():
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding='utf-8')
    home = work / 'home'
    runtime = work / 'runtime'
    home.mkdir()
    runtime.mkdir()
    env = {
        'HOME': str(home), 'USER': 'atlas-fixture', 'LOGNAME': 'atlas-fixture',
        'LANG': 'C.UTF-8', 'PATH': '/usr/bin:/bin',
        'DISPLAY': os.environ['DISPLAY'], 'XAUTHORITY': os.environ['XAUTHORITY'],
        'XDG_RUNTIME_DIR': str(runtime), 'CODE_ATLAS_HOME': str(state),
        'PYTHONDONTWRITEBYTECODE': '1', 'ATLAS_UPGRADE_SESSION': str(work),
    }
    flags = [item for arg, folder in native.STATE for item in ('--' + arg, str(state / folder))]
    version = run_command(work, env, 'ide-version', [cli, *flags, '--version'], timeout=30)
    native.require(version.splitlines()[:1] == ['1.143.0'], 'Unexpected Linux IDE version')
    run_command(
        work, env, 'configure',
        [sys.executable, '-I', '-B', ROOT / 'tools/configure.py', '--root', root], timeout=30,
    )
    policy_path = state / 'policy.json'
    policy = json.loads(policy_path.read_text())
    policy['codeExtensions']['.PY'] = 'Custom Python'
    policy_path.write_text(json.dumps(policy, indent=2) + '\n', encoding='utf-8')
    settings = state / 'vscode-user' / 'User' / 'settings.json'
    settings.parent.mkdir(parents=True, exist_ok=True)
    native.new_json(settings, {
        'update.mode': 'none', 'extensions.autoCheckUpdates': False, 'extensions.autoUpdate': False,
        'telemetry.telemetryLevel': 'off', 'workbench.startupEditor': 'none', 'window.restoreWindows': 'none',
        'security.workspace.trust.startupPrompt': 'never',
    })
    return state, root, env, flags


def install(work, env, cli, flags, state, version):
    asset = work / 'releases' / f'code-atlas-{version}.vsix'
    run_command(work, env, f'install-{version}', [cli, *flags, '--install-extension', asset])
    listed = run_command(
        work, env, f'extensions-{version}', [cli, *flags, '--list-extensions', '--show-versions'],
        timeout=30,
    )
    native.require(
        listed.strip().lower() == f'theoutlandsdev.code-atlas@{version}',
        'Expected exactly the release extension in the disposable profile',
    )
    installed = state / 'vscode-extensions' / f'theoutlandsdev.code-atlas-{version}'
    with zipfile.ZipFile(asset) as package:
        manifest = json.loads((installed / 'package.json').read_text())
        manifest.pop('__metadata', None)  # VS Code adds installation metadata to the manifest.
        native.require(manifest == json.loads(package.read('extension/package.json')),
                       'Installed manifest fields differ from the verified VSIX')
        for name in ('extension/extension.js', 'extension/policy.js', 'tools/scan.py'):
            native.require((installed / name).read_bytes() == package.read('extension/' + name),
                           f'Installed runtime differs from the verified VSIX for {name}')


def exercise_upgrade(work, ide, report):
    cli = ide / 'bin' / 'code'
    editor = ide / 'code'
    state, root, env, flags = prepare_session(work, cli)
    workspace = state / 'Atlas.code-workspace'
    config = (state / 'policy.json', workspace)
    config_hashes = [native.file_sha(file) for file in config]
    fixture_hashes = native.hashes(root)
    harness = ROOT / 'tests/native/upgrade-harness'

    def launch(phase):
        report['stage'] = phase
        print(f'Native upgrade phase: {phase}', flush=True)
        env['ATLAS_UPGRADE_PHASE'] = phase
        run_command(
            work, env, phase,
            [editor, *flags, '--sync', 'off', '--new-window',
             '--disable-setuid-sandbox', '--disable-gpu',
             f'--extensionDevelopmentPath={harness}', workspace],
        )
        result_path = work / f'{phase}.json'
        native.require(result_path.is_file(), 'Native harness did not produce a result')
        result = json.loads(result_path.read_text())
        if result['status'] != 'PASS':
            # Native check labels are test literals and never contain local paths.
            report['failed_check'] = result.get('failedCheck', 'Native harness did not complete')
            raise RuntimeError('Native harness assertion failed')
        native.require([native.file_sha(file) for file in config] == config_hashes,
                       'Policy or workspace configuration changed')
        native.require(native.hashes(root) == fixture_hashes and not any(file.is_symlink() for file in root.rglob('*')),
                       'Synthetic source bytes or membership changed')
        report['phases'][phase] = {
            'assertions': len(result['checks']),
            **{key: result[key] for key in ('installedVersion', 'indexed', 'generation') if key in result},
        }

    report['stage'] = 'install-baseline'
    install(work, env, cli, flags, state, BASELINE)
    launch('untrusted')
    report['stage'] = 'trust-generated-workspace'
    native.provision_fixture_trust(state, workspace)
    launch('baseline')
    catalog = state / 'state' / 'catalog.json'
    previous = native.file_sha(catalog)
    report['stage'] = 'install-upgrade'
    install(work, env, cli, flags, state, UPGRADE)
    native.require(native.file_sha(catalog) == previous,
                   'Upgrade installation changed the saved baseline catalog')
    report['baseline_catalog_retained_through_install'] = True
    launch('upgraded')
    launch('restart')
    report['configuration_and_fixture_bytes_preserved'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts-dir', type=Path, required=True,
                        help='New absolute directory for the single synthetic upgrade receipt')
    parser.add_argument('--assets-dir', type=Path,
                        help='Use locally downloaded copies of the four pinned GitHub release assets')
    parser.add_argument('--ide-archive', type=Path,
                        help='Use the same hash-pinned official Linux IDE archive already downloaded')
    args = parser.parse_args()
    os.umask(0o077)
    artifacts = args.artifacts_dir
    if not artifacts.is_absolute() or artifacts.exists():
        parser.error('--artifacts-dir must be a new absolute directory')
    artifacts.mkdir(mode=0o700)
    report = {
        'status': 'fail', 'stage': 'environment', 'versions': {}, 'phases': {},
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'synthetic_only': True, 'model_calls': 0, 'project_tests_executed': 0,
        'manual_ui_acceptance': 'not_run',
    }
    started = monotonic()
    try:
        native.require(sys.platform == 'linux' and platform.machine() == 'x86_64',
                       'Linux x64 required')
        native.require(os.environ.get('DISPLAY') and os.environ.get('XAUTHORITY'),
                       'Start the runner with xvfb-run and its private Xauthority')
        with tempfile.TemporaryDirectory(prefix='atlas-upgrade-') as directory:
            work = Path(directory).resolve()
            report['stage'] = 'verify-releases'
            stage_releases(work / 'releases', args.assets_dir, report)
            report['stage'] = 'verify-ide'
            ide = extract_ide(work, args.ide_archive, report)
            report['stage'] = 'prepare-session'
            exercise_upgrade(work, ide, report)
        report.update(status='pass', stage='complete')
    except Exception as error:
        report['error_type'] = type(error).__name__
        if type(error) in (RuntimeError, release.ReleaseError):
            # These errors contain fixed check labels, release filenames or the rejected
            # asset's pinned name. Never expose untrusted exception text from subprocesses,
            # parsing, network calls or the filesystem.
            detail = str(error)
            if len(detail) <= 200 and '/' not in detail and '\\' not in detail:
                report['error'] = detail
    finally:
        report['elapsed_seconds'] = round(monotonic() - started, 3)
        native.new_json(artifacts / 'upgrade.json', report)
        print(f'Published VSIX upgrade {report["status"]} at {report["stage"]}', flush=True)
        if report.get('error'):
            print(report['error'], file=sys.stderr)
        if report.get('failed_check'):
            print(report['failed_check'], file=sys.stderr)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
