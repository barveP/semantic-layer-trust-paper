"""Annotation input checks for duplicated, mismatched and inapplicable judgments."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('intake', ROOT / 'audit-site/intake.py')
intake = importlib.util.module_from_spec(spec); spec.loader.exec_module(intake)


class AnnotationInputs(unittest.TestCase):
    def setUp(self):
        with intake.RATINGS.open(newline='') as stream:
            self.rows = list(csv.DictReader(stream))

    def load(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ratings.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=self.rows[0].keys())
                writer.writeheader(); writer.writerows(rows)
            return intake.load_rows(ratings_path=path)

    def test_complete_key_preserves_notes(self):
        loaded = self.load(self.rows)
        self.assertEqual(len(loaded), 417)
        self.assertEqual([r['note'] for r in loaded], [r['note'] for r in self.rows])

    def test_duplicate_item_rejected(self):
        with self.assertRaises(ValueError):
            self.load(self.rows + [self.rows[0]])

    def test_wrong_trial_rejected(self):
        self.rows[0]['trial_id'] = self.rows[1]['trial_id']
        with self.assertRaises(ValueError):
            self.load(self.rows)

    def test_inapplicable_fault_answer_rejected(self):
        next(row for row in self.rows if row['identifies_fault'] == 'na')['identifies_fault'] = 'yes'
        with self.assertRaises(ValueError):
            self.load(self.rows)


if __name__ == '__main__':
    unittest.main()
