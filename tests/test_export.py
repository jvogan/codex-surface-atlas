from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import surface_atlas.export as export_module

from surface_atlas.export import ExportError, PolicyError, check_repository, export_subset, load_policy


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _policy(path: str, content: bytes, *, kind: str = "json", **entry_extra: object) -> dict:
    entry = {"path": path, "sha256": _digest(content), "kind": kind, **entry_extra}
    return {
        "version": 1,
        "limits": {"max_files": 10, "max_file_bytes": 10_000, "max_total_bytes": 20_000},
        "deny_terms": [],
        "files": [entry],
    }


def _check_html(tmp_path: Path, text: str, *, deny_terms: list[str] | None = None):
    source = tmp_path / "source"
    source.mkdir()
    content = text.encode("utf-8")
    (source / "index.html").write_bytes(content)
    policy = _policy("index.html", content, kind="html")
    policy["deny_terms"] = deny_terms or []
    return check_repository(source, policy)


def test_safe_export_is_transactional_and_writes_sized_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b'{"title":"Synthetic example","summary":"No source records."}\n'
    (source / "example.json").write_bytes(content)
    policy = _policy("example.json", content)

    check = check_repository(source, policy)
    assert check.ok
    assert check.total_bytes == len(content)
    assert check.files[0].bytes == len(content)
    assert check.manifest_bytes > 0

    output = tmp_path / "public"
    result = export_subset(source, output, policy)
    assert result.ok
    assert (output / "example.json").read_bytes() == content
    manifest = json.loads((output / "surface-atlas-export.json").read_text())
    assert manifest["files"][0]["sha256"] == _digest(content)
    assert manifest["total_bytes"] == len(content)


def test_generated_style_html_is_checked_as_text(tmp_path: Path) -> None:
    markup = '''<!doctype html><html><head>
    <link rel="stylesheet" href="assets/report.css"><script defer src="assets/report.js"></script>
    <script type="application/json" id="atlas-data">{"records":[{"target_id":"T-EXAMPLE"}]}</script>
    </head><body><!-- reviewed example --><pre>{&quot;state&quot;: &quot;planned&quot;}</pre>
    <script>document.documentElement.dataset.ready = "true";</script></body></html>'''
    report = _check_html(tmp_path, markup)
    assert report.ok, report.findings
    assert report.files[0].kind == "html"


@pytest.mark.parametrize(
    ("markup", "code"),
    [
        ("<p>&#47;Users&#47;sample&#47;review.json</p>", "private_path"),
        ("<p>api&#95;key=syntheticcredentialvalue</p>", "credential_value"),
        ('<a href="file%3A%2F%2F%2FUsers%2Fsample%2Freview.json">file</a>', "private_path"),
        (r'<script type="application/json">{"api\u005fkey":"syntheticcredentialvalue"}</script>', "credential_field"),
        ('<pre>{&quot;case_id&quot;: &quot;CASE-EXAMPLE&quot;}</pre>', "case_identifier"),
    ],
)
def test_html_decoded_content_and_embedded_json_receive_existing_checks(
    tmp_path: Path, markup: str, code: str
) -> None:
    report = _check_html(tmp_path, markup)
    assert not report.ok
    assert code in {finding.code for finding in report.findings}


def test_html_decoded_text_receives_private_deny_terms(tmp_path: Path) -> None:
    report = _check_html(tmp_path, "<p>CASE&#45;ALPHA&#45;42</p>", deny_terms=["CASE-ALPHA-42"])
    assert not report.ok
    assert "deny_term" in {finding.code for finding in report.findings}


def test_malformed_embedded_json_stops_html_export(tmp_path: Path) -> None:
    report = _check_html(tmp_path, '<script type="application/json">{"records": [}</script>')
    assert not report.ok
    assert "invalid_html_json" in {finding.code for finding in report.findings}


