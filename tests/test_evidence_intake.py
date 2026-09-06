"""Local intake preserves raw provenance and refuses inconsistent projections."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from surface_atlas import evidence_intake as intake
from surface_atlas.workspace import initialize_atlas


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def record(identifier, disposition='surface-target', *, record_id=None):
    value = {'record_id': record_id or 'R-' + identifier, 'entity_id': identifier,
             'preferred_name': 'Synthetic ' + identifier, 'identifiers': {'fixture': identifier},
             'reason': 'Explicit synthetic reviewer disposition.', 'locator': 'Synthetic row ' + identifier,
             'disposition': disposition}
    if disposition == 'surface-target':
        value['target'] = {'target_id': 'T-' + identifier, 'preferred_name': value['preferred_name'],
                           'structure_tier': 'retained-unmodeled',
                           'surface_evidence': {'state': 'synthetic-positive', 'basis': 'Invented intact-cell protein observation; software test only.'}}
    return value


def snapshot(query_id='Q-ONE', records=None, status='complete'):
    source = {'source_id': 'S-FIXTURE', 'query_id': query_id, 'title': 'Synthetic reviewed source',
              'query': 'Invented query for software tests', 'source_class': 'synthetic-assay',
              'retrieved_at': '2026-09-01T12:00:00Z', 'license': 'Synthetic fixture', 'status': status}
    if status != 'complete': source['limitation'] = 'Synthetic query was not fully retrieved.'
    return {'schema_version': intake.SNAPSHOT_SCHEMA, 'data_kind': 'synthetic', 'source': source,
            'records': records if records is not None else [record('ALPHA')]}


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / 'base'
    initialize_atlas('intake-test', root, disease='Synthetic research question')
    plan = json.loads((root / 'atlas-plan.json').read_text())
    plan['data_kind'] = 'synthetic'
    write(root / 'atlas-plan.json', plan)
    return root


@pytest.fixture
def managed(tmp_path, workspace):
    source = write(tmp_path / 'snapshot.json', snapshot())
    output = tmp_path / 'managed'
    intake.ingest_evidence([source], workspace, output)
    return output


def test_raw_duplicate_and_disposition_counts_are_deterministic(tmp_path):
    first = snapshot(records=[record('ALPHA'), record('BETA', 'excluded-from-surface-universe')])
    second = snapshot('Q-TWO', [record('ALPHA'), record('GAMMA', 'unresolved')])
    paths = [write(tmp_path / 'one.json', first), write(tmp_path / 'two.json', second)]
    compiled = intake.compile_snapshots(paths, 'intake-test')
    assert compiled == intake.compile_snapshots(list(reversed(paths)), 'intake-test')
    assert compiled['counts'] == {'raw_records': 4, 'duplicate_records': 1,
        'normalized_discovered_entities': 3, 'surface_targets': 1,
        'excluded_from_surface_universe': 1, 'unresolved_records': 1}
    assert len(compiled['documents']['targets.json']['records'][0]['source_refs']) == 2
    assert list(compiled['snapshots'].values()) == [path.read_bytes() for path in paths]
    for name, raw in compiled['snapshots'].items():
        assert Path(name).stem == hashlib.sha256(raw).hexdigest()


def test_conflicting_dispositions_remain_unresolved(tmp_path):
    paths = [write(tmp_path / 'a.json', snapshot('Q-A', [record('ALPHA')])),
             write(tmp_path / 'b.json', snapshot('Q-B', [record('ALPHA', 'excluded-from-surface-universe')]))]
    compiled = intake.compile_snapshots(paths, 'intake-test')
    assert compiled['counts']['surface_targets'] == compiled['counts']['excluded_from_surface_universe'] == 0
    assert compiled['counts']['unresolved_records'] == 1
    assert 'conflict' in compiled['documents']['discovered-entities.json']['records'][0]['resolution_required']


@pytest.mark.parametrize('mutation', ['same_id_different_entity', 'different_id_same_entity', 'same_target_different_entity', 'different_target_projection'])
def test_identity_conflicts_fail_instead_of_fuzzy_merging(tmp_path, mutation):
    a, b = record('ALPHA'), record('BETA')
    if mutation == 'same_id_different_entity': b['identifiers'] = a['identifiers'].copy()
    elif mutation == 'different_id_same_entity': b['entity_id'] = a['entity_id']
    elif mutation == 'same_target_different_entity': b['target']['target_id'] = a['target']['target_id']
    elif mutation == 'different_target_projection':
        b = copy.deepcopy(a); b['record_id'] = 'R-OTHER'; b['target']['preferred_name'] = 'Conflicting projected label'
    source = write(tmp_path / 'input.json', snapshot(records=[a, b]))
    with pytest.raises(intake.EvidenceError, match='identit|identifier|target_id|target projection'):
        intake.compile_snapshots([source], 'intake-test')


@pytest.mark.parametrize('mutation', ['rna_only', 'unknown_top_key', 'unknown_source_key', 'unknown_record_key', 'duplicate_record', 'partial_no_limit', 'nonportable_id', 'invalid_disposition', 'invalid_kind'])
def test_snapshot_contract_requires_explicit_review_and_strict_fields(tmp_path, mutation):
    value = snapshot()
    if mutation == 'rna_only':
        value['records'][0]['target'].pop('surface_evidence'); value['records'][0]['target']['expression'] = 100
    elif mutation == 'unknown_top_key': value['confidence'] = 100
    elif mutation == 'unknown_source_key': value['source']['trust_me'] = True
    elif mutation == 'unknown_record_key': value['records'][0]['score'] = 100
    elif mutation == 'duplicate_record': value['records'].append(copy.deepcopy(value['records'][0]))
    elif mutation == 'partial_no_limit': value['source']['status'] = 'partial'
    elif mutation == 'nonportable_id': value['records'][0]['entity_id'] = '../ALPHA'
    elif mutation == 'invalid_disposition': value['records'][0]['disposition'] = []
    elif mutation == 'invalid_kind': value['data_kind'] = []
    source = write(tmp_path / 'input.json', value)
    with pytest.raises(intake.EvidenceError):
        intake.compile_snapshots([source], 'intake-test')


@pytest.mark.parametrize('bad', ['NaN', 'Infinity', '-Infinity', '1e999'])
def test_nonfinite_json_numbers_are_rejected_even_in_unrelated_nested_target_fields(tmp_path, bad):
    content = json.dumps(snapshot()).replace('"structure_tier": "retained-unmodeled"', '"extra_measurement": ' + bad + ', "structure_tier": "retained-unmodeled"')
    source = tmp_path / 'bad.json'; source.write_text(content)
    with pytest.raises(intake.EvidenceError, match='finite'):
        intake.compile_snapshots([source], 'intake-test')


def test_duplicate_json_keys_are_not_silently_overwritten(tmp_path):
    source = tmp_path / 'bad.json'
    source.write_text(json.dumps(snapshot()).replace('"data_kind": "synthetic"', '"data_kind": "public-source", "data_kind": "synthetic"'))
    with pytest.raises(intake.EvidenceError, match='duplicate JSON key'):
        intake.compile_snapshots([source], 'intake-test')


def test_intake_copies_exact_sources_without_changing_base(managed, workspace):
    assert json.loads((workspace / 'targets.json').read_text())['records'] == []
    assert intake.reconcile_evidence(managed)['consistent']
    assert intake.has_managed_evidence(managed)
    assert not list(managed.parent.glob('.evidence-*'))


def test_projection_allows_annotations_but_never_source_field_changes(managed):
    path = managed / 'targets.json'
    value = json.loads(path.read_text())
    value['records'][0]['new_annotation'] = {'measurement_plan': 'Synthetic follow-up'}
    write(path, value)
    assert intake.reconcile_evidence(managed)['consistent']
    value['records'][0]['surface_evidence']['basis'] = 'Replaced original observation'
    write(path, value)
    with pytest.raises(intake.EvidenceError, match='projection'):
        intake.reconcile_evidence(managed)


def test_reconcile_reports_and_writes_new_counts_without_overwriting(managed):
    ledger_path = managed / 'search-ledger.json'; ledger = json.loads(ledger_path.read_text())
    ledger['counts']['surface_targets'] = 99
    write(ledger_path, ledger)
    output = managed.parent / 'corrected.json'
    result = intake.reconcile_evidence(managed, output)
    assert not result['consistent']
    assert result['changes']['surface_targets'] == {'recorded': 99, 'expected': 1}
    assert json.loads(output.read_text())['counts']['surface_targets'] == 1
    assert json.loads(ledger_path.read_text())['counts']['surface_targets'] == 99
    with pytest.raises(intake.EvidenceError, match='must not exist'):
        intake.reconcile_evidence(managed, output)
    assert not list(managed.parent.glob('.evidence-ledger-*'))


@pytest.mark.parametrize('mutation', ['strip_artifact', 'strip_all_metadata', 'coverage', 'data_kind', 'counts_bool', 'byte_bool', 'path_traversal', 'path_backslash', 'wrong_hash', 'changed_bytes'])
def test_managed_ledger_cannot_downgrade_or_forge_snapshot_provenance(managed, mutation):
    path = managed / 'search-ledger.json'; ledger = json.loads(path.read_text())
    artifact = ledger['sources'][0]['artifact']
    if mutation == 'strip_artifact': ledger['sources'][0].pop('artifact')
    elif mutation == 'strip_all_metadata':
        ledger['sources'] = []; ledger.pop('data_kind'); ledger.pop('evidence_intake')
    elif mutation == 'coverage': ledger['coverage_state'] = 'partial'
    elif mutation == 'data_kind': ledger['data_kind'] = 'public-source'
    elif mutation == 'counts_bool': ledger['counts']['surface_targets'] = True
    elif mutation == 'byte_bool': artifact['bytes'] = True
    elif mutation == 'path_traversal': artifact['path'] = 'evidence/snapshots/../../outside.json'
    elif mutation == 'path_backslash': artifact['path'] = 'evidence/snapshots/..\\outside.json'
    elif mutation == 'wrong_hash': artifact['sha256'] = '0' * 64
    elif mutation == 'changed_bytes': (managed / artifact['path']).write_text('{}')
    write(path, ledger)
    assert intake.has_managed_evidence(managed, ledger)
    with pytest.raises(intake.EvidenceError):
        intake.reconcile_evidence(managed)


def test_partial_queries_cannot_claim_complete_coverage(tmp_path, workspace):
    source = write(tmp_path / 'partial.json', snapshot(status='partial'))
    output = tmp_path / 'partial-atlas'
    intake.ingest_evidence([source], workspace, output)
    ledger_path = output / 'search-ledger.json'; ledger = json.loads(ledger_path.read_text())
    assert ledger['coverage_state'] == 'partial'
    ledger['coverage_state'] = 'complete_within_recorded_scope'; write(ledger_path, ledger)
    with pytest.raises(intake.EvidenceError, match='coverage_state'):
        intake.reconcile_evidence(output)


def symlink(link, target, directory=False):
    try: link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError): pytest.skip('symlink creation is unavailable')


def test_symlink_source_snapshot_is_rejected(tmp_path):
    source = write(tmp_path / 'source.json', snapshot())
    link = tmp_path / 'link.json'; symlink(link, source)
    with pytest.raises(intake.EvidenceError, match='regular file'):
        intake.compile_snapshots([link], 'intake-test')


def test_snapshot_directory_symlink_is_rejected(managed):
    snapshots = managed / 'evidence/snapshots'; moved = managed.parent / 'moved'
    snapshots.rename(moved); symlink(snapshots, moved, True)
    with pytest.raises(intake.EvidenceError, match='unsafe'):
        intake.reconcile_evidence(managed)


def test_intake_rejects_existing_output_and_nested_output(tmp_path, workspace):
    source = write(tmp_path / 'source.json', snapshot())
    existing = tmp_path / 'existing'; existing.mkdir()
    for output in (existing, workspace / 'nested'):
        with pytest.raises(intake.EvidenceError):
            intake.ingest_evidence([source], workspace, output)
    assert not list(tmp_path.glob('.evidence-*'))


def test_intake_cleans_stage_when_final_validation_fails(tmp_path, workspace, monkeypatch):
    from surface_atlas import validator
    source = write(tmp_path / 'source.json', snapshot())
    monkeypatch.setattr(validator, 'validate_workspace', lambda _: {'valid': False, 'errors': ['deliberate synthetic failure']})
    output = tmp_path / 'failed'
    with pytest.raises(intake.EvidenceError, match='invalid atlas'):
        intake.ingest_evidence([source], workspace, output)
    assert not output.exists()
    assert not list(tmp_path.glob('.evidence-*'))
    assert json.loads((workspace / 'targets.json').read_text())['records'] == []


def test_ledger_write_failure_cleans_temporary_file(managed, monkeypatch):
    def fail(*args): raise OSError('synthetic publication failure')
    monkeypatch.setattr(intake.os, 'link', fail)
    output = managed.parent / 'failed-ledger.json'
    with pytest.raises(OSError, match='publication failure'):
        intake.reconcile_evidence(managed, output)
    assert not output.exists()
    assert not list(managed.parent.glob('.evidence-ledger-*'))


def test_source_reference_detection_survives_removed_ledger_marker_and_snapshot_directory(managed):
    path = managed / 'search-ledger.json'; ledger = json.loads(path.read_text())
    ledger['sources'] = []; ledger.pop('data_kind'); ledger.pop('evidence_intake')
    write(path, ledger)
    shutil.rmtree(managed / 'evidence/snapshots')
    assert intake.has_managed_evidence(managed, ledger)
    with pytest.raises(intake.EvidenceError, match='every source'):
        intake.reconcile_evidence(managed)


def test_symlink_atlas_and_dangling_output_are_rejected(tmp_path, workspace):
    source = write(tmp_path / 'source.json', snapshot())
    alias = tmp_path / 'alias'; symlink(alias, workspace, True)
    with pytest.raises(intake.EvidenceError, match='symlink'):
        intake.ingest_evidence([source], alias, tmp_path / 'result')
    output = tmp_path / 'dangling'; symlink(output, tmp_path / 'missing', True)
    with pytest.raises(intake.EvidenceError, match='new directory'):
        intake.ingest_evidence([source], workspace, output)


def test_snapshot_schema_accepts_fixture_and_requires_retention_basis():
    jsonschema = pytest.importorskip('jsonschema')
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / 'schemas/v0.1/evidence-snapshot.schema.json').read_text())
    jsonschema.validate(snapshot(), schema, format_checker=jsonschema.FormatChecker())
    invalid = snapshot(); invalid['records'][0]['target']['surface_evidence'] = {'rna_expression': 100}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_as_of_uses_latest_instant_across_timezones(tmp_path):
    first, second = snapshot('Q-ONE'), snapshot('Q-TWO')
    first['source']['retrieved_at'] = '2026-09-02T00:30:00+14:00'
    second['source']['retrieved_at'] = '2026-09-01T22:00:00Z'
    paths = [write(tmp_path / 'one.json', first), write(tmp_path / 'two.json', second)]
    compiled = intake.compile_snapshots(paths, 'intake-test')
    assert compiled['documents']['search-ledger.json']['as_of'] == '2026-09-01'


def test_validator_and_report_refuse_managed_metadata_downgrade(managed, capsys):
    from surface_atlas import report_builder, validator
    path = managed / 'search-ledger.json'; ledger = json.loads(path.read_text())
    ledger.pop('data_kind'); ledger.pop('evidence_intake')
    ledger['sources'][0].pop('artifact')
    write(path, ledger)
    result = validator.validate_workspace(managed)
    assert not result['valid']
    assert any('every source' in error for error in result['errors'])
    assert report_builder.main([str(managed), '--output-root', str(managed.parent / 'reports'), '--run-id', 'downgrade', '--json']) == 1
    assert 'every source' in capsys.readouterr().err
    assert not list((managed.parent / 'reports').rglob('index.html'))


def test_zero_result_complete_query_still_has_explicit_scoped_provenance(tmp_path):
    path = write(tmp_path / 'empty.json', snapshot(records=[]))
    compiled = intake.compile_snapshots([path], 'intake-test')
    assert set(compiled['counts'].values()) == {0}
    ledger = compiled['documents']['search-ledger.json']
    assert ledger['coverage_state'] == 'complete_within_recorded_scope'
    assert len(ledger['sources']) == 1
    assert 'supplied reviewed queries' in ledger['limitations'][0]


def test_reingest_replaces_managed_snapshots_without_touching_source_or_other_artifacts(managed, tmp_path):
    before = {p.relative_to(managed).as_posix(): p.read_bytes() for p in managed.rglob('*') if p.is_file()}
    unrelated = managed / 'evidence' / 'retained-note.txt'
    unrelated.write_text('Unrelated reviewed source note must survive.')
    source = write(tmp_path / 'new-source.json', snapshot('Q-NEW', [record('BETA')]))
    output = tmp_path / 'reingested'
    intake.ingest_evidence([source], managed, output)
    expected = intake.compile_snapshots([source], 'intake-test')
    assert {p.relative_to(output).as_posix() for p in (output/'evidence/snapshots').iterdir()} == set(expected['snapshots'])
    assert not set(expected['snapshots']) & {name for name in before if name.startswith('evidence/snapshots/')}
    assert (output/'evidence/retained-note.txt').read_bytes() == unrelated.read_bytes()
    assert all((managed/name).read_bytes() == raw for name,raw in before.items())
    assert intake.reconcile_evidence(output)['consistent']
    from surface_atlas.validator import validate_workspace
    assert validate_workspace(output)['valid']


def test_reingest_keeps_explicitly_resupplied_snapshot(managed, tmp_path):
    old = next((managed/'evidence/snapshots').iterdir())
    source = write(tmp_path/'new-source.json', snapshot('Q-NEW', [record('BETA')]))
    note = managed/'retained-reference.md'
    note.write_text('Retain provenance at ' + old.relative_to(managed).as_posix())
    output = tmp_path/'reingested'
    intake.ingest_evidence([old,source], managed, output)
    assert len(list((output/'evidence/snapshots').iterdir())) == 2
    assert (output/note.name).read_bytes() == note.read_bytes()
    assert intake.reconcile_evidence(output)['consistent']


@pytest.mark.parametrize('filename', ['retained-reference.md', 'retained-record.json', 'escaped-record.json'])
def test_reingest_refuses_to_strand_meaningful_reference(managed, tmp_path, filename):
    old = next((managed/'evidence/snapshots').iterdir())
    reference = old.relative_to(managed).as_posix()
    content = json.dumps({'artifact': {'path': reference}}) if filename.endswith('.json') else '[source](' + reference + ')'
    if filename == 'escaped-record.json': content = content.replace('/', '\\/')
    (managed/filename).write_text(content)
    source = write(tmp_path/'new-source.json', snapshot('Q-NEW', [record('BETA')]))
    output = tmp_path/'refused'
    with pytest.raises(intake.EvidenceError, match='retained artifact references'):
        intake.ingest_evidence([source], managed, output)
    assert old.exists() and not output.exists()
    assert not list(tmp_path.glob('.evidence-*'))


@pytest.mark.parametrize('shape', ['nested-directory', 'unmanaged-file', 'directory-is-file'])
def test_reingest_rejects_unexpected_managed_directory_shape(managed, tmp_path, shape):
    directory = managed/'evidence/snapshots'
    if shape == 'nested-directory': (directory/'nested').mkdir()
    elif shape == 'unmanaged-file': (directory/'notes.txt').write_text('Do not silently delete this artifact.')
    else:
        shutil.rmtree(directory); directory.write_text('Not a managed directory')
    source = write(tmp_path/'new-source.json', snapshot('Q-NEW', [record('BETA')]))
    output = tmp_path/'refused'
    with pytest.raises(intake.EvidenceError, match='directory shape'):
        intake.ingest_evidence([source], managed, output)
    assert not output.exists()


def test_reconciliation_validation_and_report_reject_unreferenced_managed_snapshot(managed, tmp_path, capsys):
    stale = write(tmp_path/'stale-source.json', snapshot('Q-STALE', [record('BETA')])).read_bytes()
    path = managed/'evidence/snapshots'/f'{hashlib.sha256(stale).hexdigest()}.json'
    path.write_bytes(stale)
    with pytest.raises(intake.EvidenceError, match='unreferenced'):
        intake.reconcile_evidence(managed)
    from surface_atlas import validator, report_builder
    assert not validator.validate_workspace(managed)['valid']
    assert report_builder.main([str(managed), '--output-root', str(tmp_path/'reports'), '--run-id', 'stale', '--json']) == 1
    assert 'unreferenced' in capsys.readouterr().err
    assert not list((tmp_path/'reports').rglob('index.html'))


def test_reingest_validation_failure_keeps_original_snapshots(managed, tmp_path, monkeypatch):
    from surface_atlas import validator
    before = {p.name:p.read_bytes() for p in (managed/'evidence/snapshots').iterdir()}
    source = write(tmp_path/'new-source.json', snapshot('Q-NEW', [record('BETA')]))
    monkeypatch.setattr(validator, 'validate_workspace', lambda _: {'valid': False, 'errors': ['deliberate reingest failure']})
    output = tmp_path/'failed-reingest'
    with pytest.raises(intake.EvidenceError, match='invalid atlas'):
        intake.ingest_evidence([source], managed, output)
    assert {p.name:p.read_bytes() for p in (managed/'evidence/snapshots').iterdir()} == before
    assert not output.exists() and not list(tmp_path.glob('.evidence-*'))
