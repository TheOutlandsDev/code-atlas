#!/usr/bin/env python3
"""Create private local configuration from explicit roots; never overwrite a setup."""
import argparse
import json
import os
from pathlib import Path
import stat


def canonical(value, directory=True):
    path = Path(value)
    if not path.is_absolute() or str(path) != value or any((ord(c) < 32 or ord(c) == 127) for c in value) or '\\' in value:
        raise ValueError('Use normalized absolute paths')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError('Symlink paths are not supported')
    if directory and not path.is_dir():
        raise ValueError('Root must be an existing directory')
    return path


def configure(roots, home):
    target = canonical(home, False)
    if target.exists():
        raise ValueError('CODE_ATLAS_HOME already exists; no files overwritten')
    canonical(str(target.parent))
    broad = {'/', '/home', '/etc', '/proc', '/sys', '/dev', '/var', '/usr', '/opt', '/srv', '/tmp', str(Path.home())}
    roots = list(dict.fromkeys(str(canonical(root)) for root in roots))
    if not roots or any(root in broad for root in roots):
        raise ValueError('Choose explicit project directories or project parents')
    for root in roots:
        if str(target) == root or str(target).startswith(root + '/'):
            raise ValueError('Keep Atlas state outside configured source roots')
    template = Path(__file__).resolve().parent.parent / 'examples/policy.example.json'
    policy = json.loads(template.read_text())
    policy['bases'] = roots
    policy['seedRoots'] = roots
    policy['excludedPathPrefixes'] = [str(target)]
    os.mkdir(target, 0o700)
    try:
        os.mkdir(target / 'state', 0o700)
        for name, content in [('policy.json', policy), ('Atlas.code-workspace', {'folders': [], 'settings': {'files.autoSave': 'off', 'security.workspace.trust.enabled': True}})]:
            fd = os.open(target / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as out:
                json.dump(content, out, indent=2)
                out.write('\n')
    except Exception:
        # Preserve partial files for diagnosis. Never remove an owner's files.
        raise
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', required=True, help='Explicit canonical project directory or parent; repeatable')
    parser.add_argument('--home', default=os.environ.get('CODE_ATLAS_HOME', str(Path.home() / '.code-atlas')))
    args = parser.parse_args()
    try:
        configure(args.root, args.home)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    print('Local Atlas configuration created. Install the extension and open Atlas.code-workspace inside CODE_ATLAS_HOME.')


if __name__ == '__main__':
    main()
