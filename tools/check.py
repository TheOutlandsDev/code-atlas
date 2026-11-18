#!/usr/bin/env python3
"""Run the public offline synthetic test suites with no project discovery."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    node = shutil.which('node')
    if not node:
        sys.exit('Node.js >=18 is required for offline JavaScript tests')

    # Probe the selected Node executable with --version
    try:
        result = subprocess.run(
            [node, '--version'],
            cwd=ROOT,
            check=True,
            timeout=10,
            text=True,
            capture_output=True
        )
        version_output = result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, UnicodeError):
        sys.exit('Node.js >=18 is required for offline JavaScript tests')

    # Validate version output format
    match = re.match(r'^v([0-9]+)\.([0-9]+)\.([0-9]+)$', version_output)
    if not match or int(match.group(1)) < 18:
        sys.exit('Node.js >=18 is required for offline JavaScript tests')

    env = os.environ.copy()
    # Nested Node test runners may suppress file-level test registration.
    env.pop('NODE_TEST_CONTEXT', None)
    commands = [[sys.executable, '-I', '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], [node, 'extension/tests/core.test.cjs'], [node, 'extension/tests/activation.test.cjs'], [node, 'extension/media/ui.test.cjs'], [sys.executable, '-I', '-B', 'tools/check_release.py']]
    for command in commands:
        subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=60)
    subprocess.run([sys.executable, '-I', '-B', 'tools/check_setup.py'],
                   cwd=ROOT, env=env, check=True, timeout=60)
    print('Public synthetic suites passed. These do not run any external project tests.')


if __name__ == '__main__':
    main()
