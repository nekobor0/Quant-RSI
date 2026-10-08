"""Run deterministic public controls and preserve every assigned output."""
from pathlib import Path
import json
import time
import yaml

from oracle import adjudicate
from manual_expected import compute as independent_compute

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / 'benchmark/calibration/CALIBRATION_PACK_V0_1.yaml'
OUT = ROOT / 'artifacts/stage_c1/C1-01/baseline_results.json'


def policy(name, case_id, data):
    if name == 'AlwaysRefuse':
        return {'terminal': 'REFUSE', 'reason': 'UNSUPPORTED', 'evidence': {},
                'expected_rejection_layer': 'EVALUATOR_GATE'}
    if name == 'AlwaysPromote':
        return {'terminal': 'PROMOTE', 'reason': None, 'evidence': {'claim': 'supported'},
                'expected_rejection_layer': None}
    if name == 'ContractOnly':
        return {'terminal': 'PROMOTE', 'reason': None, 'evidence': {},
                'expected_rejection_layer': None}
    if name == 'ScriptedReferenceControl':
        result = independent_compute(case_id, data)
        return {key: result[key] for key in ('terminal', 'reason', 'evidence', 'expected_rejection_layer')}
    if name == 'MissingOutput':
        return None
    raise ValueError(name)


def run():
    pack = yaml.safe_load(PACK.read_text(encoding='utf-8'))
    rows = []
    for name in ('AlwaysRefuse', 'AlwaysPromote', 'ContractOnly',
                 'ScriptedReferenceControl', 'MissingOutput'):
        for item in pack['cases']:
            case_id = item['case_id']
            fixture = json.loads((ROOT / item['fixture_ref']).read_text(encoding='utf-8'))
            for variant, data in fixture['variants'].items():
                start = time.perf_counter_ns()
                output = policy(name, case_id, data)
                result = adjudicate(case_id, data, output)
                rows.append({'policy': name, 'case_id': case_id, 'variant': variant,
                             'output': output, 'adjudication': result,
                             'oracle_eval_ns': time.perf_counter_ns() - start})
    summary = {}
    for name in {row['policy'] for row in rows}:
        subset = [row for row in rows if row['policy'] == name]
        summary[name] = {'assigned_denominator': sum(r['adjudication']['assigned_denominator'] for r in subset),
                         'terminal_correct': sum(r['adjudication']['terminal_correct'] for r in subset),
                         'full_pass': sum(r['adjudication']['full_pass'] for r in subset),
                         'required_positive': sum(r['adjudication']['expected']['terminal'] == 'PROMOTE' for r in subset),
                         'positive_coverage': sum(r['adjudication']['expected']['terminal'] == 'PROMOTE' and r['output'] is not None and r['output']['terminal'] == 'PROMOTE' for r in subset),
                         'unjustified_refusals': sum(r['adjudication']['expected']['terminal'] == 'PROMOTE' and r['output'] is not None and r['output']['terminal'] == 'REFUSE' for r in subset),
                         'known_null_false_positives': sum(r['case_id'] in ('CAL-T3-NULL-A', 'CAL-T3-NULL-B') and r['adjudication']['expected']['terminal'] == 'REFUSE' and r['output'] is not None and r['output']['terminal'] == 'PROMOTE' for r in subset),
                         'promoted_count': sum(r['output'] is not None and r['output']['terminal'] == 'PROMOTE' for r in subset),
                         'correct_promotions': sum(r['output'] is not None and r['output']['terminal'] == 'PROMOTE' and r['adjudication']['full_pass'] for r in subset)}
    result = {'scope': 'PUBLIC_CALIBRATION_ONLY', 'policies': summary,
              'rows': rows, 'provider_calls': 0, 'scientific_candidate_trials': 0,
              'hidden_submissions': 0}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    run()
