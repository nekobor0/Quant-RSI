"""Materialize public-only case metadata; never decides an oracle outcome."""
from hashlib import sha256
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'benchmark/calibration'
CASES = [
    ('CAL-T1-FIELD', 'T1', 'E1', 'future-field', 'PIT_DATA_BOUNDARY'),
    ('CAL-T1-REVISION', 'T1', 'E1', 'future-revision', 'PIT_DATA_BOUNDARY'),
    ('CAL-T2-P10', 'T2', 'E2', 'cross-sectional-momentum', 'PIT_DATA_BOUNDARY'),
    ('CAL-T2-P20', 'T2', 'E2', 'time-series-momentum', 'PIT_DATA_BOUNDARY'),
    ('CAL-T3-NULL-A', 'T3', 'E3', 'known-null-placebo-a', 'EVALUATOR_GATE'),
    ('CAL-T3-NULL-B', 'T3', 'E3', 'known-null-placebo-b', 'EVALUATOR_GATE'),
    ('CAL-T3-COST', 'T3', 'E5', 'gross-positive-net-nonpositive', 'EXECUTION_BOUNDARY'),
    ('CAL-T3-DECAY', 'T3', 'E7', 'signal-decay', 'EVALUATOR_GATE'),
    ('CAL-T3-EXECUTION', 'T3', 'E5', 'a-share-composite-execution', 'EXECUTION_BOUNDARY'),
]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write_yaml(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding='utf-8')


def main():
    generator = digest(BASE / 'generate.py')
    oracle = digest(BASE / 'oracle.py')
    entries = []
    for case_id, tier, family, mechanism, rejection_layer in CASES:
        fixture = BASE / 'fixtures' / f'{case_id}.json'
        variants = json.loads(fixture.read_text(encoding='utf-8'))['variants']
        ref = f'benchmark/calibration/task_specs/{case_id}.yaml'
        oracle_ref = f'benchmark/calibration/oracle_manifests/{case_id}.yaml'
        paper_ref = f'benchmark/calibration/REFERENCE_{case_id[-3:]}.yaml' if tier == 'T2' else None
        spec = {
            'schema': 'BenchmarkTaskSpec_PUBLIC_PROJECTION', 'status': 'PUBLIC_CALIBRATION_ONLY',
            'task_id': case_id, 'task_version': '0.1', 'tier': tier, 'task_family': family,
            'mechanism': mechanism, 'benchmark_condition_ref': 'PUBLIC_SYNTHETIC_ONLY_NOT_OFFICIAL_RUN',
            'public_prompt': f'Adjudicate {mechanism} from the supplied synthetic fixture; cite computed evidence or refuse.',
            'public_inputs': [f'benchmark/calibration/fixtures/{case_id}.json'],
            'forbidden_inputs': ['hidden_pack', 'real_market_data', 'post_decision_information', 'model_provider'],
            'oracle_ref': oracle_ref, 'reference_definition_ref': paper_ref,
            'development_partition': 'PUBLIC_CALIBRATION', 'sealed_partition': None,
            'required_outputs': ['terminal', 'reason', 'evidence', 'expected_rejection_layer'],
            'search_budget': {'scientific_candidate_trials': 0, 'hidden_submissions': 0, 'provider_calls': 0},
            'score_denominator': 'one_per_assigned_variant_including_missing_invalid_timeout',
            'score_dimensions_ref': 'benchmark/BENCHMARK_SCORE_VECTOR.yaml',
            'formal_claim_allowed': False,
        }
        manifest = {
            'case_id': case_id, 'exposure': 'PUBLIC_CALIBRATION', 'tier': tier,
            'fixture_ref': f'benchmark/calibration/fixtures/{case_id}.json',
            'fixture_sha256': digest(fixture), 'generator_ref': 'benchmark/calibration/generate.py',
            'generator_sha256': generator, 'oracle_ref': 'benchmark/calibration/oracle.py',
            'oracle_sha256': oracle, 'shared_truth_dependency_list': [],
            'independence_rationale': 'Generator fixes input values and variants without outcomes; oracle separately computes temporal, return, null, cost, decay or execution verdict. Neither imports the other.',
            'original_reference_ref': paper_ref,
            'expected_rejection_layer': rejection_layer,
            'variants': list(variants),
            'perturbation': 'Variant input changes are recomputed by the independent oracle; no fixture byte matching.',
            'numeric_tolerance': 'exact_decimal_6_places_for_returns_else_exact',
            'assigned_denominator_policy': 'retain_all_assigned_variants_even_missing_invalid_timeout',
        }
        write_yaml(ROOT / ref, spec)
        write_yaml(ROOT / oracle_ref, manifest)
        entries.append({'case_id': case_id, 'tier': tier, 'task_family': family,
                        'task_spec_ref': ref, 'oracle_manifest_ref': oracle_ref,
                        'fixture_ref': manifest['fixture_ref'], 'exposure': 'PUBLIC_CALIBRATION'})
    write_yaml(BASE / 'CALIBRATION_PACK_V0_1.yaml', {
        'status': 'PUBLIC_CALIBRATION_ONLY_NOT_OFFICIAL_BENCHMARK',
        'case_count': len(entries), 'cases': entries,
        'independent_expected_ref': 'benchmark/calibration/INDEPENDENT_EXPECTED_V0_1.json',
        'independent_expected_sha256': digest(BASE / 'INDEPENDENT_EXPECTED_V0_1.json'),
        'hidden_score_eligibility': False,
        'hidden_mechanism_policy': 'A different seed of this generator is insufficient for hidden independence.',
    })
    print(f'public_calibration_manifests={len(entries)}')


if __name__ == '__main__':
    main()
