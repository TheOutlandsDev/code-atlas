#!/usr/bin/env python3
"""Check public setup docs offline; optionally verify the pinned release downloads."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import stat
import tempfile
import textwrap
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024
STATE_DIRS = {
    '--user-data-dir': 'vscode-user',
    '--extensions-dir': 'vscode-extensions',
    '--shared-data-dir': 'vscode-shared',
    '--agent-plugins-dir': 'agent-plugins',
    '--agents-user-data-dir': 'agents-user',
    '--agents-extensions-dir': 'agents-extensions',
}
PAYLOADS = {'LICENSE', 'SETUP.md', 'SOURCE.json', 'code-atlas-0.1.0.vsix',
            'examples/policy.example.json', 'tools/configure.py'}
ASSETS = {'code-atlas-0.1.0.vsix', 'code-atlas-0.1.0-setup-r2.zip',
          'SETUP-r2.md', 'SHA256SUMS-r2'}


class ReleaseError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_file(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_BYTES,
                'Expected a bounded regular release file')
        data = source.read(MAX_BYTES + 1)
        after = os.fstat(source.fileno())
    require(len(data) <= MAX_BYTES and
            (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            'Release file changed while reading')
    return data


def checksums(data, expected):
    entries = {}
    for line in data.decode('ascii').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_./-]+)', line)
        require(match is not None, 'Malformed SHA256SUMS line')
        name = match[2]
        require(name in expected and name not in entries,
                'Unexpected or duplicate checksum entry: ' + name)
        entries[name] = match[1]
    require(set(entries) == set(expected), 'Missing checksum entries')
    return entries


def setup_commands(text):
    commands = []
    blocks = re.findall(r'^[ \t]*```(?:sh|bash)\n(.*?)^[ \t]*```',
                        text, flags=re.MULTILINE | re.DOTALL)
    for block in blocks:
        for line in textwrap.dedent(block).replace('\\\n', '').splitlines():
            words = shlex.split(line, comments=True)
            if not words or words[0] != 'code':
                continue
            if words == ['code', '--version']:
                continue
            require('--disable-workspace-trust' not in words,
                    'Setup must keep workspace trust enabled')
            expected = ['code']
            for option, folder in STATE_DIRS.items():
                expected += [option, '$CODE_ATLAS_HOME/' + folder]
            if '--install-extension' in words:
                expected += ['--install-extension', './code-atlas-0.1.0.vsix']
                kind = 'install'
            else:
                expected += ['--sync', 'off', '--new-window',
                             '$CODE_ATLAS_HOME/Atlas.code-workspace']
                kind = 'launch'
            require(words == expected,
                    'Setup code command differs from the complete revision 2 ' + kind + ' recipe')
            commands.append(kind)
    return commands


def load_lock(root):
    lock = json.loads(read_file(root / 'release/setup-r2.json'))
    require(lock.get('schemaVersion') == 1 and lock.get('setupRevision') == 2 and
            lock.get('repository') == 'TheOutlandsDev/code-atlas' and
            lock.get('version') == '0.1.0' and lock.get('tag') == 'v0.1.0' and
            lock.get('prefix') == 'code-atlas-0.1.0-setup-r2/', 'Unsupported release lock identity')
    require(set(lock.get('assets', {})) == ASSETS and
            set(lock.get('payloads', {})) == PAYLOADS, 'Unexpected release lock allowlist')
    for spec in [*lock['assets'].values(), *lock['payloads'].values()]:
        require(set(spec) == {'bytes', 'sha256'} and type(spec['bytes']) is int and
                0 < spec['bytes'] <= MAX_BYTES and
                re.fullmatch(r'[0-9a-f]{64}', spec['sha256']) is not None,
                'Invalid release lock size or digest')
    identity = lock.get('sourceIdentity', {})
    require(identity.get('repository') == 'https://github.com/TheOutlandsDev/code-atlas' and
            identity.get('tag') == lock['tag'] and identity.get('version') == lock['version'] and
            identity.get('setupGuideRevision') == 2 and identity.get('license') == 'MIT' and
            re.fullmatch(r'[0-9a-f]{40}', identity.get('commit', '')) is not None and
            identity.get('vsixSha256') == lock['assets']['code-atlas-0.1.0.vsix']['sha256'] and
            identity.get('setupGuideSha256') == lock['assets']['SETUP-r2.md']['sha256'],
            'Invalid public source provenance')
    return lock


def verify_bytes(data, spec, name):
    require(len(data) == spec['bytes'] and digest(data) == spec['sha256'],
            'Size or SHA-256 mismatch: ' + name)


def check_repository(root=ROOT):
    lock = load_lock(root)
    guide = read_file(root / 'docs/setup-r2.md')
    verify_bytes(guide, lock['assets']['SETUP-r2.md'], 'current setup guide')
    require(setup_commands(guide.decode()) == ['install', 'launch'],
            'Guide must contain one install and one launch command')
    for file in [root / 'README.md', root / 'CONTRIBUTING.md', *sorted((root / 'docs').glob('*.md'))]:
        setup_commands(read_file(file).decode())
    readme = read_file(root / 'README.md').decode()
    require('(docs/setup-r2.md)' in readme and
            'code-atlas-0.1.0-setup-r2.zip' in readme and 'SHA256SUMS-r2' in readme,
            'README must point to current revision 2 setup and checksums')
    for name in ['docs/configuration.md', 'docs/troubleshooting.md']:
        text = read_file(root / name).decode()
        require('(setup-r2.md)' in text and '--shared-data-dir' in text,
                'Setup reference is stale: ' + name)
    for name in ['LICENSE', 'tools/configure.py', 'examples/policy.example.json']:
        verify_bytes(read_file(root / name), lock['payloads'][name], name)
    policy = json.loads(read_file(root / 'examples/policy.example.json'))
    require(all(not policy.get(key) for key in ['bases', 'seedRoots', 'seedLabels', 'reviewedTests']),
            'Example policy must not configure real source roots')
    return lock


def check_zip(data, lock):
    prefix = lock['prefix']
    expected = {prefix + name for name in PAYLOADS | {'SHA256SUMS'}}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        require(len(entries) == len(expected) and {i.filename for i in entries} == expected,
                'ZIP must contain exactly seven unique allowed entries')
        for item in entries:
            require(stat.S_ISREG(item.external_attr >> 16) and not item.flag_bits & 1 and
                    item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and
                    0 < item.file_size <= MAX_BYTES, 'Unsafe ZIP entry: ' + item.filename)
        require(sum(i.file_size for i in entries) <= MAX_BYTES, 'ZIP payload budget exceeded')
        payload = {name: archive.read(prefix + name) for name in PAYLOADS | {'SHA256SUMS'}}
    inner = checksums(payload['SHA256SUMS'], PAYLOADS)
    for name in PAYLOADS:
        require(digest(payload[name]) == inner[name], 'Inner checksum mismatch: ' + name)
        verify_bytes(payload[name], lock['payloads'][name], name)
    require(json.loads(payload['SOURCE.json']) == lock['sourceIdentity'],
            'ZIP public provenance differs from release lock')
    require(payload['code-atlas-0.1.0.vsix'] and
            digest(payload['code-atlas-0.1.0.vsix']) == lock['assets']['code-atlas-0.1.0.vsix']['sha256'],
            'Bundled VSIX differs from standalone installer')
    require(digest(payload['SETUP.md']) == lock['assets']['SETUP-r2.md']['sha256'],
            'Bundled guide differs from standalone guide')
    setup_commands(payload['SETUP.md'].decode())


def check_assets(directory, lock):
    # Read only four fixed public artifact names; do not walk the supplied directory.
    assets = {name: read_file(directory / name) for name in ASSETS}
    for name, data in assets.items():
        verify_bytes(data, lock['assets'][name], name)
    outer = checksums(assets['SHA256SUMS-r2'], ASSETS - {'SHA256SUMS-r2'})
    for name, sha in outer.items():
        require(digest(assets[name]) == sha, 'Outer checksum mismatch: ' + name)
    check_zip(assets['code-atlas-0.1.0-setup-r2.zip'], lock)


def download_url(name, lock):
    require(name in ASSETS, 'Only pinned public assets may be downloaded')
    return 'https://github.com/' + lock['repository'] + '/releases/download/' + lock['tag'] + '/' + name


class GithubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ''
        require(parsed.scheme == 'https' and not parsed.username and not parsed.password and
                (host == 'github.com' or host.endswith('.githubusercontent.com')),
                'Release download redirected outside GitHub HTTPS')
        return super().redirect_request(request, fp, code, message, headers, url)


def download_assets(directory, lock):
    opener = urllib.request.build_opener(GithubRedirects())
    for name in sorted(ASSETS):
        request = urllib.request.Request(download_url(name, lock), headers={'User-Agent': 'Code-Atlas-release-check'})
        with opener.open(request, timeout=30) as response:
            data = response.read(lock['assets'][name]['bytes'] + 1)
        verify_bytes(data, lock['assets'][name], name)
        with (directory / name).open('xb') as target:
            target.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--assets-dir', type=Path, help='Read the four pinned assets from this directory')
    group.add_argument('--download', action='store_true', help='Download only the four pinned public GitHub assets')
    args = parser.parse_args()
    try:
        lock = check_repository()
        if args.assets_dir:
            check_assets(args.assets_dir, lock)
        elif args.download:
            with tempfile.TemporaryDirectory(prefix='code-atlas-release-') as temporary:
                directory = Path(temporary)
                download_assets(directory, lock)
                check_assets(directory, lock)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, 'Release check failed: ' + str(error) + '\n')
    print('PASS: revision 2 docs, setup commands and public release lock')
    if args.assets_dir or args.download:
        print('PASS: four pinned assets, exact seven-entry ZIP, six inner and three outer checksums')


if __name__ == '__main__':
    main()
