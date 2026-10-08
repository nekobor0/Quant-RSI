"""Freeze C2 public engineering runs; never overwrite a prior trace."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from quant_rsi.benchmark_public.canonical import run_canonical  # noqa: E402

OUT = ROOT / 'artifacts/stage_c2/C2-01/canonical_run2'
RUNS = [(tier, variant, 'correct') for tier, variants in (
    ('T1', ('base', 'transfer')), ('T2', ('base', 'positive')),
    ('T3', ('base', 'positive_transfer')),
    ('T4', ('base', 'transfer', 'refusal'))) for variant in variants]
RUNS += [('T4', 'base', policy) for policy in (
    'fabricated_evidence', 'unjustified_refusal', 'invalid_format',
    'timeout', 'critic_rejection')]
RUNS += [('T4', 'unregistered_oracle', 'correct')]


def main():
    if OUT.exists():
        raise SystemExit('canonical public output already exists; append-only run requires a fresh path')
    OUT.mkdir(parents=True)
    rows = []
    for tier, variant, policy in RUNS:
        path = OUT / '-'.join((tier, variant, policy)).replace('_', '-')
        row = run_canonical(tier=tier, variant=variant, policy=policy, output_root=path)
        row['run_path'] = path.relative_to(ROOT).as_posix()
        rows.append(row)
    summary = dict(status='CANONICAL_PUBLIC_ENGINEERING_ONLY', assigned_denominator=len(rows),
        prototype_tiers=sorted({row['tier'] for row in rows}),
        public_oracle_full_pass=sum(row['public_oracle_full_pass'] for row in rows),
        diagnostics={name: sum(row['diagnostic'] == name for row in rows)
                     for name in sorted({row['diagnostic'] for row in rows})},
        provider_calls=0, scientific_candidate_trials=sum(row['scientific_candidate_trials'] for row in rows),
        scientific_variants=sum(row['scientific_variant_count'] for row in rows),
        hidden_submissions=0, formal_research_verdict='BLOCKED', official_benchmark_status='NOT_STARTED',
        g4='BLOCKED', g6='BLOCKED', rows=rows)
    (OUT / 'summary.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('assigned_denominator', 'prototype_tiers',
        'public_oracle_full_pass', 'diagnostics', 'scientific_candidate_trials',
        'formal_research_verdict')}, sort_keys=True))


if __name__ == '__main__':
    main()
