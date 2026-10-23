#!/usr/bin/env python3
"""Bounded local source metadata scanner. Never imports or executes project code."""
import ast
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time


def canonical(path, directory=None):
    path = Path(path)
    if not path.is_absolute() or os.path.normpath(str(path)) != str(path) or '\\' in str(path) or any((ord(c) < 32 or ord(c) == 127) for c in str(path)):
        raise ValueError('Invalid absolute path')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('Symlink path excluded')
    info = path.stat()
    if directory is True and not stat.S_ISDIR(info.st_mode):
        raise ValueError('Directory required')
    if directory is False and not stat.S_ISREG(info.st_mode):
        raise ValueError('Regular file required')
    return info


def regular(path, maximum):
    path = Path(path)
    before = canonical(path, False)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or opened.st_size > maximum or not stat.S_ISREG(opened.st_mode) or os.path.realpath('/proc/self/fd/' + str(fd)) != str(path):
            raise ValueError('File identity or size rejected')
        current = canonical(path, False)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError('File identity changed')
        chunks = []
        total = 0
        while total <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            chunks.append(chunk)
        after = os.fstat(fd)
        if total > maximum or (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
            raise ValueError('File changed')
        return b''.join(chunks)
    finally:
        os.close(fd)


def inside(base, value):
    return value == base or value.startswith(base + '/')


class Policy:
    def __init__(self, raw):
        if raw.get('schemaVersion') != 1 or not isinstance(raw.get('bases'), list) or not isinstance(raw.get('seedRoots'), list):
            raise ValueError('Invalid policy')
        self.raw = raw
        self.bases = [str(Path(root)) for root in raw['bases']]
        if any(root == '/' or not root.startswith('/') or os.path.normpath(root) != root for root in self.bases):
            raise ValueError('Invalid base')
        self.names = set(item.lower() for item in raw['excludedDirectoryNames'])
        self.patterns = [re.compile(item, re.I) for item in raw['excludedDirectoryPatterns']]
        self.prefixes = raw['excludedPathPrefixes']
        self.extensions = raw['codeExtensions']
        self.manifests = raw['manifestNames']
        self.seeds = set(raw['seedRoots'])
        self.reviewed = {item['rootPath'] for item in raw.get('reviewedTests', [])}
        for seed in self.seeds:
            if not any(inside(base, seed) for base in self.bases):
                raise ValueError('Seed outside bases')

    def excluded(self, base, value):
        if not inside(base, value) or any(inside(prefix, value) for prefix in self.prefixes):
            return True
        return any(part.startswith('.') or part.lower() in self.names or any(pattern.search(part) for pattern in self.patterns) for part in Path(value).relative_to(base).parts)

    def language(self, name):
        return self.manifests.get(name) or self.extensions.get(Path(name).suffix)

    def limit(self, name, ceiling):
        value = self.raw.get(name, ceiling)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError('Invalid scan limit')
        return min(value, ceiling)


class Scanner:
    def __init__(self, policy):
        self.p = policy
        self.started = time.monotonic()
        self.max_seconds = policy.limit('maxSeconds', 20)
        self.max_dirs = policy.limit('maxDirectories', 10000)
        self.max_files = policy.limit('maxScanFiles', 50000)
        self.max_projects = policy.limit('maxProjects', 500)
        self.max_entries = policy.limit('maxDirectoryEntries', 5000)
        self.max_depth = policy.limit('maxDiscoveryDepth', 8)
        self.max_bytes = policy.limit('maxFileBytes', 524288)
        self.projects = {}
        self.dirs = self.files = self.denied = self.excluded = self.checked = self.errors = 0
        self.limited = False

    def budget(self):
        if time.monotonic() - self.started > self.max_seconds or self.dirs >= self.max_dirs or self.files >= self.max_files:
            self.limited = True
            return False
        return True

    def project(self, root):
        if root in self.projects:
            return self.projects[root]
        if len(self.projects) >= self.max_projects:
            self.limited = True
            return None
        row = {'id': 'p-' + hashlib.sha256(root.encode()).hexdigest()[:16], 'label': self.p.raw.get('seedLabels', {}).get(root, Path(root).name), 'rootPath': root, 'languages': [], 'primaryLanguage': 'Other', 'fileCount': 0, 'status': 'READ_ONLY_SOURCE', 'scanComplete': True, 'sampleFiles': [], 'sourceFingerprint': '', 'testStatus': 'REVIEWED_ISOLATED_TESTS' if root in self.p.reviewed else 'NOT_CONFIGURED', 'isolatedCopyState': 'NOT_CONFIGURED', 'validation': {'status': 'NOT_CHECKED', 'syntaxPassed': 0, 'syntaxErrors': 0, 'pending': 0, 'unsupported': 0, 'lastCheckedAtUtc': None}, '_languages': Counter(), '_stamps': []}
        self.projects[root] = row
        return row

    def entries(self, directory):
        before = canonical(directory, True)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(fd)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino) or os.path.realpath('/proc/self/fd/' + str(fd)) != directory:
                raise ValueError('Directory changed')
            current = canonical(directory, True)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError('Directory identity changed')
            result = []
            with os.scandir(fd) as entries:
                for entry in entries:
                    if len(result) >= self.max_entries:
                        self.limited = True
                        break
                    result.append((entry.name, entry.stat(follow_symlinks=False)))
            return sorted(result)
        finally:
            os.close(fd)

    def walk(self, base, directory, root, depth):
        if not self.budget():
            return
        self.dirs += 1
        try:
            entries = self.entries(directory)
        except (OSError, ValueError):
            self.denied += 1
            if directory == root:
                row = self.project(root)
                if row is not None:
                    row['status'] = 'UNREADABLE'
            return
        names = {name for name, _ in entries}
        if directory != root and (names.intersection(self.p.raw['projectMarkers']) or directory in self.p.seeds):
            root = directory
        row = self.project(root)
        if row is None:
            return
        for name, info in entries:
            if not self.budget():
                break
            file = directory + '/' + name
            if self.p.excluded(base, file) or stat.S_ISLNK(info.st_mode):
                self.excluded += 1
                continue
            if stat.S_ISDIR(info.st_mode):
                if depth < self.max_depth:
                    self.walk(base, file, root, depth + 1)
                else:
                    self.limited = True
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            self.files += 1
            language = self.p.language(name)
            if not language or info.st_size > self.max_bytes:
                continue
            rel = str(Path(file).relative_to(root))
            row['fileCount'] += 1
            row['_languages'][language] += 1
            row['_stamps'].append([rel, info.st_size, info.st_mtime_ns, info.st_ino])
            if len(row['sampleFiles']) < 20:
                row['sampleFiles'].append({'relativePath': rel, 'language': language})
            validation = row['validation']
            if language not in ('Python', 'JSON'):
                validation['unsupported'] += 1
                continue
            try:
                content = regular(file, self.max_bytes)
            except (OSError, ValueError):
                validation['pending'] += 1
                self.denied += 1
                continue
            try:
                if language == 'Python':
                    ast.parse(content, filename='<local-source>')
                else:
                    json.loads(content)
                validation['syntaxPassed'] += 1
            except (SyntaxError, UnicodeError, ValueError, RecursionError, MemoryError):
                validation['syntaxErrors'] += 1
                self.errors += 1
            self.checked += 1

    def run(self):
        bases = []
        for base in self.p.bases:
            count = len(self.projects)
            start_dirs = self.dirs
            self.walk(base, base, base, 0)
            bases.append({'path': base, 'status': 'LIMITED' if self.limited else 'SCANNED', 'visitedDirectories': self.dirs - start_dirs, 'projects': len(self.projects) - count, 'limitsHit': self.limited})
        generated = datetime.now(timezone.utc).isoformat()
        for row in self.projects.values():
            counts = row.pop('_languages')
            row['languages'] = sorted(counts)
            row['primaryLanguage'] = counts.most_common(1)[0][0] if counts else 'Other'
            row['sourceFingerprint'] = hashlib.sha256(json.dumps(row.pop('_stamps'), separators=(',', ':')).encode()).hexdigest()
            row['scanComplete'] = not self.limited and not self.denied and row['status'] == 'READ_ONLY_SOURCE'
            validation = row['validation']
            validation['status'] = 'STALE_UNREADABLE' if validation['pending'] else 'SYNTAX_ERROR' if validation['syntaxErrors'] else 'SYNTAX_PASS' if validation['syntaxPassed'] else 'NOT_CHECKED'
            validation['lastCheckedAtUtc'] = generated if validation['syntaxPassed'] + validation['syntaxErrors'] else None
        return {'schemaVersion': 1, 'generation': int(time.time() * 1000), 'generatedAtUtc': generated, 'projects': list(self.projects.values()), 'coverage': {'bases': bases, 'projectCount': len(self.projects), 'codeFiles': sum(row['fileCount'] for row in self.projects.values()), 'complete': not self.limited and not self.denied, 'limited': self.limited or bool(self.denied), 'unreadableDirectories': self.denied, 'excludedDirectories': self.excluded, 'scanBudgetExceeded': self.limited, 'durationMs': int((time.monotonic() - self.started) * 1000)}, 'validation': {'mode': 'static_only', 'supportedLanguages': ['Python', 'JSON'], 'checkedThisScan': self.checked, 'cacheEntries': 0, 'errors': self.errors, 'pending': sum(row['validation']['pending'] for row in self.projects.values())}}


def scan(home):
    home = Path(home)
    info = canonical(home, True)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('CODE_ATLAS_HOME must be owner-private')
    state = home / 'state'
    canonical(state, True)
    lock_fd = os.open(state / 'scan.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        policy = Policy(json.loads(regular(home / 'policy.json', 1048576)))
        result = Scanner(policy).run()
        target = state / ('catalog-' + secrets.token_hex(8) + '.tmp')
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(result, out, separators=(',', ':'))
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(target, state / 'catalog.json')
        return result
    finally:
        os.close(lock_fd)


if __name__ == '__main__':
    try:
        scan(os.environ.get('CODE_ATLAS_HOME', str(Path.home() / '.code-atlas')))
    except (ValueError, OSError, KeyError, TypeError):
        print('Local scan failed; check private configuration and explicit roots.', file=sys.stderr)
        sys.exit(2)
