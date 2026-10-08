import json
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from quant_rsi.benchmark_public.adapter import run_public  # noqa: E402
from quant_rsi.ledger.store import TraceStore  # noqa: E402


class PublicPilotTests(unittest.TestCase):
    def test_four_tiers_transfer_and_canonical_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            for tier, variants in (('T1', ('base', 'transfer')),
                                   ('T2', ('base', 'positive')),
                                   ('T3', ('base', 'transfer')),
                                   ('T4', ('base', 'transfer'))):
                for variant in variants:
                    path = Path(temp) / f'{tier}-{variant}'
                    result = run_public(tier=tier, variant=variant,
                                        policy='correct', output_root=path)
                    self.assertTrue(result['oracle']['full_pass'], (tier, variant))
                    self.assertEqual(result['oracle']['assigned_denominator'], 1)
                    self.assertEqual(result['scientific_candidate_variants'], 0)
                    self.assertEqual(result['evidence']['candidate_id'], result['candidate']['candidate_id'])
                    self.assertEqual(result['evidence']['public_input_sha256'], result['release_sha256'])
                    self.assertGreaterEqual(result['cost']['wall_ms'], 1)
                    self.assertGreaterEqual(result['cost']['oracle_eval_ns'], 0)
                    self.assertIsNone(result['cost']['process_memory_bytes'])
                    release = json.loads((path / 'public-input.json').read_text(encoding='utf-8'))
                    self.assertNotIn('variant', release)
                    self.assertNotIn('oracle', release)
                    self.assertNotIn('seed', release['public_input'])
                    kinds = [event['kind'] for event in TraceStore(path / 'trace.sqlite').read()]
                    self.assertIn('CONDITION_REGISTERED', kinds)
                    self.assertIn('RUN_REGISTERED', kinds)
                    self.assertIn('PUBLIC_RELEASE', kinds)
                    self.assertIn('ATTEMPT_STARTED', kinds)
                    self.assertIn('ATTEMPT_SETTLED', kinds)
                    self.assertLess(kinds.index('ATTEMPT_STARTED'), kinds.index('ATTEMPT_SETTLED'))

    def test_five_t4_terminal_paths_keep_denominator(self):
        policies = ('correct', 'fabricated_evidence', 'unjustified_refusal',
                    'invalid_format', 'timeout')
        with tempfile.TemporaryDirectory() as temp:
            results = {}
            for policy in policies:
                path = Path(temp) / policy
                results[policy] = run_public(tier='T4', variant='base', policy=policy,
                                             output_root=path)
                self.assertEqual(results[policy]['oracle']['assigned_denominator'], 1)
                self.assertEqual(results[policy]['scientific_candidate_variants'], 0)
                terminal = [e for e in TraceStore(path / 'trace.sqlite').read()
                            if e['kind'] == 'ATTEMPT_SETTLED'][0]
                self.assertEqual(terminal['payload']['status'],
                                 'TIMEOUT' if policy == 'timeout' else 'SUCCEEDED')
            self.assertTrue(results['correct']['oracle']['full_pass'])
            for policy in policies[1:]:
                self.assertFalse(results[policy]['oracle']['full_pass'], policy)
            self.assertFalse(results['fabricated_evidence']['oracle']['score_components']['provenance'])
            self.assertFalse(results['unjustified_refusal']['oracle']['terminal_correct'])

    def test_nine_calibration_slots_t4_development(self):
        pack = yaml.safe_load((ROOT / 'benchmark/calibration/CALIBRATION_PACK_V0_1.yaml').read_text(encoding='utf-8'))
        pilot = yaml.safe_load((ROOT / 'benchmark/public_oracle_pilot/PROTOTYPES.yaml').read_text(encoding='utf-8'))
        self.assertEqual(pack['case_count'], 9)
        self.assertEqual(len(pilot['prototypes']), 4)
        self.assertNotIn('DEV-T4-EXPLANATION', {row['case_id'] for row in pack['cases']})
        self.assertFalse(pilot['T4_calibration_slot'])
        self.assertEqual(pilot['scientific_candidate_trials'], 0)


if __name__ == '__main__':
    unittest.main()
