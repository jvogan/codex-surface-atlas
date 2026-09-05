import copy
import json
import tempfile
from pathlib import Path

import pytest

from surface_atlas import report_builder as builder
from surface_atlas import report_presentation as presentation
from surface_atlas.screening_context import screening_role_group


def collection():
    return {
        'atlas_id': 'synthetic-surface-atlas',
        'schema_version': 'codex-surface-screening-result-collection/v0.1',
        'source_runs': [{'run_id': 'screen-a', 'screen_id': 'site-a'}, {'run_id': 'screen-b'}],
        'confirmation_contexts': [
            {'run_id': 'screen-a', 'screen_id': 'site-a', 'requested': True, 'completed': False, 'note': '<script>example</script>'},
        ],
        'input_collections': [{'input_ordinal': 1, 'sha256': 'a' * 64, 'bytes': 128}],
        'summary': {'execution_complete': False},
        'records': [
            {'screening_result_id': 'result-a', 'run_id': 'screen-a', 'execution_state': 'planned', 'pose_score': None},
            {'screening_result_id': 'result-b', 'run_id': 'screen-b', 'execution_state': 'failed', 'failure_reason': 'Example failure'},
        ],
    }


def test_run_contexts_stay_scoped_and_unmodified():
    payload = collection()
    original = copy.deepcopy(payload)
    runs = presentation.screening_run_contexts(payload, payload['records'])
    assert runs['screen-a']['confirmations'] == payload['confirmation_contexts']
    assert runs['screen-b']['confirmations'] == []
    markup = presentation.render_screen_provenance(builder, payload, payload['records'])
    assert '<script>' not in markup
    assert '&lt;script&gt;' in markup
    assert 'No confirmation context recorded for this run.' in markup
    assert '"completed": false' not in markup  # JSON quotes are HTML-escaped.
    assert '&quot;completed&quot;: false' in markup
    assert payload == original


@pytest.mark.parametrize('change', [
    {'source_runs': {}},
    {'source_runs': [None]},
    {'source_runs': []},
    {'source_runs': [{'run_id': 'same'}, {'run_id': 'same'}]},
    {'source_run': {'run_id': 'ambiguous'}},
    {'confirmation_contexts': [None]},
    {'confirmation_context': {}},
    {'confirmation_contexts': [{'run_id': 'unknown'}]},
    {'confirmation_contexts': [{'run_id': 'screen-a', 'screen_id': 'site-other'}]},
    {'records': [{'run_id': 'unknown'}]},
])
def test_invalid_run_scopes_fail_before_rendering(change):
    payload = collection()
    payload.update(change)
    with pytest.raises(ValueError, match='screening-results.json'):
        presentation.screening_run_contexts(payload, payload['records'])


def test_single_run_context_and_legacy_records():
    payload = {'source_run': {'run_id': 'screen-a'}, 'confirmation_context': {'completed': False}}
    assert presentation.screening_run_contexts(payload, [ {'run_id': 'screen-a'}])['screen-a']['confirmations'] == [{'run_id': 'screen-a', 'completed': False}]
    assert presentation.screening_run_contexts({}, [{'screening_result_id': 'legacy'}]) == {}
    assert presentation.screening_run_contexts({'source_run': {'run_id': 'screen-a'}, 'confirmation_context': None}, [])['screen-a']['confirmations'] == []


def test_json_exports_preserve_collection_envelope_and_records():
    payload = collection()
    metadata = {key: value for key, value in payload.items() if key != 'records'}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        builder.write_data_exports(root, {'atlas_id': payload['atlas_id']}, {},
                                   {'screening-results.json': payload['records']}, [], [], [],
                                   '2026-01-01T00:00:00Z', {}, {'screening-results.json': metadata})
        for path in ('data/screening-results.json', 'data/collections/screening-results.json'):
            assert json.loads((root / path).read_text()) == payload
        consolidated = json.loads((root / 'data/atlas.json').read_text())
        assert consolidated['collection_metadata']['screening-results.json'] == metadata


@pytest.mark.parametrize('fields, expected', [
    ({'screen_role': None, 'control_status': 'negative-control'}, 'control'),
    ({'screen_role': '', 'control_status': 'negative-control'}, 'control'),
    ({'screen_role': 'NEGATIVE-CONTROL'}, 'control'),
    ({'control_role': 'reference_control', 'control_status': 'passed'}, 'control'),
    ({'screen_role': 'PROSPECTIVE', 'control_status': 'negative-control'}, 'prospective'),
    ({'control_status': 'control passed'}, 'other'),
    ({'screen_role': 'uncontrolled'}, 'other'),
])
def test_roles_use_explicit_identity_before_legacy_status(fields, expected):
    assert screening_role_group(fields) == expected
    record = {'screening_result_id': 'role-test', 'molecule_id': 'MOLECULE-TEST', **fields}
    markup = presentation.render_screen_readout(builder, [record], {}, [])
    label = {'control': 'Reference controls', 'prospective': 'Prospective observations', 'other': 'Other imported observations'}[expected]
    assert f'<h3 class="screen-subheading">{label}</h3>' in markup
    assert markup.count('<table ') == 1


def test_readout_preserves_legacy_site_and_distinguishes_unrun_scores():
    record = {'screening_result_id': 'planned-test', 'molecule_id': 'MOLECULE-TEST',
              'screen_role': 'prospective', 'execution_state': 'planned',
              'site': 'Example legacy loop', 'pose_score': None,
              'seed_agreement': {'successful_comparable_seed_count': 1}}
    markup = presentation.render_screen_readout(builder, [record], {}, [])
    assert 'Example legacy loop' in markup
    assert 'Not computed' in markup
    assert '<h3>Primary screen: confirmation remains separate</h3>' not in markup
    record.update(execution_state='failed', failure_reason='<example failure>')
    markup = presentation.render_screen_readout(builder, [record], {}, [])
    assert 'No score recorded' in markup
    assert '&lt;example failure&gt;' in markup
    assert '<example failure>' not in markup
