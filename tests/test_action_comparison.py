from __future__ import annotations

import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from surface_atlas.action_comparison import SCHEMA_VERSION, build_action_comparison, render_action_comparison, validate_action_evidence

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'src/surface_atlas/assets/report/action-comparison.js'


def target(identifier, supported=()):
    return {'target_id': identifier, 'preferred_name': identifier, 'action_evidence': {
        'schema_version': SCHEMA_VERSION, 'target_id': identifier,
        'sources': [{'source_id': 'S-FIXTURE', 'citation': 'Invented assay observations for software tests.'}],
        'observations': {name: {'state': 'supported', 'basis': 'Synthetic controlled assay in the stated test context.', 'source_ids': ['S-FIXTURE']} for name in supported},
    }}


def fixture():
    return [target('T-A', ('surface_access', 'internalization', 'payload_response')),
            target('T-B', ('surface_access', 'partner_site_access', 'functional_blockade', 'tissue_contrast', 'tracer_retention')),
            {'target_id': 'T-UNKNOWN', 'evidence_score': {'score': 100}, 'risk': {'observed_signal_score': 0}, 'modality_fit': [{'score': 5}]}]


def node(script, payload):
    runtime = shutil.which('node')
    if runtime is None:
        pytest.skip('Node.js is required for JavaScript behavior tests')
    result = subprocess.run([runtime, '-e', 'const api=require(process.argv[1]); const data=JSON.parse(process.argv[2]); ' + script, str(JS), json.dumps(payload)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_action_changes_order_and_old_scores_do_not_substitute_for_evidence():
    data = build_action_comparison(fixture())
    result = node("console.log(JSON.stringify(Object.keys(data.actions).map(a=>api.ordered(data,a).map(r=>r.target_id))));", data)
    assert result == [['T-A', 'T-B', 'T-UNKNOWN'], ['T-B', 'T-A', 'T-UNKNOWN'], ['T-B', 'T-A', 'T-UNKNOWN']]
    unknown = data['records'][2]['evaluations']
    assert all(value['supported'] == 0 and value['missing'] == 3 for value in unknown.values())


def test_missing_is_not_a_favorable_tiebreaker_over_contradiction():
    records = [target('T-A'), target('T-Z')]
    records[0]['action_evidence']['observations']['surface_access'] = {'state': 'contradicted', 'basis': 'Synthetic binding was absent under the tested condition.', 'source_ids': ['S-FIXTURE']}
    data = build_action_comparison(records)
    result = node("console.log(JSON.stringify(api.ordered(data,'imaging').map(r=>r.target_id)));", data)
    assert result == ['T-A', 'T-Z']
    assert data['records'][0]['evaluations']['imaging']['contradicted'] == 1
    assert data['records'][1]['evaluations']['imaging']['missing'] == 3


@pytest.mark.parametrize('mutation', ['missing_source', 'unresolved_source', 'wrong_target', 'unknown_field', 'unknown_observation', 'unsupported_state', 'empty_basis', 'duplicate_source'])
def test_rejects_unsupported_claims_and_ambiguous_contract(mutation):
    record = target('T-A', ('surface_access',))
    evidence = record['action_evidence']
    observation = evidence['observations']['surface_access']
    if mutation == 'missing_source': observation['source_ids'] = []
    elif mutation == 'unresolved_source': observation['source_ids'] = ['NOT-THERE']
    elif mutation == 'wrong_target': evidence['target_id'] = 'T-B'
    elif mutation == 'unknown_field': evidence['efficacy_score'] = 100
    elif mutation == 'unknown_observation': evidence['observations']['safety'] = observation.copy()
    elif mutation == 'unsupported_state': observation['state'] = 'approved'
    elif mutation == 'empty_basis': observation['basis'] = ' '
    elif mutation == 'duplicate_source': evidence['sources'].append(evidence['sources'][0].copy())
    assert validate_action_evidence([record])
    with pytest.raises(ValueError):
        build_action_comparison([record])


def test_exact_target_ids_and_selected_action_survive_portable_request():
    data = build_action_comparison([target('T-A'), target('T-AA')])
    result = node("const text=api.request(data,'blockade',['T-AA']); console.log(JSON.stringify(JSON.parse(text.slice(text.indexOf('{')))));", data)
    assert result['action'] == 'blockade'
    assert result['selected_target_ids'] == ['T-AA']
    assert [row['target_id'] for row in result['targets']] == ['T-AA']
    errors = node("console.log(JSON.stringify([['T'],['T-AA','T-AA']].map(ids=>{try{api.request(data,'imaging',ids);return false;}catch(e){return true;}})));", data)
    assert errors == [True, True]
    with pytest.raises(ValueError, match='unique'):
        build_action_comparison([target('T-A'), target('T-A')])


def test_html_data_cannot_inject_markup_and_csv_formulas_are_neutralized():
    record = target('T-A', ('surface_access',))
    attack = '</section><script>alert(1)</script><img src=x onerror=alert(1)>'
    record['preferred_name'] = attack
    record['action_evidence']['observations']['surface_access']['basis'] = '=HYPERLINK("https://example.invalid")'
    record['action_evidence']['sources'][0]['citation'] = attack
    fragment = render_action_comparison([record], {'T-A': 'target-t-a.html'})
    class Parser(HTMLParser):
        tags = []
        payload = None
        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
            value = dict(attrs).get('data-action-comparison')
            if value: self.payload = json.loads(value)
    parsed = Parser(); parsed.feed(fragment)
    assert 'script' not in parsed.tags and 'img' not in parsed.tags
    assert parsed.payload['records'][0]['name'] == attack
    csv = node("console.log(JSON.stringify(api.csv(data,'imaging',['T-A'])));", parsed.payload)
    assert "'=HYPERLINK" in csv
    assert attack in csv
    with pytest.raises(ValueError, match='report-local'):
        render_action_comparison([record], {'T-A': 'javascript:alert(1)'})


def test_next_measurement_changes_with_missing_action_evidence():
    data = build_action_comparison([target('T-A', ('surface_access',))])
    evaluations = data['records'][0]['evaluations']
    assert 'uptake' in evaluations['payload-delivery']['next_measurement']
    assert 'partner site' in evaluations['blockade']['next_measurement']
    assert 'normal tissues' in evaluations['imaging']['next_measurement']
    assert all('adds one' in value['decision_sensitivity'] for value in evaluations.values())
    complete = build_action_comparison([fixture()[0]])['records'][0]['evaluations']['payload-delivery']
    assert 'removes one' in complete['decision_sensitivity']


def test_contract_schema_matches_valid_example():
    jsonschema = pytest.importorskip('jsonschema')
    schema = json.loads((ROOT / 'schemas/v0.1/action-evidence.schema.json').read_text())
    for record in fixture()[:2]:
        jsonschema.validate(record['action_evidence'], schema)
    invalid = copy.deepcopy(fixture()[0]['action_evidence'])
    invalid['observations']['surface_access']['source_ids'] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)
