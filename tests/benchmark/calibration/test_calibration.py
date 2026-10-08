from hashlib import sha256
from pathlib import Path
from decimal import Decimal
import json
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'benchmark/calibration'))
from oracle import reference, adjudicate  # noqa: E402
from manual_expected import compute as independent_compute  # noqa: E402


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = yaml.safe_load((ROOT / 'benchmark/calibration/CALIBRATION_PACK_V0_1.yaml').read_text(encoding='utf-8'))
        cls.results = json.loads((ROOT / 'artifacts/stage_c1/C1-01/baseline_results.json').read_text(encoding='utf-8'))

    def test_nine_unique_public_cases_and_frozen_references(self):
        cases = self.pack['cases']
        self.assertEqual(len(cases), 9)
        self.assertEqual(len({x['case_id'] for x in cases}), 9)
        self.assertEqual(len({x['task_spec_ref'] for x in cases}), 9)
        self.assertTrue(all(x['exposure'] == 'PUBLIC_CALIBRATION' for x in cases))
        self.assertFalse(self.pack['hidden_score_eligibility'])
        for case in cases:
            spec = yaml.safe_load((ROOT / case['task_spec_ref']).read_text(encoding='utf-8'))
            manifest = yaml.safe_load((ROOT / case['oracle_manifest_ref']).read_text(encoding='utf-8'))
            self.assertEqual(spec['task_id'], case['case_id'])
            self.assertEqual(spec['sealed_partition'], None)
            self.assertEqual(manifest['shared_truth_dependency_list'], [])
            for kind in ('generator', 'oracle'):
                path = ROOT / manifest[f'{kind}_ref']
                self.assertEqual(sha256(path.read_bytes()).hexdigest(), manifest[f'{kind}_sha256'])
            self.assertEqual(sha256((ROOT / case['fixture_ref']).read_bytes()).hexdigest(), manifest['fixture_sha256'])
        for paper in ('P10', 'P20'):
            manifest = yaml.safe_load((ROOT / f'benchmark/calibration/REFERENCE_{paper}.yaml').read_text(encoding='utf-8'))
            self.assertEqual(sha256((ROOT / manifest['source_file']).read_bytes()).hexdigest(), manifest['source_sha256'])
            self.assertEqual(manifest['QUANT_RSI_CONCEPT_ADAPTATION']['replication_label'], 'CONCEPT_REPLICATION_ONLY_NOT_EXACT_PAPER_REPLICATION')

    def test_hand_computed_cases_and_perturbations(self):
        expected = {
            'CAL-T1-FIELD': {'base': ('REFUSE', 'PIT_DATA_BOUNDARY'), 'positive': ('PROMOTE', None), 'transfer': ('PROMOTE', None)},
            'CAL-T1-REVISION': {'base': ('REFUSE', 'PIT_DATA_BOUNDARY'), 'positive': ('PROMOTE', None), 'transfer': ('PROMOTE', None)},
            'CAL-T2-P10': {'base': ('PROMOTE', None), 'positive': ('PROMOTE', None), 'negative': ('REFUSE', 'PIT_DATA_BOUNDARY')},
            'CAL-T2-P20': {'base': ('PROMOTE', None), 'positive': ('PROMOTE', None), 'negative': ('REFUSE', 'PIT_DATA_BOUNDARY')},
            'CAL-T3-NULL-A': {'base': ('REFUSE', 'EVALUATOR_GATE'), 'positive': ('PROMOTE', None), 'transfer': ('REFUSE', 'EVALUATOR_GATE')},
            'CAL-T3-NULL-B': {'base': ('REFUSE', 'EVALUATOR_GATE'), 'positive': ('PROMOTE', None), 'transfer': ('REFUSE', 'EVALUATOR_GATE')},
            'CAL-T3-COST': {'base': ('REFUSE', 'EXECUTION_BOUNDARY'), 'positive': ('PROMOTE', None), 'transfer': ('REFUSE', 'EXECUTION_BOUNDARY')},
            'CAL-T3-DECAY': {'base': ('REFUSE', 'EVALUATOR_GATE'), 'positive': ('PROMOTE', None), 'transfer': ('REFUSE', 'EVALUATOR_GATE')},
            'CAL-T3-EXECUTION': {'base': ('REFUSE', 'EXECUTION_BOUNDARY'), 'positive_suspension': ('PROMOTE', None), 'positive_limit': ('PROMOTE', None), 'positive_t_plus_one': ('PROMOTE', None)},
        }
        for case_id, variants in expected.items():
            data = json.loads((ROOT / f'benchmark/calibration/fixtures/{case_id}.json').read_text(encoding='utf-8'))['variants']
            self.assertEqual(set(data), set(variants))
            for variant, (terminal, layer) in variants.items():
                result = reference(case_id, data[variant])
                self.assertEqual((result['terminal'], result['expected_rejection_layer']), (terminal, layer), (case_id, variant))
        p10 = json.loads((ROOT / 'benchmark/calibration/fixtures/CAL-T2-P10.json').read_text(encoding='utf-8'))['variants']
        self.assertEqual(reference('CAL-T2-P10', p10['base'])['evidence']['winner_id'], 'S09')
        self.assertEqual(reference('CAL-T2-P10', p10['positive'])['evidence']['winner_id'], 'S08')
        self.assertEqual(reference('CAL-T2-P10', p10['base'])['evidence']['gross_return'],
                         str((Decimal(5) / Decimal(128)).quantize(Decimal('0.000001'))))
        p20 = json.loads((ROOT / 'benchmark/calibration/fixtures/CAL-T2-P20.json').read_text(encoding='utf-8'))['variants']
        self.assertEqual(reference('CAL-T2-P20', p20['base'])['evidence']['long_ids'], ['A'])
        self.assertEqual(reference('CAL-T2-P20', p20['positive'])['evidence']['long_ids'], ['A', 'B'])
        self.assertEqual(reference('CAL-T2-P20', p20['base'])['evidence']['gross_return'],
                         str((Decimal(5) / Decimal(113) / 2).quantize(Decimal('0.000001'))))
        self.assertEqual(reference('CAL-T2-P20', p20['positive'])['evidence']['gross_return'],
                         str(((Decimal(5) / Decimal(113) + Decimal(5) / Decimal(89)) / 2).quantize(Decimal('0.000001'))))
        self.assertEqual(p20['positive']['next_open'], p20['base']['next_open'])
        self.assertEqual(p20['positive']['exit_close'], p20['base']['exit_close'])
        self.assertEqual(reference('CAL-T3-COST', {'gross_pnl': '12', 'roundtrip_cost': '8'})['evidence']['net_pnl'], '4')

    def test_independent_frozen_oracle_results_and_new_inputs(self):
        independent_path = ROOT / self.pack['independent_expected_ref']
        self.assertEqual(sha256(independent_path.read_bytes()).hexdigest(), self.pack['independent_expected_sha256'])
        expected = json.loads(independent_path.read_text(encoding='utf-8'))
        self.assertEqual(set(expected), {case['case_id'] for case in self.pack['cases']})
        for case_id, outcomes in expected.items():
            fixture = json.loads((ROOT / f'benchmark/calibration/fixtures/{case_id}.json').read_text(encoding='utf-8'))['variants']
            for variant, frozen in outcomes.items():
                self.assertEqual(reference(case_id, fixture[variant]), frozen, (case_id, variant))
            if 'NULL' in case_id:
                self.assertEqual(len(set(fixture['base']['labels'])), 2)
                self.assertEqual(len(set(fixture['transfer']['labels'])), 2)
                self.assertNotEqual(fixture['base']['features'], fixture['transfer']['features'])
                self.assertNotEqual(fixture['base']['seed'], fixture['transfer']['seed'])
        field = {'decision_at': 20, 'available_at': 19, 'value': 31}
        self.assertEqual(reference('CAL-T1-FIELD', field),
                         {'terminal': 'PROMOTE', 'reason': None, 'evidence': {'observed_value': 31}, 'expected_rejection_layer': None})
        cost = {'gross_pnl': '27', 'roundtrip_cost': '29'}
        self.assertEqual(reference('CAL-T3-COST', cost)['reason'], 'NET_NONPOSITIVE')
        mutations = {
            'CAL-T1-FIELD': {'decision_at': 20, 'available_at': 21, 'value': 31},
            'CAL-T1-REVISION': {'decision_at': 20, 'revision_available_at': 19, 'revised_value': 31},
            'CAL-T2-P10': {**json.loads((ROOT / 'benchmark/calibration/fixtures/CAL-T2-P10.json').read_text(encoding='utf-8'))['variants']['base'],
                           'eligible_ids': [f'S{i:02d}' for i in range(8)]},
            'CAL-T2-P20': {**json.loads((ROOT / 'benchmark/calibration/fixtures/CAL-T2-P20.json').read_text(encoding='utf-8'))['variants']['base'],
                           'monthly_closes': {'A': [100] * 12 + [80], 'B': list(range(100, 87, -1))}},
            'CAL-T3-NULL-A': {'features': [0, 1, 2, 3], 'labels': [0, 1, 0, 1]},
            'CAL-T3-NULL-B': {'features': [0, 1, 2, 3], 'labels': [0, 0, 1, 1]},
            'CAL-T3-COST': cost,
            'CAL-T3-DECAY': {'early_effect': ['0.03'] * 4, 'late_effect': ['0.03'] * 4, 'retirement_threshold': '0.02'},
            'CAL-T3-EXECUTION': {'execution_session': 20, 'orders': [{'id': 'fresh', 'side': 'buy',
                                    'suspended': False, 'limit_locked': False, 'acquired_session': None}]},
        }
        for case_id, data in mutations.items():
            self.assertEqual(reference(case_id, data), independent_compute(case_id, data), case_id)

    def test_baselines_and_denominator(self):
        summary = self.results['policies']
        total = summary['ScriptedReferenceControl']['assigned_denominator']
        self.assertGreater(total, 9)
        self.assertEqual(summary['ScriptedReferenceControl']['full_pass'], total)
        self.assertEqual(summary['MissingOutput']['assigned_denominator'], total)
        self.assertEqual(summary['MissingOutput']['full_pass'], 0)
        for name in ('AlwaysRefuse', 'AlwaysPromote', 'ContractOnly'):
            self.assertEqual(summary[name]['assigned_denominator'], total)
            self.assertLess(summary[name]['full_pass'], total)
            self.assertTrue(any(row['policy'] == name and not row['adjudication']['full_pass'] for row in self.results['rows']))
        self.assertFalse(adjudicate('CAL-T1-FIELD', {'decision_at': 1, 'available_at': 2, 'value': 7}, None)['full_pass'])
        self.assertEqual(adjudicate('CAL-T1-FIELD', {'decision_at': 1, 'available_at': 2, 'value': 7},
                                    {'terminal': 'PROMOTE', 'evidence': {}})['assigned_denominator'], 1)
        self.assertEqual(self.results['provider_calls'], 0)
        for malformed in ({'terminal': 'REFUSE', 'reason': 'FUTURE_FIELD'},
                          {'terminal': 'REFUSE', 'reason': 'FUTURE_FIELD', 'evidence': {}, 'expected_rejection_layer': 'EVALUATOR_GATE'}):
            self.assertFalse(adjudicate('CAL-T1-FIELD', {'decision_at': 1, 'available_at': 2, 'value': 7}, malformed)['full_pass'])
        self.assertEqual(summary['AlwaysRefuse']['positive_coverage'], 0)
        self.assertEqual(summary['AlwaysRefuse']['unjustified_refusals'], summary['AlwaysRefuse']['required_positive'])
        self.assertGreater(summary['AlwaysPromote']['known_null_false_positives'], 0)
        self.assertLess(summary['AlwaysPromote']['correct_promotions'], summary['AlwaysPromote']['promoted_count'])


if __name__ == '__main__':
    unittest.main()
