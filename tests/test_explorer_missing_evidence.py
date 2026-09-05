"""Missing measurements remain visible when evidence is projected into the explorer."""
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from surface_atlas import report_builder as builder, report_presentation as presentation


ROOT = Path(__file__).resolve().parents[1]


def research_targets():
    return json.loads((ROOT / 'examples/research-case/targets.json').read_text())['records']


def test_all_example_missing_components_appear_as_gaps_without_mutation():
    targets = research_targets()
    before = copy.deepcopy(targets)
    projected = presentation.explorer_records([builder.target_profile(record, i) for i, record in enumerate(targets)])
    for source, record in zip(targets, projected):
        missing = [c['component'] for c in source['evidence_score']['components'] if c['state'] == 'not-measured']
        assert missing
        for component in missing:
            assert component + ' — not measured' in record['gaps']
        assert record['missingDataRule'] == source['evidence_score']['missing_data_rule']
    assert targets == before


def test_zero_points_without_explicit_missing_state_do_not_create_a_gap():
    record = {'target_id': 'T', 'risk': {'unresolved_dimensions': ['surface-density']},
              'evidence_score': {'components': [
                  {'component': 'measured-zero', 'state': 'observed', 'points': 0},
                  {'component': 'unclassified-zero', 'points': 0},
              ]}}
    projected = presentation.explorer_records([builder.target_profile(record, 0)])[0]
    assert projected['gaps'] == ['surface-density']


def test_actual_explorer_script_displays_missing_state_and_rule():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to exercise the explorer renderer')
    target = next(record for record in research_targets() if record['gene_symbol'] == 'CEACAM5')
    records = presentation.explorer_records([builder.target_profile(target, 0)])
    harness = r'''
const fs = require('fs'), vm = require('vm');
const records = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor() { this.innerHTML = ''; this.textContent = ''; this.value = ''; this.children = []; }
  querySelectorAll() { return []; }
  addEventListener() {}
  appendChild(child) { this.children.push(child); }
  scrollIntoView() {}
}
const ids = new Map();
const document = {
  readyState: 'complete', querySelectorAll: () => [], querySelector: () => null,
  createElement: () => new Element(),
  getElementById: id => { if (!ids.has(id)) ids.set(id, new Element()); return ids.get(id); }
};
document.getElementById('atlas-explorer-data').textContent = JSON.stringify(records);
const context = {document, window: {addEventListener() {}},
  location: {search: '', hash: '', href: 'http://localhost/explore.html'},
  history: {replaceState() {}}, URL, URLSearchParams};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const selected = document.getElementById('atlas-selection');
process.stdout.write(JSON.stringify({main: selected.innerHTML, details: selected.children.map(x => x.innerHTML)}));
'''
    result = subprocess.run([node, '-e', harness, str(ROOT / 'src/surface_atlas/assets/report/presentation.js')],
                            input=json.dumps(records), text=True, capture_output=True, check=True)
    rendered = json.loads(result.stdout)
    assert 'tcsa single cell context — not measured' in rendered['main']
    assert 'No unresolved measurements listed' not in rendered['main']
    assert '0 / 15 · not measured' in rendered['details'][0]
    assert target['evidence_score']['missing_data_rule'] in rendered['details'][0]


def test_disease_context_fallback_does_not_deny_recorded_association_evidence():
    record = next(record for record in research_targets() if record['gene_symbol'] == 'CEACAM5')
    profile = builder.target_profile(record, 0)
    html = builder.render_target_dossier(profile, {}, {})
    assert '<dt>Disease context</dt>' in html
    assert '<dt>Disease evidence</dt><dd>Not recorded</dd>' not in html
    assert 'open targets disease association' in html
    explicit = builder.target_profile({'target_id': 'T', 'disease_evidence': 'Recorded association'}, 0)
    assert explicit['disease_evidence_label'] == 'Disease evidence'
    assert explicit['disease_evidence'] == 'Recorded association'
