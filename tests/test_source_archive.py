"""Release archives retain repository configuration and reviewed source bytes."""
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('source_archive_check', Path(__file__).resolve().parents[1] / 'scripts/check_source_archive.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def bundle(tmp_path, *, omit=False, changed=False, duplicate=False, symlink=False):
    files = {'.gitattributes': b'* text=auto eol=lf\n', '.github/workflows/test.yml': b'name: Test\n'}
    policy = {'version': 1, 'files': [{'path': p, 'sha256': hashlib.sha256(b).hexdigest()} for p, b in files.items()]}
    files['export-policy.json'] = json.dumps(policy).encode()
    if omit:
        del files['.gitattributes']
    if changed:
        files['.gitattributes'] = b'* text=auto eol=crlf\n'
    path = tmp_path / 'source.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        for name, data in files.items():
            member = tarfile.TarInfo('package/' + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
            if duplicate and name == '.gitattributes':
                archive.addfile(member, io.BytesIO(data))
        if symlink:
            member = tarfile.TarInfo('package/link')
            member.type = tarfile.SYMTYPE
            member.linkname = '.gitattributes'
            archive.addfile(member)
    return path


def test_source_archive_retains_reviewed_hidden_files(tmp_path):
    assert module.check_source_archive(bundle(tmp_path)) == 2


@pytest.mark.parametrize(('option', 'message'), [
    ('omit', 'missing from source archive'),
    ('changed', 'differs in source archive'),
    ('duplicate', 'Duplicate source archive file'),
    ('symlink', 'regular files'),
])
def test_source_archive_rejects_incomplete_or_ambiguous_contents(tmp_path, option, message):
    with pytest.raises(ValueError, match=message):
        module.check_source_archive(bundle(tmp_path, **{option: True}))


@pytest.mark.parametrize('name,payload', [
    ('docs/local-note.md', b'unreviewed'),
    ('src/codex_surface_atlas.egg-info/local-note.txt', b'unreviewed'),
    ('setup.cfg', b'[tool]\nprivate = unreviewed\n'),
    ('unused-directory/', None),
])
def test_source_archive_rejects_unreviewed_extras(tmp_path, name, payload):
    clean = bundle(tmp_path)
    modified = tmp_path / 'modified.tar.gz'
    with tarfile.open(clean) as source, tarfile.open(modified, 'w:gz') as archive:
        for member in source.getmembers():
            archive.addfile(member, source.extractfile(member))
        member = tarfile.TarInfo('package/' + name)
        if payload is None:
            member.type = tarfile.DIRTYPE
            archive.addfile(member)
        else:
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    with pytest.raises(ValueError):
        module.check_source_archive(modified)
