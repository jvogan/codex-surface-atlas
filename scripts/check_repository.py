#!/usr/bin/env python3
"""Verify that Git tracks exactly the reviewed source files and bytes."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from surface_atlas.export import ExportError, check_repository, load_policy


def verify_tracked_source(root: Path) -> int:
    root = root.resolve()
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=root,
                         check=True, capture_output=True, text=True).stdout.strip()
    if Path(top).resolve() != root:
        raise ValueError('Run this check at the repository root.')
    policy_path = root / 'export-policy.json'
    policy = load_policy(policy_path)
    entries = subprocess.run(['git', 'ls-files', '--stage', '-z'], cwd=root,
                             check=True, capture_output=True).stdout.split(b'\0')
    tracked = set()
    blobs = {}
    for entry in filter(None, entries):
        metadata, path = entry.split(b'\t', 1)
        mode, oid, stage = metadata.split()
        name = path.decode('utf-8')
        if mode not in (b'100644', b'100755') or stage != b'0':
            raise ValueError(f'Non-regular or conflicted tracked entry: {name}')
        tracked.add(name)
        blobs[name] = oid.decode('ascii')
    expected = {entry.path for entry in policy.files} | {'export-policy.json'}
    extra, missing = tracked - expected, expected - tracked
    if extra or missing:
        details = []
        if extra:
            details.append('Not in export policy: ' + ', '.join(sorted(extra)))
        if missing:
            details.append('Not tracked: ' + ', '.join(sorted(missing)))
        raise ValueError('\n'.join(details))
    # The worktree scanner must inspect the same bytes that Git will publish.
    diff = subprocess.run(['git', 'diff', '--quiet', '--no-ext-diff', '--'], cwd=root)
    if diff.returncode:
        raise ValueError('Tracked files differ from the index; review and stage the intended bytes first.')
    for name, oid in blobs.items():
        staged = subprocess.run(['git', 'cat-file', 'blob', oid], cwd=root,
                                check=True, capture_output=True).stdout
        if staged != (root / name).read_bytes():
            raise ValueError(f'Tracked bytes differ from working file: {name}')
    reports = [check_repository(root, policy)]
    # A policy cannot pin itself, but its contents still need the text checks.
    reports.append(check_repository(root, {
        'version': 1, 'limits': {'max_files': 1, 'max_file_bytes': 1000000, 'max_total_bytes': 2000000},
        'files': [{'path': 'export-policy.json', 'kind': 'json',
        'sha256': hashlib.sha256(policy_path.read_bytes()).hexdigest()}],
    }))
    for report in reports:
        if not report.ok:
            raise ValueError('\n'.join(f'{f.code}: {f.path}: {f.message}' for f in report.findings))
    return len(tracked)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path, default=Path('.'))
    args = parser.parse_args()
    try:
        count = verify_tracked_source(args.directory)
    except (ExportError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Repository check failed: {exc}')
        return 1
    print(f'Repository check passed: {count} tracked files match the reviewed policy.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
