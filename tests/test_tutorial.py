from __future__ import annotations

import hashlib
import json
import html
from pathlib import Path

import pytest

from surface_atlas.action_comparison import build_action_comparison
from surface_atlas.evidence_intake import compile_snapshots, reconcile_evidence
from surface_atlas.research_intake import validate_optional_research
from surface_atlas.sequence_sites import validate_sequence_sites
from surface_atlas.tutorial import TutorialError, create_tutorial
from surface_atlas.validator import validate_workspace


def read(root: Path, name: str):
    return json.loads((root / name).read_text())


def inventory(root: Path):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_complete_tutorial_is_valid_deterministic_and_reconciled(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    result = create_tutorial(first)
    create_tutorial(second)
    assert inventory(first) == inventory(second)
    assert result['counts'] == {'raw_records': 6, 'duplicate_records': 1, 'normalized_discovered_entities': 5,
                                'surface_targets': 3, 'excluded_from_surface_universe': 1, 'unresolved_records': 1}
    assert result['network_or_provider_calls'] is False
    assert validate_workspace(first)['valid']
    assert reconcile_evidence(first)['consistent']
    targets = read(first, 'targets.json')
    assert validate_sequence_sites(first, targets) == []
    assert validate_optional_research(first, result['atlas_id'], targets) == []
    for path in first.glob('*.json'):
        assert read(first, path.name)['data_kind'] == 'synthetic'
    compiled = compile_snapshots([first / 'tutorial-inputs/query-two.json', first / 'tutorial-inputs/query-one.json'], result['atlas_id'])
    assert compiled['counts'] == result['counts']
    assert read(first, 'search-ledger.json') == compiled['documents']['search-ledger.json']
    assert {row['target_id'] for row in targets['records']} == {'T-EMBER', 'T-LANTERN', 'T-ORBIT'}


def test_tutorial_exact_site_action_order_and_assay_ceilings(tmp_path):
    root = tmp_path / 'tutorial'; create_tutorial(root)
    targets = read(root, 'targets.json')
    expected = read(root, 'expected-results.json')
    comparison = build_action_comparison(targets)
    for action, first in expected['action_first'].items():
        ordered = sorted(comparison['records'], key=lambda row: (-row['evaluations'][action]['supported'], row['target_id']))
        assert ordered[0]['target_id'] == first
    ember = next(t for t in targets['records'] if t['target_id'] == 'T-EMBER')['sequence_sites']
    assert ember['sequence'][1:3] == 'CD'
    assert ember['mappings'][1] == {'canonical_position': 2, 'chain': 'A', 'author_residue_number': 10, 'insertion_code': 'A'}
    assert ember['unresolved'] == [{'start': 3, 'end': 9}]
    pdb=(root/'tutorial-inputs/synthetic-author.pdb').read_text().splitlines()
    cys={int(line[6:11]):line[12:16].strip() for line in pdb if line.startswith('ATOM  ') and line[17:20]=='CYS' and line[21:27]=='A  10A'}
    assert set(cys.values()) == {'N', 'CA', 'C', 'O', 'CB', 'SG'}
    bonds=[(int(line[6:11]),int(line[11:16])) for line in pdb if line.startswith('CONECT')]
    assert sum(left in cys and right in cys for left,right in bonds) == 5
    runs = read(root, 'binder-runs.json')['records']
    assert len(runs) == 2
    run, second = runs
    assert run['evaluation_protocol']['id'] != second['evaluation_protocol']['id']
    assert run['generator']['seed'] != second['generator']['seed']
    assert second['controls_status'] == 'not-run'
    assert all(o['metrics'] == {} and o['status'] == 'not-run' for c in second['candidates'] for o in c['observations'])
    assay = read(root, 'assay-results.json')['records'][0]
    assert run['controls_status'] == 'failed'
    assert all(c['promotion']['decision'] == 'not-promoted' for c in run['candidates'])
    assert assay['reading']['relation'] == '>' and assay['reading']['value'] == 100.0 and assay['reading']['unit'] == 'nM'
    assert assay['controls'][0]['acceptance_status'] == 'failed'
    assert assay['replicates'][0]['reading']['value'] is None
    assert 'No computation or laboratory experiment was performed' in expected['claim_ceiling']
    assert all(not p.is_symlink() for p in root.rglob('*'))


def test_tutorial_never_overwrites_and_failure_is_atomic(tmp_path, monkeypatch):
    root = tmp_path / 'tutorial'; root.mkdir(); (root / 'keep.txt').write_text('keep')
    with pytest.raises(TutorialError):
        create_tutorial(root)
    assert (root / 'keep.txt').read_text() == 'keep'
    broken = tmp_path / 'broken'; broken.symlink_to(tmp_path / 'absent')
    with pytest.raises(TutorialError):
        create_tutorial(broken)
    output = tmp_path / 'failure'
    monkeypatch.setattr('surface_atlas.tutorial.validate_workspace', lambda _: {'valid': False, 'errors': ['synthetic forced failure']})
    with pytest.raises(TutorialError, match='forced failure'):
        create_tutorial(output)
    assert not output.exists()
    assert not list(tmp_path.glob('.surface-atlas-tutorial-*'))


def test_tutorial_cli_report_preserves_reader_facts_and_packaged_sources(tmp_path, capsys):
    from surface_atlas.cli import main
    root = tmp_path / 'tutorial'
    assert main(['tutorial', str(root), '--json']) == 0
    created = json.loads(capsys.readouterr().out)
    assert created['counts']['normalized_discovered_entities'] == 5
    assert main(['validate', str(root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['valid']
    assert main(['report', str(root), '--output-root', str(tmp_path / 'reports'), '--run-id', 'tutorial', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    report = Path(result['run_directory'])
    for name in ['sequence-sites.html', 'action-comparison.html', 'campaigns.html', 'assays.html']:
        assert (report / name).is_file()
    for path in report.glob('*.html'):
        text = path.read_text()
        assert 'synthetic' in text.lower()
        assert str(root) not in text and '/Users/' not in text
    sequence_page = html.unescape((report / 'sequence-sites.html').read_text())
    assert 'ACDEFGHIK' in sequence_page and '"insertion_code":"A"' in sequence_page
    assert 'data/artifacts/tutorial-inputs/synthetic-author.pdb' in sequence_page
    assert (report / 'data/artifacts/tutorial-inputs/synthetic-author.pdb').read_bytes() == (root / 'tutorial-inputs/synthetic-author.pdb').read_bytes()
    campaigns = html.unescape((report / 'campaigns.html').read_text())
    assert 'synthetic-run-1' in campaigns and 'synthetic-run-2' in campaigns
    assert 'failed' in campaigns and 'not-run' in campaigns
    assays = html.unescape((report / 'assays.html').read_text())
    assert 'IC50' in assays and 'nM' in assays and '100' in assays
    assert 'failed' in assays and ('not-measured' in assays or 'Not measured' in assays)
