"""Keep displayed scientific outcomes tied to the packaged observation."""
import copy
import json
import unittest
from pathlib import Path

from surface_atlas import report_builder as builder, report_presentation as presentation


class ResearchCasePresentationTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.collection = json.loads((root / 'examples/research-case/screening-results.json').read_text())
        self.records = self.collection['records']
        self.metadata = {key: value for key, value in self.collection.items() if key != 'records'}

    def test_record_confirmation_is_visible_without_claiming_run_confirmation(self):
        html = presentation.render_screen_provenance(builder, self.metadata, self.records)
        self.assertIn('Record confirmations', html)
        self.assertIn('Run confirmations', html)
        self.assertIn('Assessment passed', html)
        self.assertIn('same-protocol-confirmation-passed', html)
        self.assertIn('SR-FAP-6Y0F-356-smina-v1-NP011', html)
        self.assertNotIn('No confirmation context recorded', html)
        self.assertEqual(html.count('Assessment details ·'), 1)

    def test_embedded_assessment_is_retained_without_optional_run_metadata(self):
        html = presentation.render_screen_provenance(builder, {}, self.records)
        self.assertIn('same-protocol-confirmation-passed', html)
        self.assertNotIn('Source run', html)

    def test_unmatched_assessed_run_is_rejected_instead_of_silently_hidden(self):
        records = copy.deepcopy(self.records)
        records[0]['run_id'] = 'unregistered-run'
        with self.assertRaisesRegex(ValueError, 'each record must reference a source run'):
            presentation.render_screen_provenance(builder, self.metadata, records)

    def test_record_assessment_and_run_context_keep_distinct_scopes(self):
        metadata = copy.deepcopy(self.metadata)
        metadata['confirmation_context'] = {'state': 'run-confirmation-state', 'requested': 3}
        html = presentation.render_screen_provenance(builder, metadata, self.records)
        self.assertIn('run-confirmation-state', html)
        self.assertEqual(html.count('Assessment details ·'), 1)
        self.assertEqual(html.count('<summary>Confirmation context 1</summary>'), 1)

    def test_linked_pose_shows_its_seed_and_score_separately_from_primary_score(self):
        record = self.records[0]
        path = record['pose_artifact']['path']
        html = presentation.render_screen_readout(builder, self.records, {path: 'artifacts/egcg.sdf'}, [], self.metadata)
        self.assertIn('NP011-seed41-mode1', html)
        self.assertIn('-11.79', html)
        self.assertIn('Seed 11', html)
        self.assertIn('Top pose Vinardo -11.74094 kcal/mol', html)
        self.assertIn('nine-mode docked pose ensemble', html)
        self.assertIn('href="artifacts/egcg.sdf"', html)

    def test_pose_score_requires_a_matching_artifact_observation(self):
        record = copy.deepcopy(self.records[0])
        record['seed_observations'][1]['pose_artifact']['path'] = 'different.sdf'
        self.assertNotIn('Top pose Vinardo', presentation.saved_pose_context(record))


if __name__ == '__main__':
    unittest.main()
