#!/usr/bin/env python3
"""Check that a source archive retains every reviewed file and its exact bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath


# Only setuptools' known generated files may escape the reviewed inventory.
GENERATED_FILES = {'PKG-INFO', 'setup.cfg'} | {
    'src/codex_surface_atlas.egg-info/' + name
    for name in ('PKG-INFO', 'SOURCES.txt', 'dependency_links.txt',
                 'entry_points.txt', 'requires.txt', 'top_level.txt')
}


def check_source_archive(path: Path, policy_path: Path | None = None) -> int:
    with tarfile.open(path, 'r:*') as archive:
        files = {}
        roots = set()
        directories = set()
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or '\\' in member.name
                    or name.as_posix() != member.name.rstrip('/')
                    or any(':' in part for part in name.parts)):
                raise ValueError('Source archive contains an unsafe entry name.')
            if not name.parts:
                raise ValueError('Source archive contains an empty entry name.')
            roots.add(name.parts[0])
            if member.isdir():
                directories.add(PurePosixPath(*name.parts[1:]).as_posix())
                continue
            if not member.isfile() or len(name.parts) < 2:
                raise ValueError('Source archive entries must be regular files under one root directory.')
            relative = PurePosixPath(*name.parts[1:]).as_posix()
            if relative in files:
                raise ValueError(f'Duplicate source archive file: {relative}')
            files[relative] = member
        if len(roots) != 1 or 'export-policy.json' not in files:
            raise ValueError('Source archive needs one root directory containing export-policy.json.')
        policy_bytes = archive.extractfile(files['export-policy.json']).read()
        if policy_path is not None and policy_bytes != policy_path.read_bytes():
            raise ValueError('Source archive policy differs from the trusted review policy.')
        policy = json.loads(policy_bytes)
        if not isinstance(policy, dict) or policy.get('version') != 1 or not isinstance(policy.get('files'), list) or not policy['files']:
            raise ValueError('Source archive needs a nonempty version 1 export policy.')
        reviewed = set()
        for entry in policy['files']:
            if not isinstance(entry, dict) or not isinstance(entry.get('path'), str) or not isinstance(entry.get('sha256'), str):
                raise ValueError('Invalid reviewed-file entry in source archive policy.')
            name = entry['path']
            parsed = PurePosixPath(name)
            if (not name or parsed.is_absolute() or '..' in parsed.parts
                    or '\\' in name or parsed.as_posix() != name
                    or name == 'export-policy.json' or name in GENERATED_FILES):
                raise ValueError(f'Invalid reviewed-file path: {name}')
            if name in reviewed:
                raise ValueError(f'Duplicate reviewed-file entry: {name}')
            reviewed.add(name)
            if name not in files:
                raise ValueError(f'Reviewed file missing from source archive: {name}')
            payload = archive.extractfile(files[name])
            digest = hashlib.sha256()
            for chunk in iter(lambda: payload.read(1024 * 1024), b''):
                digest.update(chunk)
            if digest.hexdigest() != entry['sha256']:
                raise ValueError(f'Reviewed file differs in source archive: {name}')
        if 'setup.cfg' in files:
            generated_config = archive.extractfile(files['setup.cfg']).read().replace(b'\r\n', b'\n')
            if generated_config != b'[egg_info]\ntag_build = \ntag_date = 0\n\n':
                raise ValueError('Source archive setup.cfg is not the expected generated configuration.')
        allowed_directories = {'.'}
        for name in files:
            allowed_directories.update(parent.as_posix() for parent in PurePosixPath(name).parents)
        if directories - allowed_directories:
            raise ValueError('Unreviewed source archive directories: '
                             + ', '.join(sorted(directories - allowed_directories)))
        extra = set(files) - reviewed - {'export-policy.json'} - GENERATED_FILES
        if extra:
            raise ValueError('Unreviewed source archive files: ' + ', '.join(sorted(extra)))
    return len(reviewed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--policy', type=Path, default=Path(__file__).resolve().parents[1] / 'export-policy.json')
    args = parser.parse_args()
    try:
        count = check_source_archive(args.archive, args.policy)
    except (ValueError, OSError, tarfile.TarError) as exc:
        print(f'Source archive check failed: {exc}')
        return 1
    print(f'Source archive check passed: {count} reviewed files retain their exact bytes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
