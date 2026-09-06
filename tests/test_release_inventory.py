"""Build real distributions to guard against setuptools glob leakage."""
from __future__ import annotations

import hashlib
import base64
import csv
import io
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
description = "Synthetic distribution verification fixture"
readme = "README.md"
requires-python = ">=3.10"
dependencies = []
license = "MIT"
license-files = ["LICENSE", "NOTICE.md"]
[project.optional-dependencies]
test = ["pytest>=8", "tomli>=2; python_version < '3.11'"]
[project.scripts]
surface-atlas = "surface_atlas.cli:main"
[tool.setuptools.packages.find]
where = ["src"]
[tool.setuptools.package-data]
surface_atlas = ["assets/report/*.js"]
[tool.setuptools.data-files]
"share/codex-surface-atlas/schemas/v0.1" = ["schemas/v0.1/*.json"]
''',
        'LICENSE': 'MIT license fixture\n',
        'README.md': '# Synthetic distribution fixture\n\nNo research evidence.\n',
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
    assert SOURCE.check_source_archive(archive, policy) == 9
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


def append_metadata_header(payload, header):
    """Insert an attack header using the real metadata's line endings."""
    newline = b'\r\n' if b'\r\n' in payload else b'\n'
    headers, separator, body = payload.partition(newline + newline)
    assert separator, 'metadata fixture needs a header/body separator'
    return headers + newline + header + separator + body


def rewrite_wheel_with_recomputed_record(wheel, destination, mutate):
    """Model an adversary who can rewrite both payload and every RECORD hash."""
    with ZipFile(wheel) as original:
        content = {name: original.read(name) for name in original.namelist()}
    mutate(content)
    record = next(name for name in content if name.endswith('/RECORD'))
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    for name, payload in sorted(content.items()):
        if name != record:
            digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b'=').decode('ascii')
            writer.writerow([name, 'sha256=' + digest, str(len(payload))])
    writer.writerow([record, '', ''])
    content[record] = stream.getvalue().encode('utf-8')
    with ZipFile(destination, 'w') as bundle:
        for name, payload in content.items():
            bundle.writestr(name, payload)


@pytest.mark.parametrize('mutation', [
    'dependency', 'dependency_url', 'unconditional_extra_dependency', 'identity',
    'version', 'requires_python', 'extra', 'unknown_header', 'duplicate_header',
    'dynamic_dependency', 'metadata_version', 'description', 'console_target',
    'console_added', 'entrypoint_group', 'entrypoint_defaults', 'entrypoint_comment',
    'entrypoint_section_suffix', 'purelib', 'wheel_tag',
    'wheel_build', 'wheel_generator', 'wheel_body', 'top_level', 'missing_wheel',
    'missing_entrypoints', 'metadata_directory',
])
def test_generated_metadata_tampering_rejected_even_with_recomputed_record(project, mutation):
    _, wheel = build(project)
    def mutate(content):
        before = dict(content)
        metadata = next(name for name in content if name.endswith('/METADATA'))
        prefix = metadata.rsplit('/', 1)[0]
        def header(line):
            content[metadata] = append_metadata_header(content[metadata], line)
        if mutation == 'dependency':
            header(b'Requires-Dist: injected-package>=1')
        elif mutation == 'dependency_url':
            header(b'Requires-Dist: injected-package @ https://example.invalid/payload.whl')
        elif mutation == 'unconditional_extra_dependency':
            content[metadata] = content[metadata].replace(b'pytest>=8; extra == "test"', b'pytest>=8')
        elif mutation == 'identity':
            content[metadata] = content[metadata].replace(b'Name: codex-surface-atlas', b'Name: unrelated-package')
        elif mutation == 'version':
            content[metadata] = content[metadata].replace(b'Version: 0.1.0', b'Version: 999.0')
        elif mutation == 'requires_python':
            content[metadata] = content[metadata].replace(b'Requires-Python: >=3.10', b'Requires-Python: <3')
        elif mutation == 'extra':
            header(b'Provides-Extra: injected')
        elif mutation == 'unknown_header':
            header(b'Obsoletes-Dist: another-package')
        elif mutation == 'duplicate_header':
            header(b'Name: codex-surface-atlas')
        elif mutation == 'dynamic_dependency':
            header(b'Dynamic: requires-dist')
        elif mutation == 'metadata_version':
            content[metadata] = content[metadata].replace(b'Metadata-Version: 2.4', b'Metadata-Version: 9.9')
        elif mutation == 'description':
            content[metadata] += b'Unreviewed metadata description\n'
        elif mutation == 'console_target':
            content[prefix + '/entry_points.txt'] = b'[console_scripts]\nsurface-atlas = surface_atlas.cli:injected\n'
        elif mutation == 'console_added':
            content[prefix + '/entry_points.txt'] += b'injected = surface_atlas.cli:main\n'
        elif mutation == 'entrypoint_group':
            content[prefix + '/entry_points.txt'] += b'\n[injected.plugins]\nplugin = surface_atlas.cli:main\n'
        elif mutation == 'entrypoint_defaults':
            content[prefix + '/entry_points.txt'] = b'[DEFAULT]\ninjected = payload:main\n' + content[prefix + '/entry_points.txt']
        elif mutation == 'entrypoint_comment':
            content[prefix + '/entry_points.txt'] += b'# Unreviewed private annotation\n'
        elif mutation == 'entrypoint_section_suffix':
            content[prefix + '/entry_points.txt'] = content[prefix + '/entry_points.txt'].replace(b'[console_scripts]', b'[console_scripts] Unreviewed annotation')
        elif mutation == 'purelib':
            content[prefix + '/WHEEL'] = content[prefix + '/WHEEL'].replace(b'Root-Is-Purelib: true', b'Root-Is-Purelib: false')
        elif mutation == 'wheel_tag':
            content[prefix + '/WHEEL'] = content[prefix + '/WHEEL'].replace(b'Tag: py3-none-any', b'Tag: cp310-cp310-any')
        elif mutation == 'wheel_build':
            content[prefix + '/WHEEL'] += b'Build: 999\n'
        elif mutation == 'wheel_generator':
            content[prefix + '/WHEEL'] = content[prefix + '/WHEEL'].replace(b')\n', b'+private-note)\n')
        elif mutation == 'wheel_body':
            content[prefix + '/WHEEL'] += b'\nUnreviewed wheel data\n'
        elif mutation == 'top_level':
            content[prefix + '/top_level.txt'] += b'injected\n'
        elif mutation == 'missing_wheel':
            del content[prefix + '/WHEEL']
        elif mutation == 'missing_entrypoints':
            del content[prefix + '/entry_points.txt']
        elif mutation == 'metadata_directory':
            for name in list(content):
                if name.startswith(prefix + '/'):
                    content[name.replace(prefix, 'codex_surface_atlas-999.0.dist-info', 1)] = content.pop(name)
        assert content != before, 'tampering fixture did not change the wheel'
    destination = project / 'tampered.whl'
    rewrite_wheel_with_recomputed_record(wheel, destination, mutate)
    with pytest.raises(WHEEL.DistributionCheckError):
        WHEEL.check_wheel_inventory(destination, project / 'export-policy.json')


@pytest.mark.parametrize('source', ['pyproject.toml', 'README.md'])
def test_generated_metadata_authority_requires_reviewed_source_hash(project, source):
    _, wheel = build(project)
    path = project / source
    path.write_bytes(path.read_bytes() + b'\n# Unreviewed local change\n')
    with pytest.raises(WHEEL.DistributionCheckError, match='metadata source differs from review policy'):
        WHEEL.check_wheel_inventory(wheel, project / 'export-policy.json')


def test_generated_metadata_authority_requires_readme_in_policy(project):
    _, wheel = build(project)
    policy = project / 'export-policy.json'
    data = json.loads(policy.read_text())
    data['files'] = [entry for entry in data['files'] if entry['path'] != 'README.md']
    policy.write_text(json.dumps(data))
    with pytest.raises(WHEEL.DistributionCheckError, match='missing metadata source: README.md'):
        WHEEL.check_wheel_inventory(wheel, policy)


def test_clean_recomputed_record_does_not_change_acceptance(project):
    _, wheel = build(project)
    destination = project / 'repacked.whl'
    rewrite_wheel_with_recomputed_record(wheel, destination, lambda content: None)
    assert WHEEL.check_wheel_inventory(destination, project / 'export-policy.json') == 5
