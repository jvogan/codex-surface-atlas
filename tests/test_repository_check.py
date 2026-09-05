"""The source inventory check must cover what Git will publish."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('repository_check', Path(__file__).resolve().parents[1] / 'scripts/check_repository.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def source(tmp_path):
    git(tmp_path, 'init')
    content = b'Reviewed example.\n'
    (tmp_path / 'README.md').write_bytes(content)
    policy = {'version': 1, 'limits': {'max_files': 5, 'max_file_bytes': 10000, 'max_total_bytes': 20000},
              'files': [{'path': 'README.md', 'kind': 'text', 'sha256': hashlib.sha256(content).hexdigest()}]}
    (tmp_path / 'export-policy.json').write_text(json.dumps(policy))
    git(tmp_path, 'add', 'README.md', 'export-policy.json')
    return tmp_path


def test_exact_staged_source_passes_and_untracked_notes_are_not_published(source):
    (source / 'notes.txt').write_text('Local notes')
    assert checker.verify_tracked_source(source) == 2


def test_unreviewed_tracked_file_is_rejected(source):
    (source / 'extra.txt').write_text('Unexpected file')
    git(source, 'add', 'extra.txt')
    with pytest.raises(ValueError, match='Not in export policy: extra.txt'):
        checker.verify_tracked_source(source)


def test_missing_tracked_file_is_rejected(source):
    git(source, 'rm', '--cached', 'README.md')
    with pytest.raises(ValueError, match='Not tracked: README.md'):
        checker.verify_tracked_source(source)


def test_staged_edits_need_reviewed_hashes(source):
    (source / 'README.md').write_text('Changed content')
    git(source, 'add', 'README.md')
    with pytest.raises(ValueError, match='hash_mismatch'):
        checker.verify_tracked_source(source)


def test_unstaged_edits_are_rejected_even_if_git_assumes_unchanged(source):
    git(source, 'update-index', '--assume-unchanged', 'README.md')
    (source / 'README.md').write_text('Different working content')
    with pytest.raises(ValueError, match='Tracked bytes differ'):
        checker.verify_tracked_source(source)


def test_policy_text_is_scanned_even_though_it_cannot_pin_itself(source):
    path = source / 'export-policy.json'
    policy = json.loads(path.read_text())
    policy['deny_terms'] = ['api' + '_key=' + 'examplecredentialvalue']
    path.write_text(json.dumps(policy))
    git(source, 'add', 'export-policy.json')
    with pytest.raises(ValueError, match='credential_value'):
        checker.verify_tracked_source(source)
