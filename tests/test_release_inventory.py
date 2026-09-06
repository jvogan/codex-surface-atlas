"""Build real distributions to guard against setuptools glob leakage."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOURCE = load('check_source_archive')
WHEEL = load('check_distribution')


@pytest.fixture
def project(tmp_path):
    files = {
        'pyproject.toml': '''[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"
[project]
name = "codex-surface-atlas"
version = "0.1.0"
license = "MIT"
license-files = ["LICENSE", "NOTICE.md"]
[tool.setuptools.packages.find]
where = ["src"]
[tool.setuptools.package-data]
surface_atlas = ["assets/report/*.js"]
[tool.setuptools.data-files]
"share/codex-surface-atlas/schemas/v0.1" = ["schemas/v0.1/*.json"]
''',
        'LICENSE': 'MIT license fixture\n',
        'NOTICE.md': 'Synthetic test material\n',
        'docs/guide.md': 'Reviewed guide\n',
        'src/surface_atlas/__init__.py': '',
        'src/surface_atlas/assets/report/main.js': '"use strict";\n',
        'schemas/v0.1/atlas-plan.schema.json': '{}\n',
        'MANIFEST.in': (ROOT / 'MANIFEST.in').read_text(),
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    policy = {'version': 1, 'files': [
        {'path': name, 'sha256': hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()}
        for name in files
    ]}
    (tmp_path / 'export-policy.json').write_text(json.dumps(policy), encoding='utf-8')
    return tmp_path


def build(project):
    result = subprocess.run([sys.executable, '-m', 'build', '--no-isolation'],
                            cwd=project, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return next((project / 'dist').glob('*.tar.gz')), next((project / 'dist').glob('*.whl'))


def test_clean_real_build_retains_reviewed_inventory(project):
    archive, wheel = build(project)
    policy = project / 'export-policy.json'
    assert SOURCE.check_source_archive(archive, policy) == 8
    assert WHEEL.check_wheel_inventory(wheel, policy) == 5


def test_packaging_globs_cannot_admit_unreviewed_local_files(project):
    # These are absent from the reviewed policy, as local untracked files would be.
    (project / 'docs/local-note.md').write_text('Unreviewed local note\n')
    (project / 'src/surface_atlas/assets/report/local.js').write_text('unreviewed();\n')
    archive, wheel = build(project)
    policy = project / 'export-policy.json'
    with pytest.raises(ValueError, match='Unreviewed source archive files:.*docs/local-note.md'):
        SOURCE.check_source_archive(archive, policy)
    with pytest.raises(WHEEL.DistributionCheckError, match='unreviewed wheel files:.*local.js'):
        WHEEL.check_wheel_inventory(wheel, policy)


@pytest.mark.parametrize('mutation', ['payload', 'record', 'extra_metadata', 'missing_schema', 'duplicate'])
def test_wheel_inventory_rejects_tampering(project, mutation):
    _, wheel = build(project)
    with ZipFile(wheel) as original:
        content = {name: original.read(name) for name in original.namelist()}
    resource = 'surface_atlas/assets/report/main.js'
    if mutation == 'payload':
        content[resource] = b'changed();'
    elif mutation == 'record':
        record = next(name for name in content if name.endswith('/RECORD'))
        content[record] = b''
    elif mutation == 'extra_metadata':
        metadata = next(name for name in content if name.endswith('/METADATA'))
        content[metadata.rsplit('/', 1)[0] + '/local-note.txt'] = b'unreviewed'
    elif mutation == 'missing_schema':
        del content[next(name for name in content if name.endswith('atlas-plan.schema.json'))]
    modified = project / 'modified.whl'
    with ZipFile(modified, 'w') as bundle:
        for name, payload in content.items():
            bundle.writestr(name, payload)
        if mutation == 'duplicate':
            with pytest.warns(UserWarning, match='Duplicate name'):
                bundle.writestr(resource, content[resource])
    with pytest.raises(WHEEL.DistributionCheckError):
        WHEEL.check_wheel_inventory(modified, project / 'export-policy.json')


def test_source_archive_requires_trusted_policy(project):
    archive, _ = build(project)
    trusted = project / 'export-policy.json'
    trusted.write_text('{}')
    with pytest.raises(ValueError, match='trusted review policy'):
        SOURCE.check_source_archive(archive, trusted)
