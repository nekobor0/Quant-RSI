"""Build exactly four public prototype bundles and retain every terminal."""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from quant_rsi.benchmark_public.adapter import run_public  # noqa: E402

OUT = ROOT / 'artifacts/stage_c1/C1-03/pilot_run2'
RUNS = [(tier, variant, 'correct') for tier, variants in (
    ('T1', ('base', 'transfer')), ('T2', ('base', 'positive')),
    ('T3', ('base', 'transfer')), ('T4', ('base', 'transfer')))
    for variant in variants]
RUNS += [('T4', 'base', policy) for policy in (
    'fabricated_evidence', 'unjustified_refusal', 'invalid_format', 'timeout')]


def main():
    if OUT.exists():
        raise SystemExit('pilot output already exists; do not overwrite append-only evidence')
    start_wall, start_cpu = time.perf_counter_ns(), time.process_time_ns()
    rows = []
    for tier, variant, policy in RUNS:
        identity = '-'.join((tier, variant, policy))
        result = run_public(tier=tier, variant=variant, policy=policy,
                            output_root=OUT / identity)
        rows.append({'tier': tier, 'variant': variant, 'policy': policy,
                     'terminal': result['oracle']['expected']['terminal'],
                     'full_pass': result['oracle']['full_pass'],
                     'denominator': result['oracle']['assigned_denominator'],
                     'scientific_candidate_variants': result['scientific_candidate_variants'],
                     'report_ref': f'artifacts/stage_c1/C1-03/pilot_run2/{identity}/report.json',
                     'wall_ms': result['cost']['wall_ms'],
                     'oracle_eval_ns': result['cost']['oracle_eval_ns']})
    summary = {'status': 'PUBLIC_ORACLE_PILOT_NOT_OFFICIAL_SCORE',
               'prototype_tiers': sorted({row['tier'] for row in rows}),
               'calibration_slots': 9, 'T4_exposure': 'PUBLIC_DEVELOPMENT_ORACLE_PROTOTYPE',
               'assigned_denominator': sum(row['denominator'] for row in rows),
               'full_pass': sum(row['full_pass'] for row in rows),
               'T4_terminal_outputs': ['correct_candidate', 'fabricated_evidence',
                   'unjustified_refusal', 'invalid_format', 'timeout_missing'],
               'rows': rows, 'provider_calls': 0, 'scientific_candidate_trials': 0,
               'hidden_submissions': 0,
               'cost': {'wall_ms_total': (time.perf_counter_ns() - start_wall + 999999) // 1000000,
                        'cpu_ms_total': (time.process_time_ns() - start_cpu + 999999) // 1000000,
                        'oracle_eval_ns_total': sum(row['oracle_eval_ns'] for row in rows),
                        'process_peak_memory_bytes': None,
                        'provider_token_cost': 'N/A_FAKE_PROVIDER',
                        'implementation_attempts': 2, 'engineering_repairs': 1}}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'prototype_tiers': summary['prototype_tiers'],
                      'assigned_denominator': summary['assigned_denominator'],
                      'full_pass': summary['full_pass'], 'wall_ms_total': summary['cost']['wall_ms_total']}))


if __name__ == '__main__':
    main()
