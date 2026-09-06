"""Build an entirely synthetic, deterministic offline walkthrough in a new atlas."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .action_comparison import SCHEMA_VERSION as ACTION_SCHEMA, validate_action_evidence
from .evidence_intake import SNAPSHOT_SCHEMA, compile_snapshots, reconcile_evidence
from .example import create_example
from .export import _rename_directory_exclusive
from .research_demo import write_synthetic_research_inputs
from .research_intake import import_assays, import_binder_runs
from .sequence_sites import SCHEMA_VERSION as SEQUENCE_SCHEMA, validate_sequence_sites
from .validator import validate_workspace


class TutorialError(ValueError):
    """The requested new tutorial could not be published safely."""


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _sequence_record(root: Path, target_id: str) -> dict:
    rows = ['REMARK   1 SYNTHETIC TOY COORDINATES ONLY; NO STRUCTURE PREDICTION OR EXPERIMENT.']
    atom_geometry = [('N', 'N', -1.3, 0., 0.), ('CA', 'C', 0., 0., 0.),
                     ('C', 'C', 1.45, .15, 0.), ('O', 'O', 2., 1.25, 0.),
                     ('CB', 'C', -.1, -1.5, 0.), ('SG', 'S', .7, -2.8, .7)]
    bond_rows = []
    serial = 0
    for residue, chain, number, insertion, offset in [('ALA', 'A', 10, '', -6.), ('CYS', 'A', 10, 'A', 0.), ('GLY', 'B', 1, '', 6.)]:
        indices = {}
        for name, element, x, y, z in atom_geometry[:{'ALA': 5, 'CYS': 6, 'GLY': 4}[residue]]:
            serial += 1
            indices[name] = serial
            atom_field = (' ' + name).ljust(4)
            rows.append(f'ATOM  {serial:5d} {atom_field} {residue:3s} {chain}{number:4d}{insertion:1s}   {x+offset:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00          {element:>2s}  ')
        for left, right in [('N', 'CA'), ('CA', 'C'), ('C', 'O'), ('CA', 'CB'), ('CB', 'SG')]:
            if left in indices and right in indices:
                bond_rows.append(f'CONECT{indices[left]:5d}{indices[right]:5d}')
    rows.extend(bond_rows)
    data = ('\n'.join(rows) + '\nEND\n').encode('ascii')
    coordinate = root / 'tutorial-inputs' / 'synthetic-author.pdb'
    coordinate.write_bytes(data)
    sequence = 'ACDEFGHIK' if target_id == 'T-EMBER' else 'ACD'
    return {
        'schema_version': SEQUENCE_SCHEMA, 'accession': target_id + '-SYNTHETIC', 'isoform': None,
        'source_id': 'tutorial-source-one', 'sequence': sequence, 'length': len(sequence),
        'sequence_sha256': hashlib.sha256(sequence.encode('ascii')).hexdigest(),
        'coordinate_model': 1, 'numbering': 'author',
        'coordinates': {'path': 'tutorial-inputs/synthetic-author.pdb', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'format': 'pdb'},
        'mappings': [{'canonical_position': 1, 'chain': 'A', 'author_residue_number': 10, 'insertion_code': ''},
                     {'canonical_position': 2, 'chain': 'A', 'author_residue_number': 10, 'insertion_code': 'A'}],
        'unresolved': [{'start': 3, 'end': len(sequence)}],
        'extracellular': [{'start': 1, 'end': len(sequence), 'label': 'Invented extracellular span; synthetic annotation only', 'source_id': 'tutorial-source-one'}],
        'partners': [{'partner_id': 'synthetic-partner', 'accession': 'TOY-1', 'label': 'Invented partner', 'chain': 'B'}],
    }


def _actions(target_id: str) -> dict:
    supported = {'T-EMBER': ['surface_access', 'internalization', 'payload_response'],
                 'T-LANTERN': ['surface_access', 'partner_site_access', 'functional_blockade', 'tissue_contrast', 'tracer_retention'],
                 'T-ORBIT': []}[target_id]
    observations = {key: {'state': 'supported', 'basis': 'Invented tutorial observation; no experiment or biological evidence.', 'source_ids': ['tutorial-action-fixture']} for key in supported}
    if target_id == 'T-EMBER':
        observations['functional_blockade'] = {'state': 'contradicted', 'basis': 'Invented contradiction exercises the decision display; no experiment.', 'source_ids': ['tutorial-action-fixture']}
    return {'schema_version': ACTION_SCHEMA, 'target_id': target_id,
            'sources': [{'source_id': 'tutorial-action-fixture', 'citation': 'Synthetic tutorial fixture generated offline; no external source or observation.'}],
            'observations': observations}


def _snapshot(query: str, records: list) -> dict:
    return {'schema_version': SNAPSHOT_SCHEMA, 'data_kind': 'synthetic',
            'source': {'source_id': 'tutorial-source-' + query, 'query_id': 'tutorial-query-' + query,
                       'title': 'Synthetic reviewed query ' + query, 'query': 'Invented local fixture census; no source retrieval',
                       'source_class': 'synthetic-fixture', 'retrieved_at': '2026-01-15T00:00:00Z',
                       'license': 'CC0-1.0 synthetic fixture', 'status': 'complete'}, 'records': records}


def _second_run(first_input: Path) -> Path:
    """Independent unevaluated run; no score or control pooling with run one."""
    second = _load(first_input)
    raw = b'SYNTHETIC TEST DATA ONLY. Independent run two and its controls were not run. No computation or assay occurred.\n'
    (first_input.parent / 'synthetic-second-source.txt').write_bytes(raw)
    artifact = {'path': 'synthetic-second-source.txt', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'storage': 'workspace'}
    def rebind(value):
        if isinstance(value, list):
            return [rebind(item) for item in value]
        if isinstance(value, dict):
            if 'artifact' in value and 'locator' in value:
                return {'artifact': copy.deepcopy(artifact), 'locator': 'line 1: independent synthetic not-run fixture'}
            return {key: rebind(item) for key, item in value.items()}
        return value
    second = rebind(second)
    run = second['records'][0]
    run.update(run_id='synthetic-run-2', campaign_id='synthetic-campaign-2', controls_status='not-run')
    run['generator'].update(name='synthetic-generator-two', version='test-2', seed=11)
    run['evaluation_protocol'].update(id='synthetic-protocol-two', version='test-2')
    for stage in run['stages']:
        stage.update(status='not-run', reason='Independent synthetic run two was not evaluated; no scores or control results exist.')
    for candidate in run['candidates']:
        candidate['candidate_id'] += '-run-two'
        candidate['construct_id'] += '-run-two'
        for observation in candidate['observations']:
            observation.update(observation_id=candidate['candidate_id'] + '-seed-11', seed=11, status='not-run', metrics={}, reason='Synthetic run two was not evaluated.')
        candidate['promotion'].update(decision='not-promoted', rationale='Independent synthetic controls were not run; advancement is unsupported.')
        if candidate['role'] != 'candidate':
            candidate.update(acceptance_status='not-run', acceptance_rule='Control must be evaluated under the independent protocol before any advancement.')
    path = first_input.parent / 'binder-runs-two.json'
    _write(path, second)
    return path


def create_tutorial(output_directory: str | Path) -> dict:
    """Publish a validated tutorial atomically; never overwrite an existing path."""
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise TutorialError('tutorial output must be a new directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.surface-atlas-tutorial-', dir=output.parent))
    root = staging / 'atlas'
    try:
        create_example(root)
        plan = _load(root / 'atlas-plan.json')
        atlas_id = plan['atlas_id']
        original = _load(root / 'targets.json')['records']
        rows = []
        for index, target in enumerate(original, 1):
            rows.append({'record_id': f'synthetic-record-{index}', 'entity_id': 'ENTITY-' + target['target_id'],
                         'preferred_name': target['preferred_name'], 'identifiers': {'synthetic': target['target_id']},
                         'reason': 'Reviewed invented surface annotation; synthetic illustration only.',
                         'locator': f'fixture row {index}', 'disposition': 'surface-target', 'target': target})
        for index, disposition in [(4, 'excluded-from-surface-universe'), (5, 'unresolved')]:
            rows.append({'record_id': f'synthetic-record-{index}', 'entity_id': f'ENTITY-SYNTHETIC-{index}',
                         'preferred_name': 'Invented intracellular entity' if index == 4 else 'Invented unresolved entity',
                         'identifiers': {'synthetic': f'SYNTHETIC-{index}'}, 'reason': 'Invented exclusion basis' if index == 4 else 'No reviewed surface basis in this synthetic fixture',
                         'locator': f'fixture row {index}', 'disposition': disposition})
        inputs = root / 'tutorial-inputs'
        inputs.mkdir()
        _write(inputs / 'query-one.json', _snapshot('one', rows[:2] + [rows[3]]))
        duplicate = copy.deepcopy(rows[0]); duplicate['record_id'] = 'synthetic-repeat-1'; duplicate['locator'] = 'fixture repeat row 1'
        _write(inputs / 'query-two.json', _snapshot('two', [duplicate, rows[2], rows[4]]))
        compiled = compile_snapshots([inputs / 'query-one.json', inputs / 'query-two.json'], atlas_id)
        for relative, data in compiled['snapshots'].items():
            path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        for filename, document in compiled['documents'].items():
            _write(root / filename, document)
        targets = _load(root / 'targets.json')
        for target in targets['records']:
            target['action_evidence'] = _actions(target['target_id'])
            if target['target_id'] in {'T-EMBER', 'T-LANTERN'}:
                target['sequence_sites'] = _sequence_record(root, target['target_id'])
        _write(root / 'targets.json', targets)
        plan['scope']['coverage_claim'] = compiled['documents']['search-ledger.json']['coverage_state']
        _write(root / 'atlas-plan.json', plan)
        research = write_synthetic_research_inputs(inputs / 'research', atlas_id, 'T-EMBER')
        second_run = _second_run(research['binder_runs'])
        import_binder_runs([research['binder_runs'], second_run], root, staging / 'binder-bundle')
        shutil.copytree(staging / 'binder-bundle', root, dirs_exist_ok=True)
        import_assays(research['assay_results'], root, staging / 'assay-bundle')
        shutil.copytree(staging / 'assay-bundle', root, dirs_exist_ok=True)
        # Keep the synthetic designation explicit in every generated collection.
        for path in root.glob('*.json'):
            document = _load(path)
            document['data_kind'] = 'synthetic'
            _write(path, document)
        expected = {'data_kind': 'synthetic', 'network_or_provider_calls': False, 'counts': compiled['counts'],
                    'action_first': {'payload-delivery': 'T-EMBER', 'blockade': 'T-LANTERN', 'imaging': 'T-LANTERN'},
                    'sequence_site': {'target_id': 'T-EMBER', 'canonical_interval': [2, 3], 'fasta_sequence': 'CD', 'verified_author_residues': ['A:10A'], 'unresolved_canonical_positions': [3], 'partner_id': 'synthetic-partner', 'partner_chain': 'B'},
                    'binder_runs': 2, 'candidates': 4, 'binder_controls': {'synthetic-run-1': 'failed', 'synthetic-run-2': 'not-run'}, 'promotion': 'not-promoted',
                    'assay_results': 1, 'assay_endpoint': 'IC50', 'assay_relation': '>', 'assay_value': 100.0, 'assay_unit': 'nM',
                    'assay_controls': 'failed', 'missing_replicates': 1,
                    'claim_ceiling': 'Synthetic illustration only. No computation or laboratory experiment was performed. Failed controls and censored readings do not support candidate advancement or efficacy claims.'}
        _write(root / 'expected-results.json', expected)
        (root / 'README.md').write_text(TUTORIAL_README, encoding='utf-8')
        errors = validate_sequence_sites(root, targets) + validate_action_evidence(targets)
        result = validate_workspace(root)
        errors.extend(result.get('errors', []))
        if errors or not result.get('valid'):
            raise TutorialError('tutorial validation failed: ' + '; '.join(errors))
        reconciliation = reconcile_evidence(root)
        if not reconciliation.get('consistent'):
            raise TutorialError('tutorial evidence reconciliation failed')
        _rename_directory_exclusive(root, output)
        return {'directory': str(output.resolve()), 'atlas_id': atlas_id, 'data_kind': 'synthetic', 'counts': compiled['counts'], 'network_or_provider_calls': False}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


TUTORIAL_README = '''# Synthetic offline tutorial

All records are invented. No model computation, source retrieval, laboratory
experiment or clinical action was performed. This atlas exercises preservation
and inspection of evidence records; it makes no biological claim.

From the directory containing this atlas (called `tutorial` below):

```sh
surface-atlas validate tutorial --json
surface-atlas report tutorial --output-root reports --run-id tutorial --json
```

The source inputs are `tutorial-inputs/query-one.json` and `query-two.json`.
The research inputs are `tutorial-inputs/research/binder-runs.json` and
`tutorial-inputs/research/assay-results.json`. Their associated source artifact
is local. Recreate everything offline with `surface-atlas tutorial tutorial-new`.

Expected census: 6 raw records, 1 duplicate, 5 unique entities, 3 retained
targets, 1 excluded entity and 1 unresolved entity. Coverage is complete only
within these two invented reviewed queries. Retained target IDs remain
T-EMBER, T-LANTERN and T-ORBIT; existing screens and opportunities use those IDs.

On the Sequence sites page select Ember canonical positions 2–3. The exact
FASTA is CD; only C maps to author chain A residue 10 insertion code A. Position
3 is unresolved and must not appear in 3D. The partner is synthetic-partner,
author chain B. Switch to Lantern and back: the Ember interval and partner
checkbox remain unchanged. Download FASTA and review the Codex request for
accession, numbering, mapping and source hashes.

On Action comparison, Ember leads payload delivery while Lantern leads blockade
and imaging. This ordering counts supplied supporting criteria only; it is not
an efficacy or safety ranking. Orbit has missing evidence and receives no
automatic suitability credit.

Campaigns shows two independent synthetic runs, each with one candidate and one
negative control. Run one has a failed control; run two and its controls were
not run. Protocols and seeds remain distinct and scores are never pooled.
Neither candidate is promoted. Assays shows one synthetic
IC50 reading >100 nM, a failed control and one missing replicate. Keep the bound,
units and missing value; do not convert the bound to an exact measurement or
advance the candidate. No therapeutic conclusion follows from this fixture.

`expected-results.json` records these exact checkpoints for automated checks.
'''