def test_html_parse_error_does_not_echo_input(tmp_path: Path) -> None:
    marker = "PRIVATE-MARKER-FOR-ERROR"
    report = _check_html(tmp_path, f'<script type="application/json">{{"{marker}": true}}')
    finding = next(item for item in report.findings if item.code == "invalid_html")
    assert marker not in finding.message


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("model.cif", "data_example\n_entry.id example\n"),
        ("model.pdb", "HEADER    SYNTHETIC MODEL\nEND\n"),
        ("compound.sdf", "Synthetic compound\n  SurfaceAtlas\n\n$$$$\n"),
        ("sequence.fasta", ">synthetic_sequence\nACDEFG\n"),
        ("sequence.fa", ">synthetic_sequence\nACDEFG\n"),
        ("compounds.smi", "C M-EXAMPLE\n"),
        ("compounds.smiles", "C M-EXAMPLE\n"),
    ],
)
def test_reviewed_molecular_text_formats_receive_text_checks(
    tmp_path: Path, name: str, content: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payload = content.encode("utf-8")
    (source / name).write_bytes(payload)
    report = check_repository(source, _policy(name, payload, kind="molecular-text"))
    assert report.ok, report.findings
    assert report.files[0].review_exceptions == ()


def test_molecular_text_rejects_private_paths_and_invalid_utf8(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    private_content = b"HEADER /Users/example/private/model.pdb\n"
    (source / "private.pdb").write_bytes(private_content)
    private_report = check_repository(
        source, _policy("private.pdb", private_content, kind="molecular-text")
    )
    assert "private_path" in {finding.code for finding in private_report.findings}

    invalid_content = b"HEADER \xff\n"
    (source / "invalid.pdb").write_bytes(invalid_content)
    invalid_report = check_repository(
        source, _policy("invalid.pdb", invalid_content, kind="molecular-text")
    )
    assert "invalid_utf8" in {finding.code for finding in invalid_report.findings}


def test_molecular_text_receives_release_deny_terms(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b">CASE-ALPHA-42\nACDEFG\n"
    (source / "sequence.fasta").write_bytes(content)
    policy = _policy("sequence.fasta", content, kind="molecular-text")
    policy["deny_terms"] = ["CASE-ALPHA-42"]
    report = check_repository(source, policy)
    assert "deny_term" in {finding.code for finding in report.findings}


def test_tsv_uses_tab_delimiter_and_checks_sensitive_headers(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    clean = b"molecule_id\tvalue\nM-EXAMPLE\t0\n"
    (source / "clean.tsv").write_bytes(clean)
    assert check_repository(source, _policy("clean.tsv", clean, kind="tabular")).ok

    sensitive = b"api_key\tvalue\nsynthetic\t0\n"
    (source / "sensitive.tsv").write_bytes(sensitive)
    report = check_repository(source, _policy("sensitive.tsv", sensitive, kind="tabular"))
    assert "credential_field" in {finding.code for finding in report.findings}


def test_malformed_tsv_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b'column_a\tcolumn_b\nvalue\t"unterminated\n'
    (source / "invalid.tsv").write_bytes(content)
    report = check_repository(source, _policy("invalid.tsv", content, kind="tabular"))
    assert "invalid_tsv" in {finding.code for finding in report.findings}


@pytest.mark.parametrize(
    "path",
    [
        "../secret.json",
        "/tmp/secret.json",
        "safe/../../secret.json",
        "safe\\file.json",
        "safe\nfile.json",
        "cafe\u0301.json",
    ],
)
def test_policy_rejects_traversal_and_non_posix_paths(path: str) -> None:
    with pytest.raises(PolicyError):
        load_policy(_policy(path, b"{}"))


@pytest.mark.parametrize(
    "path",
    [".git/config.json", "cache/result.json", "__pycache__/result.json", "provider-receipts/run.json", "private/case.json"],
)
def test_policy_rejects_private_cache_and_receipt_paths(path: str) -> None:
    with pytest.raises(PolicyError):
        load_policy(_policy(path, b"{}"))


def test_requested_unapproved_path_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b"{}"
    (source / "safe.json").write_bytes(content)
    report = check_repository(source, _policy("safe.json", content), include=["other.json", "../escape"])
    assert not report.ok
    assert {finding.code for finding in report.findings} == {
        "empty_selection",
        "unapproved_path",
        "invalid_path",
    }


def test_string_include_is_rejected_instead_of_iterated(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b"{}"
    (source / "safe.json").write_bytes(content)
    report = check_repository(source, _policy("safe.json", content), include="safe.json")
    assert not report.ok
    assert {finding.code for finding in report.findings} == {"empty_selection", "invalid_path"}


def test_symlink_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"{}")
    (source / "safe.json").symlink_to(outside)
    report = check_repository(source, _policy("safe.json", b"{}"))
    assert not report.ok
    assert report.findings[0].code == "symlink"


def test_symlinked_source_directory_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b"{}"
    (source / "safe.json").write_bytes(content)
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    report = check_repository(alias, _policy("safe.json", content))
    assert not report.ok
    assert report.findings[0].code == "source_symlink"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO test requires POSIX")
def test_special_file_is_rejected_without_blocking(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    os.mkfifo(source / "pipe.json")
    report = check_repository(source, _policy("pipe.json", b"{}"))
    assert not report.ok
    assert report.findings[0].code == "not_regular_file"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ({"api_key": "not-for-public-export"}, "credential_field"),
        ({"provider_receipt": {"cost": 1}}, "provider_receipt"),
        ({"messages": [{"role": "user", "content": "private"}]}, "internal_conversation"),
        ({"case_id": "CASE-2048"}, "case_identifier"),
        ({"source": "/Users/example/private/file.json"}, "private_path"),
        ({"source": "/Volumes/Research/private/file.json"}, "private_path"),
        ({"source": "C:\\Users\\example\\private\\file.json"}, "private_path"),
    ],
)
def test_sensitive_structured_content_is_rejected(tmp_path: Path, value: dict, code: str) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = json.dumps(value).encode()
    (source / "item.json").write_bytes(content)
    report = check_repository(source, _policy("item.json", content))
    assert not report.ok
    assert code in {finding.code for finding in report.findings}


def test_empty_schema_fields_are_not_treated_as_records(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b'{"authorization":{},"request_id":null,"messages":[]}'
    (source / "template.json").write_bytes(content)
    assert check_repository(source, _policy("template.json", content)).ok


def test_raw_prefixed_credential_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    token = "sk-proj-" + "A" * 24
    content = json.dumps({"value": token}).encode()
    (source / "item.json").write_bytes(content)
    report = check_repository(source, _policy("item.json", content))
    assert not report.ok
    assert "credential_value" in {finding.code for finding in report.findings}


def test_unknown_format_and_unreviewed_binary_are_rejected() -> None:
    with pytest.raises(PolicyError):
        load_policy(_policy("artifact.dat", b"data", kind="text"))
    with pytest.raises(PolicyError):
        load_policy(_policy("artifact.dat", b"data", kind="binary"))


def test_generated_manifest_path_is_reserved() -> None:
    with pytest.raises(PolicyError):
        load_policy(_policy("surface-atlas-export.json", b"{}"))


def test_explicitly_reviewed_binary_is_hash_checked(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b"\x00\xffsynthetic"
    (source / "artifact.dat").write_bytes(content)
    policy = _policy("artifact.dat", content, kind="binary", reviewed_binary=True)
    assert check_repository(source, policy).ok
    output = tmp_path / "public"
    export_subset(source, output, policy)
    manifest = json.loads((output / "surface-atlas-export.json").read_text())
    assert manifest["files"][0]["review_exceptions"] == ["binary_content_not_scanned"]


def test_changed_content_refuses_export_without_partial_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    reviewed = b'{"title":"reviewed"}'
    (source / "item.json").write_bytes(reviewed)
    policy = _policy("item.json", reviewed)
    (source / "item.json").write_bytes(b'{"title":"changed"}')
    output = tmp_path / "public"

    with pytest.raises(ExportError, match="hash_mismatch"):
        export_subset(source, output, policy)
    assert not output.exists()
    assert not list(tmp_path.glob(".public.tmp-*"))


def test_total_size_override_supports_bundle_triage(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b'{"title":"synthetic bundle"}'
    (source / "item.json").write_bytes(content)
    report = check_repository(source, _policy("item.json", content), max_total_bytes=5)
    assert not report.ok
    assert report.total_bytes == len(content)
    assert "total_too_large" in {finding.code for finding in report.findings}


def test_existing_output_is_never_modified(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b"{}"
    (source / "item.json").write_bytes(content)
    output = tmp_path / "public"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(ExportError, match="must not already exist"):
        export_subset(source, output, _policy("item.json", content))
    assert marker.read_text() == "keep"


def test_empty_allowlist_does_not_report_success(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    policy = {
        "version": 1,
        "limits": {"max_files": 1, "max_file_bytes": 1, "max_total_bytes": 1},
        "deny_terms": [],
        "files": [],
    }
    report = check_repository(source, policy)
    assert not report.ok
    assert report.findings[0].code == "empty_selection"


def test_python_fixture_exception_is_named_hash_bound_and_manifested(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b'SAMPLE = "/Users/example/private/input.json"\n'
    (source / "fixture.py").write_bytes(content)
    policy = _policy("fixture.py", content, kind="python", allow_findings=["private_path"])
    assert check_repository(source, policy).ok
    output = tmp_path / "public"
    export_subset(source, output, policy)
    manifest = json.loads((output / "surface-atlas-export.json").read_text())
    assert manifest["files"][0]["review_exceptions"] == ["private_path"]
    (source / "fixture.py").write_bytes(content + b"# changed\n")
    changed = check_repository(source, policy)
    assert not changed.ok
    assert "hash_mismatch" in {finding.code for finding in changed.findings}


def test_non_source_file_cannot_except_findings() -> None:
    content = b'{"case_id":"example"}'
    with pytest.raises(PolicyError, match="only valid for reviewed source"):
        load_policy(_policy("data.json", content, allow_findings=["case_identifier"]))


def test_private_deny_term_is_rejected_without_echoing_term(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b'{"title":"Synthetic CASE-ALPHA-42"}'
    (source / "item.json").write_bytes(content)
    policy = _policy("item.json", content)
    policy["deny_terms"] = ["CASE-ALPHA-42"]
    report = check_repository(source, policy)
    assert not report.ok
    finding = next(item for item in report.findings if item.code == "deny_term")
    assert "CASE-ALPHA-42" not in finding.message


def test_private_deny_term_in_path_is_not_echoed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b"{}"
    (source / "case-alpha-42.json").write_bytes(content)
    policy = _policy("case-alpha-42.json", content)
    policy["deny_terms"] = ["CASE-ALPHA-42"]
    report = check_repository(source, policy)
    finding = next(item for item in report.findings if item.code == "deny_term")
    assert finding.path == "."
    assert "CASE-ALPHA-42" not in finding.message


def test_private_deny_term_in_unapproved_path_is_not_echoed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b"{}"
    (source / "safe.json").write_bytes(content)
    policy = _policy("safe.json", content)
    policy["deny_terms"] = ["CASE-ALPHA-42"]
    report = check_repository(source, policy, include=["CASE-ALPHA-42.json"])
    finding = next(item for item in report.findings if item.code == "unapproved_path")
    assert finding.path == "."


def test_publish_collision_preserves_new_output_and_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = b"{}"
    (source / "safe.json").write_bytes(content)
    output = tmp_path / "public"

    def collide(_source: object, _destination: object) -> None:
        output.mkdir()
        (output / "owner.txt").write_text("keep", encoding="utf-8")
        raise FileExistsError("simulated publish race")

    monkeypatch.setattr(export_module, "_rename_directory_exclusive", collide)
    with pytest.raises(ExportError, match="output may have appeared"):
        export_subset(source, output, _policy("safe.json", content))
    assert (output / "owner.txt").read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(".public.tmp-*"))


def test_exclusive_directory_publish_never_replaces_empty_destination(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "new.txt").write_text("new", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    with pytest.raises(OSError):
        export_module._rename_directory_exclusive(staged, destination)
    assert staged.is_dir()
    assert not (destination / "new.txt").exists()


@pytest.mark.parametrize(
    ("name", "kind", "content", "expected_code"),
    [
        ("broken.py", "python", b"def broken(:\n", "invalid_python"),
        ("broken.svg", "svg", b"<svg><path></svg>", "invalid_svg"),
        ("broken.excalidraw", "excalidraw", b"{broken", "invalid_json"),
    ],
)
def test_source_format_validation(
    tmp_path: Path, name: str, kind: str, content: bytes, expected_code: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / name).write_bytes(content)
    report = check_repository(source, _policy(name, content, kind=kind))
    assert not report.ok
    assert expected_code in {finding.code for finding in report.findings}


def test_git_attributes_use_scanned_config_kind(tmp_path: Path) -> None:
    content = b"* text=auto eol=lf\n*.png binary\n"
    (tmp_path / ".gitattributes").write_bytes(content)
    result = check_repository(tmp_path, _policy(".gitattributes", content, kind="config"))
    assert result.ok, result.findings


_ATTACHMENT_ID = '-'.join(('12345678', '1234', '4234', '8234', '123456789abc'))
_ATTACHMENT_URL = 'https://github.com/user-attachments/assets/' + _ATTACHMENT_ID


@pytest.mark.parametrize('text', [
    _ATTACHMENT_URL,
    '<' + _ATTACHMENT_URL + '>',
    '[Watch the clip](' + _ATTACHMENT_URL + ')',
    'Public attachment:\n' + _ATTACHMENT_URL + '\n',
])
def test_canonical_github_attachment_uuid_is_not_a_case_identifier(tmp_path, text):
    source = tmp_path / 'source'; source.mkdir()
    content = text.encode()
    (source / 'README.md').write_bytes(content)
    policy = _policy('README.md', content, kind='text')
    report = check_repository(source, policy)
    assert report.ok, report.findings
    assert report.files[0].review_exceptions == ()
    output = tmp_path / 'public'
    export_subset(source, output, policy)
    assert (output / 'README.md').read_bytes() == content
    (source / 'README.md').write_bytes(content + b'changed')
    assert not check_repository(source, policy).ok


@pytest.mark.parametrize('url', [
    _ATTACHMENT_URL.replace('github.com', 'github.com.example.invalid'),
    _ATTACHMENT_URL.replace('github.com', 'example.invalid/github.com'),
    _ATTACHMENT_URL.replace('github.com', 'user@github.com'),
    _ATTACHMENT_URL.replace('github.com', 'github.com@evil.invalid'),
    _ATTACHMENT_URL.replace('github.com', 'github.com:443'),
    _ATTACHMENT_URL.replace('https:', 'http:'),
    _ATTACHMENT_URL + '/private',
    _ATTACHMENT_URL + '.mp4',
    _ATTACHMENT_URL + '?download=1',
    _ATTACHMENT_URL + '#fragment',
    _ATTACHMENT_URL + '/',
    _ATTACHMENT_URL + '\\private',
    'https://example.invalid/?redirect=(' + _ATTACHMENT_URL + ')',
    'https://example.invalid/path/' + _ATTACHMENT_URL,
    'prefix/' + _ATTACHMENT_URL,
    '(' + _ATTACHMENT_URL + ')suffix',
    'ftp://' + _ATTACHMENT_URL,
])
def test_attachment_lookalikes_and_suffixes_remain_blocked(tmp_path, url):
    source = tmp_path / 'source'; source.mkdir()
    content = url.encode()
    (source / 'README.md').write_bytes(content)
    report = check_repository(source, _policy('README.md', content, kind='text'))
    assert 'case_identifier' in {finding.code for finding in report.findings}


def test_same_uuid_outside_attachment_is_still_a_case_identifier(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    content = (_ATTACHMENT_URL + '\nUnrelated identifier: ' + _ATTACHMENT_ID).encode()
    (source / 'README.md').write_bytes(content)
    report = check_repository(source, _policy('README.md', content, kind='text'))
    assert 'case_identifier' in {finding.code for finding in report.findings}


def test_attachment_does_not_mask_other_sensitive_content_or_explicit_fields(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    content = json.dumps({'attachment': _ATTACHMENT_URL, 'case_id': _ATTACHMENT_URL,
                          'api_key': 'syntheticcredentialvalue',
                          'header': ' '.join(('Authorization:', 'Bearer', 'syntheticcredentialvalue')),
                          'source_path': '/Users/example/private/notes.txt'}).encode()
    (source / 'item.json').write_bytes(content)
    policy = _policy('item.json', content)
    policy['deny_terms'] = [_ATTACHMENT_ID]
    report = check_repository(source, policy)
    assert {'case_identifier', 'credential_field', 'credential_value', 'private_path', 'deny_term'} <= {finding.code for finding in report.findings}


def test_attachment_in_html_attribute_and_decoded_content_uses_same_rule(tmp_path):
    report = _check_html(tmp_path, '<a href="' + _ATTACHMENT_URL + '">Public video</a>')
    assert report.ok, report.findings
