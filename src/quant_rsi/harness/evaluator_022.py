"""Versioned evaluator 0.2.2-period-tolerant, and a unified offline re-evaluation.

PURPOSE
-------
Pilot 002 exposed a punctuation defect in the frozen evaluator 0.2.0. Its reason
clause check is exact string equality against the published explanation
sentences (`capability_oracle.py:559-567`), and the frozen contract publishes
those sentences WITH a trailing period. Both models wrote the same sentence
without it, so an otherwise fully compliant answer failed on punctuation alone.

This module does NOT modify the frozen evaluator. It builds a *new version* that
specifies tolerant semantics, and it re-scores already-captured responses
offline. No network call, no credential read, and no original score is altered:
`score_original` and `score_0_2_2` are reported side by side.

TOLERANCE RULE (deliberately narrow)
------------------------------------
A clause that fails exact matching is accepted as a listed explanation only when
it differs from exactly one listed sentence by exactly one trailing '.'.
Nothing else is tolerated: no case folding, no whitespace collapsing, no prefix
matching, no fuzzy distance. The reason is that any wider tolerance would start
guessing at model intent, which this evaluator exists to avoid.

Everything else -- evidence aliases, fact values, negation, sources, verdict
acceptance -- is delegated unchanged to the frozen 0.2.0 implementation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quant_rsi.harness import capability_oracle as oracle
from quant_rsi.harness.comparison import ROOT

EVALUATOR_VERSION = '0.2.2-period-tolerant'
FROZEN_EVALUATOR_VERSION = '0.2.0'
FROZEN_ORACLE_SHA256 = 'ac42a75593e7c3535831c78ada304ffaddf251eb846c17414a940093cd7e4297'

PILOT_002_RUN = (ROOT / 'benchmark/capability_public/runs/compatibility_pilot'
                 / 'TRACK_A_V02_CLARIFIED_COMPATIBILITY_PILOT_002')
PILOT_001_RUN = (ROOT / 'benchmark/capability_public/runs/compatibility_pilot'
                 / 'TRACK_A_V02_DSH_COMPATIBILITY_PILOT_001')


def _period_variants(explanations):
    """Add the no-trailing-period spelling of each listed sentence."""
    variants = set(explanations)
    for sentence in explanations:
        if sentence.endswith('.'):
            variants.add(sentence[:-1])
    return variants


def tolerant_contract(contract):
    """A copy of the task contract whose listed sentences tolerate a final period."""
    patched = dict(contract)
    original = contract['reason_explanations']
    patched['reason_explanations'] = sorted(_period_variants(original))
    patched['_period_tolerance_applied'] = True
    patched['_original_reason_explanations'] = list(original)
    return patched


_TASK_CACHE = {}


def frozen_contract(task_id):
    """The untouched 0.2.0 contract for one task, read from the frozen fixture."""
    if task_id not in _TASK_CACHE:
        task = oracle.suite_fixtures('0.2')['tasks'][task_id]
        _TASK_CACHE[task_id] = {'task': task, 'contract': task['input_contract']}
    return _TASK_CACHE[task_id]


def adjudicate_tolerant(task_id, response_bytes, *, failure_type=None):
    """Frozen 0.2.0 adjudication run against the tolerant contract.

    `capability_oracle.suite_fixtures` re-parses the fixture file on every call
    (there is no cache), so mutating a previously loaded dict has no effect --
    that was a real bug in an earlier version of this module, caught because the
    re-score reported zero changed rows. The only seam that actually reaches the
    evaluator is `load_fixtures`, so that is what gets substituted.
    """
    from unittest.mock import patch

    original_load = oracle.load_fixtures
    target = str(oracle.V02_PATH)

    def tolerant_load(path=None):
        data = original_load(path)
        if path is not None and str(path) != target:
            return data
        for tid, task in data['tasks'].items():
            task['input_contract'] = tolerant_contract(task['input_contract'])
        return data

    if not any(s.endswith('.') for s in
               frozen_contract(task_id)['contract']['reason_explanations']):
        # Nothing to tolerate for this task; delegate untouched.
        return oracle.adjudicate_v02(task_id, response_bytes, failure_type=failure_type)
    with patch.object(oracle, 'load_fixtures', tolerant_load):
        return oracle.adjudicate_v02(task_id, response_bytes, failure_type=failure_type)


def period_tolerant_clauses(task_id, response_text):
    """Which clauses were accepted ONLY because of the trailing-period tolerance.

    Reported so the tolerance is visible per record instead of silently absorbed.
    """
    if not response_text:
        return []
    try:
        text = response_text.strip()
        if text.startswith('```'):
            import re
            fenced = re.fullmatch(r'```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```', text)
            if not fenced:
                return []
            text = fenced[1]
        reason = json.loads(text).get('reason')
    except (ValueError, UnicodeDecodeError, AttributeError):
        return []
    if not isinstance(reason, str):
        return []
    published = set(frozen_contract(task_id)['contract']['reason_explanations'])
    rescued = []
    for clause in reason.split(';'):
        clause = clause.strip()
        if clause in published or not clause:
            continue
        if (clause + '.') in published:
            rescued.append(clause)
    return rescued


def rescore_record(record):
    """Re-score one captured record both ways. Pure function over stored bytes."""
    task_id = record['task_id']
    text = record.get('response_text')
    raw = text.encode('utf-8') if text is not None else None
    failure = record.get('provider_failure')
    original = oracle.adjudicate_v02(task_id, raw, failure_type=failure).to_dict()
    tolerant = adjudicate_tolerant(task_id, raw, failure_type=failure).to_dict()
    return {
        'provider_id': record['provider_id'],
        'task_id': task_id,
        'score_original': original,
        'score_0_2_2': tolerant,
        'period_rescued_clauses': period_tolerant_clauses(task_id, text),
        'changed': original != tolerant,
    }


def load_records(run_root):
    result = json.loads((Path(run_root) / 'result.json').read_text(encoding='utf-8'))
    return result['records']


def summarise(rows, label):
    assigned = len(rows)
    passed = sum(1 for r in rows if r['score_0_2_2']['full_pass'])
    passed_before = sum(1 for r in rows if r['score_original']['full_pass'])
    return {
        'batch': label,
        'records': assigned,
        'full_pass_original': passed_before,
        'full_pass_0_2_2': passed,
        'newly_passing': passed - passed_before,
        'verdict_correct_original': sum(1 for r in rows if r['score_original']['verdict_ok']),
        'verdict_correct_0_2_2': sum(1 for r in rows if r['score_0_2_2']['verdict_ok']),
        'reason_unsupported_original': sum(
            'reason:UNSUPPORTED_CLAUSE' in r['score_original']['exact_mismatches'] for r in rows),
        'reason_unsupported_0_2_2': sum(
            'reason:UNSUPPORTED_CLAUSE' in r['score_0_2_2']['exact_mismatches'] for r in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, action='append', default=None,
                        help='run directory to re-score; repeatable')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()

    from hashlib import sha256
    frozen_sha = sha256(Path(oracle.__file__).read_bytes()).hexdigest()
    if frozen_sha != FROZEN_ORACLE_SHA256:
        print('WARNING: frozen evaluator bytes changed; expected', FROZEN_ORACLE_SHA256,
              'got', frozen_sha, file=sys.stderr)

    runs = args.run or [PILOT_002_RUN, PILOT_001_RUN]
    report = {
        'evaluator_version_new': EVALUATOR_VERSION,
        'evaluator_version_frozen': FROZEN_EVALUATOR_VERSION,
        'frozen_evaluator_sha256': frozen_sha,
        'frozen_evaluator_unchanged': frozen_sha == FROZEN_ORACLE_SHA256,
        'network_calls': 0,
        'real_credentials_read': 0,
        'tolerance_rule': 'a listed sentence is also accepted without exactly one trailing period',
        'batches': [],
    }

    for run_root in runs:
        run_root = Path(run_root)
        if not (run_root / 'result.json').exists():
            print(f'skip (no result.json): {run_root}', file=sys.stderr)
            continue
        records = load_records(run_root)
        rows = [rescore_record(r) for r in records]
        report['batches'].append({
            'run_dir': str(run_root.relative_to(ROOT)),
            'summary': summarise(rows, run_root.name),
            'rows': rows,
        })

    if args.write:
        out = ROOT / 'benchmark/capability_public/pilot_v02_clarified/REEVAL_0_2_2.json'
        out.write_bytes(json.dumps(report, sort_keys=True, indent=2).encode())
        report['written_to'] = str(out.relative_to(ROOT))

    for batch in report['batches']:
        s = batch['summary']
        print(f"\n=== {s['batch']} ===")
        for key in ('records', 'full_pass_original', 'full_pass_0_2_2', 'newly_passing',
                    'verdict_correct_original', 'verdict_correct_0_2_2',
                    'reason_unsupported_original', 'reason_unsupported_0_2_2'):
            print(f'  {key:32} {s[key]}')
        for row in batch['rows']:
            if row['changed']:
                print(f"    CHANGED {row['provider_id']:9} {row['task_id']:26} "
                      f"pass {row['score_original']['full_pass']} -> {row['score_0_2_2']['full_pass']}"
                      f"  rescued={row['period_rescued_clauses']}")
    print('\nfrozen evaluator unchanged:', report['frozen_evaluator_unchanged'])
    if report.get('written_to'):
        print('written:', report['written_to'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
