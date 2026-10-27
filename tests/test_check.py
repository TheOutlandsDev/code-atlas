"""Isolated regression checks. Node and all QA subprocesses are mocked."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('code_atlas_check_under_test', ROOT / 'tools/check.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
NODE = '/synthetic/node'


class NodeGuardTests(unittest.TestCase):
    def invoke(self, version='v20.11.1\n', *, available=True, probe_error=None):
        calls = []
        def process(command, **kwargs):
            command = list(command)
            calls.append((command, kwargs))
            if command == [NODE, '--version']:
                if probe_error is not None:
                    raise probe_error
                return types.SimpleNamespace(stdout=version, stderr='', returncode=0)
            return types.SimpleNamespace(stdout='', stderr='', returncode=0)
        output, error = io.StringIO(), None
        with mock.patch.object(runner.shutil, 'which', return_value=NODE if available else None), \
             mock.patch.object(runner.subprocess, 'run', side_effect=process), \
             mock.patch.dict(os.environ, {'NODE_TEST_CONTEXT': 'synthetic-nested-context', 'ATLAS_TEST_MARKER': 'keep'}), \
             mock.patch('sys.stdout', output):
            try:
                runner.main()
            except Exception as exc:
                error = exc
            except SystemExit as exc:
                error = exc
        return error, calls, output.getvalue()

    def assert_rejected(self, error, calls, output):
        self.assertIsInstance(error, SystemExit)
        self.assertIn('Node', str(error))
        self.assertIn('18', str(error))
        self.assertNotIn('Public synthetic suites passed', output)
        self.assertTrue(all(command == [NODE, '--version'] for command, _ in calls), 'QA suite started before failed preflight')

    def test_missing_node_rejects_without_subprocesses(self):
        result = self.invoke(available=False)
        self.assert_rejected(*result)
        self.assertEqual(result[1], [])

    def test_old_node_versions_reject_before_suites(self):
        for version in ['v0.12.18', 'v16.20.2\n', 'v17.9.1']:
            with self.subTest(version=version):
                self.assert_rejected(*self.invoke(version))

    def test_supported_versions_keep_all_six_suites_in_order(self):
        for version in ['v18.0.0\n', 'v20.11.1', '  v24.6.0\n']:
            with self.subTest(version=version):
                error, calls, output = self.invoke(version)
                self.assertIsNone(error)
                self.assertEqual(calls[0][0], [NODE, '--version'])
                self.assertEqual([c for c, _ in calls[1:]], [
                    [runner.sys.executable, '-I', '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                    [NODE, 'extension/tests/core.test.cjs'],
                    [NODE, 'extension/tests/activation.test.cjs'],
                    [NODE, 'extension/media/ui.test.cjs'],
                    [runner.sys.executable, '-I', '-B', 'tools/check_release.py'],
                    [runner.sys.executable, '-I', '-B', 'tools/check_setup.py'],
                ])
                self.assertIn('Public synthetic suites passed.', output)
                for _, kwargs in calls[1:]:
                    self.assertEqual(kwargs['cwd'], runner.ROOT)
                    self.assertIs(kwargs['check'], True)
                    self.assertEqual(kwargs['timeout'], 60)

    def test_malformed_stable_version_output_rejects(self):
        for version in ['', 'not-a-version', 'v18', 'v18.0', 'v18.0.0 trailing', '18.0.0']:
            with self.subTest(version=version):
                self.assert_rejected(*self.invoke(version))

    def test_probe_os_error_fails_cleanly(self):
        self.assert_rejected(*self.invoke(probe_error=OSError('synthetic unavailable executable')))

    def test_probe_nonzero_exit_fails_cleanly(self):
        self.assert_rejected(*self.invoke(probe_error=subprocess.CalledProcessError(1, [NODE, '--version'])))

    def test_probe_timeout_fails_cleanly(self):
        self.assert_rejected(*self.invoke(probe_error=subprocess.TimeoutExpired([NODE, '--version'], 10)))

    def test_probe_is_bounded_and_nested_suite_environment_preserved(self):
        error, calls, _ = self.invoke()
        self.assertIsNone(error)
        self.assertEqual(calls[0][0], [NODE, '--version'])
        probe = calls[0][1]
        self.assertGreater(probe['timeout'], 0)
        self.assertLessEqual(probe['timeout'], 10)
        self.assertIs(probe['check'], True)
        self.assertIs(probe['text'], True)
        self.assertTrue(probe.get('capture_output') is True or probe.get('stdout') == subprocess.PIPE)
        for _, kwargs in calls[1:]:
            self.assertNotIn('NODE_TEST_CONTEXT', kwargs['env'])
            self.assertEqual(kwargs['env']['ATLAS_TEST_MARKER'], 'keep')


    def test_non_ascii_version_digits_reject_before_suites(self):
        for version in ['v\u0661\u0668.\u0660.\u0660', 'v\uff11\uff18.\uff10.\uff10']:
            with self.subTest(version=version):
                self.assert_rejected(*self.invoke(version))


if __name__ == '__main__':
    unittest.main()
