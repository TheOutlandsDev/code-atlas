"""Negative controls for the real-process synthetic setup/scanner workflow."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('code_atlas_setup_check', ROOT / 'tools/check_setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupSmokeControls(unittest.TestCase):
    def test_scanner_that_does_not_publish_a_catalog_fails(self):
        files = setup.runtime_files()
        files['tools/scan.py'] = b'# Deliberately broken synthetic scanner: exits without scanning.\n'
        with self.assertRaises(FileNotFoundError):
            setup.smoke(files)

    def test_scanner_that_modifies_source_fails_preservation_check(self):
        files = setup.runtime_files()
        files['tools/scan.py'] += b'\nroot = Path(json.loads((Path(os.environ["CODE_ATLAS_HOME"]) / "policy.json").read_text())["bases"][0])\n(root / "python-demo/main.py").write_text("# changed by deliberately broken synthetic scanner\\n")\n'
        with self.assertRaisesRegex(ValueError, 'Scanner changed a synthetic source file'):
            setup.smoke(files)

    def test_scanner_that_keeps_a_stale_catalog_fails_refresh_check(self):
        files = setup.runtime_files()
        files['tools/scan.py'] = (b'import os, sys\nfrom pathlib import Path\n'
                                  b'if (Path(os.environ["CODE_ATLAS_HOME"]) / "state/catalog.json").exists():\n'
                                  b'    sys.exit(0)\n' + files['tools/scan.py'])
        with self.assertRaisesRegex(ValueError, 'Refresh missed newly created project'):
            setup.smoke(files)


if __name__ == '__main__':
    unittest.main()
