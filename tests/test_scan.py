"""Synthetic fixtures only: no workstation inventory or project execution."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

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
        self.assertEqual(row['programLines'], 2)
        self.assertTrue(row['programLinesComplete'])

    def test_physical_lines_include_unterminated_last_line_without_content(self):
        self.write('main.py', 'one\r\ntwo\r\nthree')
        self.write('style.css', '')
        result = self.result()
        row = result['projects'][0]
        self.assertEqual(row['programLines'], 3)
        self.assertEqual(row['programLineFiles'], 2)
        self.assertTrue(result['coverage']['programLinesComplete'])
        self.assertNotIn('three', json.dumps(result))

    def test_line_count_budget_reports_partial_count(self):
        self.write('first.css', 'one\n')
        self.write('second.css', 'two\n')
        self.raw['maxLineCountBytes'] = 4
        result = self.result()
        self.assertEqual(result['coverage']['programLines'], 1)
        self.assertEqual(result['coverage']['programLinePendingFiles'], 1)
        self.assertFalse(result['coverage']['programLinesComplete'])
        self.assertTrue(result['coverage']['complete'])

    def test_refresh_recounts_replaced_source_without_retaining_old_total(self):
        file = self.write('main.py', 'pass\n' * 39)
        self.assertEqual(self.result()['coverage']['programLines'], 39)
        replacement = self.base / 'replacement.py'
        replacement.write_text('pass\n' * 123)
        replacement.replace(file)
        result = self.result()
        self.assertEqual(result['coverage']['programLines'], 123)
        self.assertEqual(result['coverage']['programLinePendingFiles'], 0)
        self.assertEqual(result['validation']['pending'], 0)
        self.assertEqual(result['projects'][0]['validation']['syntaxPassed'], 1)

    def test_regular_refuses_path_replacement_after_read(self):
        file = self.write('main.py', 'pass\n')
        replacement = self.base / 'replacement.py'
        replacement.write_text('pass\n')
        real_fstat = os.fstat
        replaced = False
        observations = 0

        def replace_after_final_descriptor_check(fd):
            nonlocal replaced, observations
            info = real_fstat(fd)
            observations += 1
            if observations == 2:
                replacement.replace(file)
                replaced = True
            return info

        with mock.patch.object(scan.os, 'fstat', side_effect=replace_after_final_descriptor_check):
            with self.assertRaises(ValueError):
                scan.regular(file, 32)
        self.assertTrue(replaced)

    def test_regular_refuses_redirected_ancestor_after_read(self):
        file = self.write('main.py', 'pass\n')
        moved = self.base / 'moved-code'
        real_read = os.read
        redirected = False

        def redirect_after_read(fd, size):
            nonlocal redirected
            data = real_read(fd, size)
            if data and not redirected:
                self.project.rename(moved)
                self.project.symlink_to(moved, target_is_directory=True)
                redirected = True
            return data

        with mock.patch.object(scan.os, 'read', side_effect=redirect_after_read):
            with self.assertRaises(ValueError):
                scan.regular(file, 32)
        self.assertTrue(redirected)

    def result_after_discovery_replacement(self, name, content):
        file = self.project / name
        replacement = self.base / 'replacement-source'
        replacement.write_text(content)
        scanner = scan.Scanner(scan.Policy(self.raw))
        entries = scanner.entries
        replaced = False

        def replace_after_entries(directory):
            nonlocal replaced
            result = entries(directory)
            if directory == str(self.project) and not replaced:
                replacement.replace(file)
                replaced = True
            return result

        with mock.patch.object(scanner, 'entries', side_effect=replace_after_entries):
            result = scanner.run()
        self.assertTrue(replaced)
        return scanner, result

    def test_changed_discovery_metadata_defers_both_count_and_parser(self):
        self.write('main.py', 'pass\n')
        scanner, result = self.result_after_discovery_replacement('main.py', 'pass\npass\n')
        self.assertEqual(scanner.line_bytes, 0)
        self.assertEqual(result['coverage']['programLines'], 0)
        self.assertEqual(result['coverage']['programLinePendingFiles'], 1)
        self.assertEqual(result['validation']['pending'], 1)
        self.assertEqual(result['projects'][0]['validation']['syntaxPassed'], 0)

    def test_grown_source_cannot_exceed_remaining_line_byte_budget(self):
        self.write('style.css', 'one\n')
        self.raw['maxLineCountBytes'] = 4
        scanner, result = self.result_after_discovery_replacement('style.css', 'two\nthree\n')
        self.assertEqual(scanner.line_bytes, 0)
        self.assertEqual(result['coverage']['programLines'], 0)
        self.assertEqual(result['coverage']['programLinePendingFiles'], 1)
        self.assertFalse(result['coverage']['programLinesComplete'])

    def test_same_size_replacement_does_not_reuse_discovery_identity(self):
        self.write('style.css', 'old\n')
        scanner, result = self.result_after_discovery_replacement('style.css', 'new\n')
        self.assertEqual(scanner.line_bytes, 0)
        self.assertEqual(result['coverage']['programLinePendingFiles'], 1)

    def test_regular_empty_file_reads_no_bytes_at_zero_remaining_budget(self):
        file = self.write('style.css', '')
        with mock.patch.object(scan.os, 'read', side_effect=AssertionError('No read allowance')):
            self.assertEqual(scan.regular(file, 0, expected=file.stat()), b'')

    def test_zero_syntax_pending_does_not_establish_full_discovery(self):
        self.write('a/main.py', 'pass\n')
        self.raw['maxDirectories'] = 1
        result = self.result()
        self.assertEqual(result['validation']['pending'], 0)
        self.assertTrue(result['coverage']['limited'])
        self.assertFalse(result['coverage']['complete'])
        self.assertFalse(result['coverage']['programLinesComplete'])

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
