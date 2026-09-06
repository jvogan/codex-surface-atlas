"""Generated sdist metadata is checked against trusted source inputs too."""
from __future__ import annotations

import io
import json
import tarfile

import pytest

# Reuse the actual build fixture so source and wheel checks see the same backend
# output, including conditional requirements. No mocked metadata serialization.
from test_release_inventory import SOURCE, build, project  # noqa: F401


@pytest.mark.parametrize('mutation', [
    'root_dependency', 'egg_unknown_header', 'both_readme', 'entry_point',
    'entry_comment', 'requires', 'requires_comment', 'dependency_links',
    'top_level', 'sources_traversal', 'sources_comment', 'sources_missing',
    'sources_duplicate', 'missing_metadata',
])
def test_source_generated_metadata_cannot_carry_unreviewed_content(project, mutation):
    archive_path, _ = build(project)
    with tarfile.open(archive_path) as archive:
        files = {member.name: archive.extractfile(member).read()
                 for member in archive.getmembers() if member.isfile()}
    root = next(iter(files)).split('/', 1)[0] + '/'
    egg = root + 'src/codex_surface_atlas.egg-info/'
    if mutation == 'root_dependency':
        files[root + 'PKG-INFO'] = files[root + 'PKG-INFO'].replace(b'\n\n', b'\nRequires-Dist: unreviewed-dependency>=1\n\n', 1)
    elif mutation == 'egg_unknown_header':
        files[egg + 'PKG-INFO'] = files[egg + 'PKG-INFO'].replace(b'\n\n', b'\nX-Unreviewed: synthetic private note\n\n', 1)
    elif mutation == 'both_readme':
        for name in (root + 'PKG-INFO', egg + 'PKG-INFO'):
            files[name] += b'Unreviewed synthetic note.\n'
    elif mutation == 'entry_point':
        files[egg + 'entry_points.txt'] = b'[console_scripts]\nsurface-atlas = surface_atlas.cli:unreviewed\n'
    elif mutation == 'entry_comment':
        files[egg + 'entry_points.txt'] += b'# Unreviewed synthetic private note.\n'
    elif mutation == 'requires':
        files[egg + 'requires.txt'] += b'unreviewed-dependency>=1\n'
    elif mutation == 'requires_comment':
        files[egg + 'requires.txt'] += b'# Unreviewed synthetic private note.\n'
    elif mutation == 'dependency_links':
        files[egg + 'dependency_links.txt'] = b'https://example.invalid/unreviewed\n'
    elif mutation == 'top_level':
        files[egg + 'top_level.txt'] += b'unreviewed_package\n'
    elif mutation == 'sources_traversal':
        files[egg + 'SOURCES.txt'] += b'../unreviewed.txt\n'
    elif mutation == 'sources_comment':
        files[egg + 'SOURCES.txt'] += b'# Unreviewed synthetic private note.\n'
    elif mutation == 'sources_missing':
        files[egg + 'SOURCES.txt'] = files[egg + 'SOURCES.txt'].replace(b'README.md\n', b'')
    elif mutation == 'sources_duplicate':
        files[egg + 'SOURCES.txt'] += b'README.md\n'
    elif mutation == 'missing_metadata':
        del files[root + 'PKG-INFO']
    modified = project / 'modified.tar.gz'
    with tarfile.open(modified, 'w:gz') as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name); member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError):
        SOURCE.check_source_archive(modified, project / 'export-policy.json')


def test_source_metadata_requires_separate_trusted_review_policy(project):
    archive, _ = build(project)
    with pytest.raises(ValueError, match='explicit trusted review policy'):
        SOURCE.check_source_archive(archive)


def test_source_metadata_does_not_trust_changed_checkout_configuration(project):
    archive, _ = build(project)
    config = project / 'pyproject.toml'
    config.write_text(config.read_text().replace('version = "0.1.0"', 'version = "0.2.0"'))
    with pytest.raises(ValueError, match='trusted metadata source differs'):
        SOURCE.check_source_archive(archive, project / 'export-policy.json')


def test_clean_source_metadata_matches_trusted_project_and_conditional_requirements(project):
    archive, _ = build(project)
    policy = project / 'export-policy.json'
    assert SOURCE.check_source_archive(archive, policy) == len(json.loads(policy.read_text())['files'])
