import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('scan', ROOT / 'tools/scan.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)

class TestExtensionCase(unittest.TestCase):
    def test_uppercase_extensions(self):
        raw = json.loads((ROOT / 'examples/policy.example.json').read_text())
        raw['bases'] = []
        raw['seedRoots'] = []
        policy = scan.Policy(raw)
        # Test that uppercase extensions are recognized
        self.assertEqual(policy.language('MAIN.PY'), 'Python')
        self.assertEqual(policy.language('settings.JsOn'), 'JSON')

    def test_lowercase_extensions(self):
        raw = json.loads((ROOT / 'examples/policy.example.json').read_text())
        raw['bases'] = []
        raw['seedRoots'] = []
        policy = scan.Policy(raw)
        # Test that lowercase extensions still work
        self.assertEqual(policy.language('main.py'), 'Python')
        self.assertEqual(policy.language('settings.json'), 'JSON')

    def test_custom_manifest_precedence(self):
        raw = json.loads((ROOT / 'examples/policy.example.json').read_text())
        raw['bases'] = []
        raw['seedRoots'] = []
        raw['manifestNames']['Exact.PY'] = 'Custom manifest'
        policy = scan.Policy(raw)
        # Test that custom manifest names are case sensitive and work
        self.assertEqual(policy.language('Exact.PY'), 'Custom manifest')
        self.assertEqual(policy.language('exact.py'), 'Python')

    def test_exact_custom_suffix_beats_normalized_fallback(self):
        raw = json.loads((ROOT / 'examples/policy.example.json').read_text())
        raw['codeExtensions']['.PY'] = 'Custom Python'
        policy = scan.Policy(raw)
        self.assertEqual(policy.language('legacy.PY'), 'Custom Python')
        self.assertEqual(policy.language('mixed.pY'), 'Python')

if __name__ == '__main__':
    unittest.main()
