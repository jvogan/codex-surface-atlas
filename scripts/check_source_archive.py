#!/usr/bin/env python3
"""Check that a source archive retains every reviewed file and its exact bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath


def check_source_archive(path: Path) -> int:
    with tarfile.open(path, 'r:*') as archive:
        files = {}
        roots = set()
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or '\\' in member.name:
                raise ValueError('Source archive contains an unsafe entry name.')
            if not name.parts:
                raise ValueError('Source archive contains an empty entry name.')
            roots.add(name.parts[0])
            if member.isdir():
                continue
            if not member.isfile() or len(name.parts) < 2:
                raise ValueError('Source archive entries must be regular files under one root directory.')
            relative = PurePosixPath(*name.parts[1:]).as_posix()
            if relative in files:
                raise ValueError(f'Duplicate source archive file: {relative}')
            files[relative] = member
        if len(roots) != 1 or 'export-policy.json' not in files:
            raise ValueError('Source archive needs one root directory containing export-policy.json.')
        policy = json.loads(archive.extractfile(files['export-policy.json']).read())
        if not isinstance(policy, dict) or policy.get('version') != 1 or not isinstance(policy.get('files'), list) or not policy['files']:
            raise ValueError('Source archive needs a nonempty version 1 export policy.')
        reviewed = set()
        for entry in policy['files']:
            if not isinstance(entry, dict) or not isinstance(entry.get('path'), str) or not isinstance(entry.get('sha256'), str):
                raise ValueError('Invalid reviewed-file entry in source archive policy.')
            name = entry['path']
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
    return len(reviewed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    try:
        count = check_source_archive(args.archive)
    except (ValueError, OSError, tarfile.TarError) as exc:
        print(f'Source archive check failed: {exc}')
        return 1
    print(f'Source archive check passed: {count} reviewed files retain their exact bytes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
