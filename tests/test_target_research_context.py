"""Target dossiers must expose the scientific records packaged for that target."""
import json
import tempfile
import unittest
from pathlib import Path

from surface_atlas import report_builder as builder, report_presentation as presentation
from surface_atlas.report import build_report


class TargetResearchContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = Path(__file__).resolve().parents[1] / 'examples/research-case'
        cls.records = {r['gene_symbol']: r for r in json.loads((cls.example / 'targets.json').read_text())['records']}
        cls.temporary = tempfile.TemporaryDirectory()
        result = build_report(cls.example, output_root=Path(cls.temporary.name), run_id='target-context')
        cls.output = Path(result['run_directory'])

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def dossier(self, symbol):
        profile = builder.target_profile(self.records[symbol], 0)
        return (self.output / f'target-{profile["slug"]}.html').read_text()

    def test_target_dossier_contains_only_matched_binder_results(self):
        html = self.dossier('CEACAM5')
        self.assertIn('BoltzGen 03', html)
        self.assertIn('Shuffled tusamitamab VH', html)
        self.assertIn('Control assessment failed; no candidate was promoted.', html)
        self.assertIn('href="binders.html#designed-binders"', html)
        self.assertIn('href="binders.html#binder-controls"', html)
        self.assertIn('0.588', html)
        self.assertIn('0.765', html)
        for symbol in ('FAP', 'ITGB6'):
            self.assertNotIn('BoltzGen 03', self.dossier(symbol))
            self.assertNotIn('Shuffled tusamitamab VH', self.dossier(symbol))

    def test_cell_owner_measurements_reach_dossier_and_explorer(self):
        fap = self.records['FAP']
        context, values, measured, population, cohort = presentation.expression_summary(fap)
        self.assertEqual(cohort, 'COAD')
        self.assertEqual(population, 'Tumor cells')
        self.assertEqual(values['fibroblast'], 26.113207547169807)
        self.assertEqual(measured, 1.7048977061376318)
        html = presentation.render_dossier_context(builder, fap)
        self.assertIn('Tumor cells transcript detection', html)
        self.assertIn('26.11%', html)
        self.assertIn('1.7%', html)
        self.assertIn('recorded COAD cohort', html)
        self.assertIn('not verified cell ownership', html)
        projected = presentation.explorer_records([builder.target_profile(fap, 0)])[0]
        self.assertEqual(projected['expression'], measured)
        self.assertEqual(projected['cohort'], cohort)

    def test_population_summary_is_readable_and_missing_stays_unresolved(self):
        owner = builder.target_profile(self.records['FAP'], 0)['cell_owner']
        self.assertIn('stromal', owner)
        self.assertIn('fibroblast 26.11%', owner)
        self.assertNotIn('assignment_basis', owner)
        owner = builder.target_profile(self.records['CEACAM5'], 0)['cell_owner']
        self.assertIn('unresolved', owner)
        self.assertIn('transcript measurements unavailable', owner)
        self.assertNotIn('0%', owner)

    def test_warning_details_are_scoped_to_observed_signals(self):
        profile = builder.target_profile(self.records['FAP'], 0)
        self.assertEqual(profile['risk_label'], 'Recorded warning assessment')
        html = presentation.render_dossier_context(builder, self.records['FAP'])
        self.assertIn('Recorded warning signals', html)
        self.assertIn('tumor microenvironment sharing', html)
        self.assertIn('secreted or shed form', html)
        self.assertIn('fibroblast', html)
        self.assertIn('<dd>26.11%</dd>', html)
        self.assertIn('<dd>1.7%</dd>', html)
        self.assertNotIn('<dd>26.113207547169807</dd>', html)
        self.assertEqual(self.records['FAP']['cell_owner']['observed_percent_expressing']['fibroblast'], 26.113207547169807)
        self.assertNotIn('<dt>Normal-tissue risk</dt>', self.dossier('FAP'))
        explicit = builder.target_profile({'target_id': 'T', 'normal_tissue_risk': 'measured normal tissue'}, 0)
        self.assertEqual(explicit['risk_label'], 'Normal-tissue risk')

    def test_target_screen_title_includes_recorded_controls(self):
        html = self.dossier('FAP')
        self.assertIn('Molecular screening results', html)
        self.assertNotIn('Prospective molecule screens', html)
        self.assertIn('noncognate-control', html)
        self.assertIn('positive-control', html)

    def test_explicit_expression_context_retains_precedence(self):
        record = dict(self.records['FAP'], expression_context={
            'population_key': 'activated', 'population_label': 'Activated cells',
            'cohort_name': 'Alternate cohort', 'single_cell_percent_expressing': {'values': {'activated': 0}},
        })
        _, values, measured, population, cohort = presentation.expression_summary(record)
        self.assertEqual((values, measured, population, cohort), ({'activated': 0}, 0, 'Activated cells', 'Alternate cohort'))


if __name__ == '__main__':
    unittest.main()
