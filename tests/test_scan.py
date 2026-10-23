"""Synthetic fixtures only: no workstation inventory or project execution."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


scan = module('scan')
configure = module('configure')


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='code-atlas-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'code'
        self.project.mkdir()
        self.home = self.base / 'atlas'
        self.raw = json.loads((ROOT / 'examples/policy.example.json').read_text())
        self.raw['bases'] = [str(self.project)]
        self.raw['seedRoots'] = [str(self.project)]

    def write(self, rel, content):
        file = self.project / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
        return file

    def result(self):
        return scan.Scanner(scan.Policy(self.raw)).run()

    def test_no_roots_does_not_discover_anything(self):
        self.raw['bases'] = []
        self.raw['seedRoots'] = []
        self.assertEqual(self.result()['projects'], [])

    def test_language_detection_and_syntax_only(self):
        self.write('main.py', 'raise RuntimeError("must not execute")\n')
        self.write('src/lib.rs', 'pub fn answer() -> u32 { 42 }\n')
        result = self.result()
        row = result['projects'][0]
        self.assertEqual(row['fileCount'], 2)
        self.assertEqual(row['languages'], ['Python', 'Rust'])
        self.assertEqual(row['validation']['syntaxPassed'], 1)
        self.assertEqual(row['validation']['unsupported'], 1)

    def test_invalid_python_and_json_are_reported_without_diagnostic_content(self):
        self.write('main.py', 'def invalid(\n')
        self.write('sample.json', '{bad')
        result = self.result()
        self.assertEqual(result['validation']['errors'], 2)
        self.assertNotIn('{bad', json.dumps(result))
        self.assertNotIn('def invalid', json.dumps(result))

    def test_secret_generated_hidden_document_data_names_excluded(self):
        for name in ['secrets', 'node_modules', '.git', 'private', 'documents', 'data', 'target']:
            self.write(name + '/hidden.py', 'pass\n')
        self.write('credentials.json', '{}')
        self.write('.env', 'password=fictional')
        self.write('main.py', 'pass\n')
        result = self.result()
        self.assertEqual(result['coverage']['codeFiles'], 1)
        self.assertEqual(result['coverage']['excludedDirectories'], 9)

    def test_symlink_file_directory_and_external_source_not_read(self):
        self.write('main.py', 'pass\n')
        outside = self.base / 'outside.py'
        outside.write_text('def broken(\n')
        (self.project / 'alias.py').symlink_to(outside)
        (self.project / 'loop').symlink_to(self.project)
        self.assertEqual(self.result()['coverage']['codeFiles'], 1)

    def test_project_markers_split_nested_projects(self):
        self.write('one/pyproject.toml', '[project]\nname="example"\n')
        self.write('one/main.py', 'pass\n')
        self.write('two/Cargo.toml', '[package]\nname="example"\n')
        self.write('two/lib.rs', 'fn answer(){}\n')
        result = self.result()
        self.assertEqual(len(result['projects']), 3)
        self.assertEqual(sum(row['fileCount'] for row in result['projects']), 4)

    def test_directory_file_depth_and_project_budgets_are_visible(self):
        self.write('a/b/c/main.py', 'pass\n')
        self.write('first.py', 'pass\n')
        self.write('second.py', 'pass\n')
        for key in ['maxDirectories', 'maxScanFiles', 'maxDirectoryEntries', 'maxDiscoveryDepth']:
            raw = copy.deepcopy(self.raw)
            raw[key] = 1
            result = scan.Scanner(scan.Policy(raw)).run()
            self.assertTrue(result['coverage']['limited'], key)

    def test_excluded_prefix_is_enforced(self):
        self.write('sub/main.py', 'pass\n')
        self.raw['excludedPathPrefixes'] = [str(self.project / 'sub')]
        self.assertEqual(self.result()['coverage']['codeFiles'], 0)

    def test_oversized_file_is_not_read(self):
        self.write('main.py', 'pass\n' * 20)
        self.raw['maxFileBytes'] = 4
        self.assertEqual(self.result()['coverage']['codeFiles'], 0)

    def test_unsafe_limits_and_seeds_rejected(self):
        for key in ['maxSeconds', 'maxDirectories', 'maxFileBytes']:
            raw = copy.deepcopy(self.raw)
            raw[key] = -1
            with self.assertRaises(ValueError):
                scan.Scanner(scan.Policy(raw))
        self.raw['seedRoots'] = ['/not/configured']
        with self.assertRaises(ValueError):
            scan.Policy(self.raw)

    def test_private_configuration_and_atomic_catalog(self):
        configure.configure([str(self.project)], str(self.home))
        self.write('main.py', 'pass\n')
        before = (self.project / 'main.py').read_bytes()
        result = scan.scan(str(self.home))
        self.assertEqual(result['coverage']['codeFiles'], 1)
        self.assertEqual((self.project / 'main.py').read_bytes(), before)
        self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.home / 'state').stat().st_mode), 0o700)
        for name in ['policy.json', 'Atlas.code-workspace', 'state/catalog.json']:
            self.assertEqual(stat.S_IMODE((self.home / name).stat().st_mode), 0o600)
        self.assertFalse(list((self.home / 'state').glob('*.tmp')))

    def test_configure_refuses_overwrite_broad_root_and_source_state_overlap(self):
        configure.configure([str(self.project)], str(self.home))
        before = (self.home / 'policy.json').read_bytes()
        with self.assertRaises(ValueError):
            configure.configure([str(self.project)], str(self.home))
        self.assertEqual((self.home / 'policy.json').read_bytes(), before)
        with self.assertRaises(ValueError):
            configure.configure(['/'], str(self.base / 'new'))
        with self.assertRaises(ValueError):
            configure.configure([str(self.project)], str(self.project / 'atlas'))

    def test_configure_refuses_symlink_root_and_target_ancestor(self):
        link = self.base / 'link'
        link.symlink_to(self.project)
        with self.assertRaises(ValueError):
            configure.configure([str(link)], str(self.home))
        with self.assertRaises(ValueError):
            configure.configure([str(self.project)], str(link / 'atlas'))

    def test_publicly_readable_state_is_rejected(self):
        configure.configure([str(self.project)], str(self.home))
        self.home.chmod(0o755)
        with self.assertRaises(ValueError):
            scan.scan(str(self.home))

    def test_reviewed_workspace_is_metadata_only(self):
        self.write('main.py', 'pass\n')
        self.raw['reviewedTests'] = [{'rootPath': str(self.project), 'workspace': str(self.base / 'Test.code-workspace')}]
        self.assertEqual(self.result()['projects'][0]['testStatus'], 'REVIEWED_ISOLATED_TESTS')


if __name__ == '__main__':
    unittest.main()
