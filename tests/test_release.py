"""Synthetic release failures; no network, IDE or external project discovery."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import struct
import tempfile
import unittest
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('atlas_release_check', ROOT / 'tools/check_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def archive(payload, changes=None, extra=(), modes=None, compression=zipfile.ZIP_DEFLATED):
    entries = {name: data for name, data in payload.items()}
    entries['SHA256SUMS'] = ''.join(checksum(data) + '  ' + name + '\n'
                                  for name, data in sorted(payload.items())).encode()
    entries.update(changes or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as target:
        for name, data in [*sorted(entries.items()), *extra]:
            info = zipfile.ZipInfo('code-atlas-0.1.0-setup-r2/' + name)
            info.external_attr = (modes or {}).get(name, stat.S_IFREG | 0o644) << 16
            info.compress_type = compression
            target.writestr(info, data)
    return output.getvalue()


def fixture():
    guide = (ROOT / 'docs/setup-r2.md').read_bytes()
    vsix = b'synthetic installer fixture\n'
    identity = copy.deepcopy(release.load_lock(ROOT)['sourceIdentity'])
    identity['vsixSha256'] = checksum(vsix)
    identity['setupGuideSha256'] = checksum(guide)
    payload = {'LICENSE': b'Synthetic MIT fixture\n', 'SETUP.md': guide,
               'SOURCE.json': (json.dumps(identity) + '\n').encode(),
               'code-atlas-0.1.0.vsix': vsix,
               'examples/policy.example.json': b'{"bases":[],"seedRoots":[],"reviewedTests":[]}\n',
               'tools/configure.py': b'# synthetic setup fixture\n'}
    bundle = archive(payload)
    assets = {'code-atlas-0.1.0.vsix': vsix, 'SETUP-r2.md': guide,
              'code-atlas-0.1.0-setup-r2.zip': bundle}
    assets['SHA256SUMS-r2'] = ''.join(checksum(data) + '  ' + name + '\n'
                                     for name, data in sorted(assets.items())).encode()
    lock = {'prefix': 'code-atlas-0.1.0-setup-r2/', 'repository': 'TheOutlandsDev/code-atlas',
            'tag': 'v0.1.0', 'sourceIdentity': identity,
            'assets': {name: {'bytes': len(data), 'sha256': checksum(data)} for name, data in assets.items()},
            'payloads': {name: {'bytes': len(data), 'sha256': checksum(data)} for name, data in payload.items()}}
    return payload, assets, lock


class ReleaseChecks(unittest.TestCase):
    def test_current_repository_and_commands_pass(self):
        release.check_repository(ROOT)
        self.assertEqual(release.setup_commands((ROOT / 'docs/setup-r2.md').read_text()),
                         ['install', 'launch'])

    def test_complete_synthetic_bundle_passes(self):
        _, assets, lock = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, data in assets.items():
                (directory / name).write_bytes(data)
            # An unrelated file is not walked, opened or required to be public.
            (directory / 'unrelated.txt').write_text('synthetic unrelated fixture')
            release.check_assets(directory, lock)

    def test_each_state_directory_is_required(self):
        text = (ROOT / 'docs/setup-r2.md').read_text()
        for option, folder in release.STATE_DIRS.items():
            with self.subTest(option=option):
                changed = text.replace(option + ' "$CODE_ATLAS_HOME/' + folder + '"', '')
                with self.assertRaises(release.ReleaseError):
                    release.setup_commands(changed)

    def test_launch_requires_sync_off(self):
        text = (ROOT / 'docs/setup-r2.md').read_text().replace('--sync off', '')
        with self.assertRaises(release.ReleaseError):
            release.setup_commands(text)

    def test_unqualified_default_profile_install_is_rejected(self):
        with self.assertRaises(release.ReleaseError):
            release.setup_commands('```sh\ncode --install-extension example.vsix\n```\n')

    def test_duplicate_or_trust_disabling_options_are_rejected(self):
        text = (ROOT / 'docs/setup-r2.md').read_text()
        for extra in ['--disable-workspace-trust', '--shared-data-dir unexpected']:
            with self.subTest(extra=extra), self.assertRaises(release.ReleaseError):
                release.setup_commands(text.replace('--sync off', '--sync off ' + extra))

    def test_checksum_parser_rejects_missing_duplicate_extra_and_malformed(self):
        line = '0' * 64 + '  LICENSE\n'
        for value in ['', line + line, line + '1' * 64 + '  inventory.json\n', 'bad  LICENSE\n']:
            with self.subTest(value=value), self.assertRaises(release.ReleaseError):
                release.checksums(value.encode(), {'LICENSE'})

    def test_outer_asset_tampering_fails(self):
        _, assets, lock = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, data in assets.items():
                (directory / name).write_bytes(data)
            (directory / 'code-atlas-0.1.0.vsix').write_bytes(b'changed synthetic bytes')
            with self.assertRaises(release.ReleaseError):
                release.check_assets(directory, lock)

    def test_extra_zip_inventory_entry_fails(self):
        payload, _, lock = fixture()
        with self.assertRaises(release.ReleaseError):
            release.check_zip(archive(payload, extra=[('inventory.json', b'{}')]), lock)

    def test_duplicate_zip_entry_fails(self):
        payload, _, lock = fixture()
        with self.assertWarns(UserWarning):
            data = archive(payload, extra=[('LICENSE', b'duplicate synthetic fixture')])
        with self.assertRaises(release.ReleaseError):
            release.check_zip(data, lock)

    def test_traversal_zip_entry_fails(self):
        payload, _, lock = fixture()
        with self.assertRaises(release.ReleaseError):
            release.check_zip(archive(payload, extra=[('../outside.py', b'# synthetic')]), lock)

    def test_symlink_zip_entry_fails(self):
        payload, _, lock = fixture()
        with self.assertRaises(release.ReleaseError):
            release.check_zip(archive(payload, modes={'LICENSE': stat.S_IFLNK | 0o777}), lock)

    def test_unsupported_zip_compression_fails(self):
        payload, _, lock = fixture()
        with self.assertRaises(release.ReleaseError):
            release.check_zip(archive(payload, compression=zipfile.ZIP_BZIP2), lock)

    def test_encrypted_zip_flag_fails_before_read(self):
        payload, _, lock = fixture()
        data = bytearray(archive(payload))
        for signature, offset in [(b'PK\x03\x04', 6), (b'PK\x01\x02', 8)]:
            at = data.find(signature)
            flags = struct.unpack_from('<H', data, at + offset)[0]
            struct.pack_into('<H', data, at + offset, flags | 1)
        with self.assertRaises(release.ReleaseError):
            release.check_zip(bytes(data), lock)

    def test_zip_size_budget_fails(self):
        payload, _, lock = fixture()
        payload['LICENSE'] = b'x' * (release.MAX_BYTES + 1)
        with self.assertRaises(release.ReleaseError):
            release.check_zip(archive(payload), lock)

    def test_inner_checksum_tampering_fails(self):
        payload, _, lock = fixture()
        with self.assertRaises(release.ReleaseError):
            release.check_zip(archive(payload, changes={'SETUP.md': b'tampered synthetic guide'}), lock)

    def test_recomputed_inner_manifest_does_not_bypass_lock(self):
        payload, _, lock = fixture()
        payload['LICENSE'] = b'changed synthetic license'
        with self.assertRaises(release.ReleaseError):
            release.check_zip(archive(payload), lock)

    def test_different_source_identity_fails(self):
        payload, _, lock = fixture()
        identity = json.loads(payload['SOURCE.json'])
        identity['commit'] = '0' * 40
        payload['SOURCE.json'] = json.dumps(identity).encode()
        lock['payloads']['SOURCE.json'] = {'bytes': len(payload['SOURCE.json']),
                                           'sha256': checksum(payload['SOURCE.json'])}
        with self.assertRaises(release.ReleaseError):
            release.check_zip(archive(payload), lock)

    def test_symlink_asset_is_rejected(self):
        _, assets, lock = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, data in assets.items():
                (directory / name).write_bytes(data)
            target = directory / 'code-atlas-0.1.0.vsix'
            target.rename(directory / 'fixture.vsix')
            target.symlink_to(directory / 'fixture.vsix')
            with self.assertRaises((OSError, release.ReleaseError)):
                release.check_assets(directory, lock)

    def test_only_pinned_public_download_names_are_allowed(self):
        _, _, lock = fixture()
        self.assertEqual(release.download_url('SETUP-r2.md', lock),
                         'https://github.com/TheOutlandsDev/code-atlas/releases/download/v0.1.0/SETUP-r2.md')
        with self.assertRaises(release.ReleaseError):
            release.download_url('../other', lock)

    def test_download_redirects_stay_on_github_https(self):
        redirect = release.GithubRedirects()
        request = urllib.request.Request('https://github.com/example')
        for url in ['http://github.com/example', 'https://example.invalid/example', 'file:///example']:
            with self.subTest(url=url), self.assertRaises(release.ReleaseError):
                redirect.redirect_request(request, None, 302, '', {}, url)
        good = redirect.redirect_request(request, None, 302, '', {},
                                         'https://release-assets.githubusercontent.com/example')
        self.assertEqual(good.host, 'release-assets.githubusercontent.com')

    def test_packaged_documentation_includes_current_setup_and_checks(self):
        package_spec = importlib.util.spec_from_file_location('atlas_public_package', ROOT / 'tools/package.py')
        package = importlib.util.module_from_spec(package_spec)
        package_spec.loader.exec_module(package)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in package.RUNTIME:
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            (directory / 'inventory.json').write_text('{}')
            package.ROOT = directory
            with contextlib.redirect_stdout(io.StringIO()):
                output = package.package()
            with zipfile.ZipFile(output) as archive_file:
                self.assertIn('extension/docs/setup-r2.md', archive_file.namelist())
                self.assertIn('extension/docs/release-checks.md', archive_file.namelist())
                self.assertNotIn('extension/inventory.json', archive_file.namelist())


if __name__ == '__main__':
    unittest.main()
