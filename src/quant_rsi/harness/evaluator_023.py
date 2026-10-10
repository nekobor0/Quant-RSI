"""Public diagnostic policy revision; serial scoring over the frozen oracle.

Only punctuation tolerance and explicitly published token-limit value aliases
change. Verdicts, sources, other facts and failure gates are not rewritten.
"""
import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from quant_rsi.harness import evaluator_022 as previous, capability_oracle as oracle
from quant_rsi.harness.comparison import ROOT

VERSION = '0.2.3-public-diagnostics'
DIRECTORY = ROOT / 'benchmark/capability_public/pilot_v023'
POLICY = DIRECTORY / 'answer_policy.json'
FREEZE = DIRECTORY / 'freeze.json'
REPORT = DIRECTORY / 'REEVAL_0_2_3.json'
BASE_PERIOD_SHA = 'c76ef9fe5b1f3cb6f145ada6d1f4f640cc328aa85753c5b72e23413160c05eff'


def verify_bindings():
    bindings = previous.verify_bindings()
    if bindings['new_evaluator']['sha256'] != BASE_PERIOD_SHA:
        raise ValueError('frozen period evaluator changed')
    plan = json.loads(FREEZE.read_bytes())
    for relative, expected in plan['sha256'].items():
        if sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('v0.2.3 binding changed: ' + relative)
    bindings['period_evaluator'] = bindings.pop('new_evaluator')
    bindings['new_evaluator'] = {'version': VERSION,
        'path': str(Path(__file__).relative_to(ROOT)),
        'sha256': sha256(Path(__file__).read_bytes()).hexdigest()}
    bindings['public_policy'] = {'path': str(POLICY.relative_to(ROOT)),
                               'sha256': sha256(POLICY.read_bytes()).hexdigest()}
    bindings['freeze_sha256'] = sha256(FREEZE.read_bytes()).hexdigest()
    return bindings


def adjudicate(task_id, response_bytes, *, failure_type=None):
    verify_bindings()
    if task_id != 'A-PROVIDER-TOKEN-LIMIT':
        return previous.adjudicate_tolerant(task_id, response_bytes, failure_type=failure_type)
    aliases = json.loads(POLICY.read_bytes())['failure_class_catalog'][
        'TOKEN_BUDGET_EXHAUSTED']['accepted_exact_value_aliases']
    original = oracle._strict_same

    def same(value, expected, kind):
        if (kind == 'string' and expected == 'TOKEN_BUDGET_EXHAUSTED'
                and isinstance(value, str) and value in aliases):
            value = 'TOKEN_BUDGET_EXHAUSTED'
        return original(value, expected, kind)

    with patch.object(oracle, '_strict_same', same):
        return previous.adjudicate_tolerant(task_id, response_bytes, failure_type=failure_type)


def rescore_record(record):
    row = previous.rescore_record(record)  # verifies the preserved original score
    text = record['response_text']
    row['score_0_2_3'] = adjudicate(record['task_id'], text.encode() if text is not None else None,
                                  failure_type=record.get('provider_failure')).to_dict()
    row['changed_from_0_2_2'] = row['score_0_2_2'] != row['score_0_2_3']
    row['contract_retrospective_status'] = (
        'PUBLIC_CONTRACT_AMBIGUITY_REVIEW_REQUIRED'
        if record['task_id'] == 'A-PROVIDER-TOKEN-LIMIT' else 'POST_HOC_POLICY_RESCORING')
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = {'evaluator_version': VERSION, 'bindings': verify_bindings(),
                  'network_calls': 0, 'real_credentials_read': 0,
                  'status': 'POST_HOC_OFFLINE_POLICY_RESCORING',
                  'confirmed_legal_answer_misjudgments': None, 'batches': []}
        for root in (previous.PILOT_002_RUN, previous.PILOT_001_RUN):
            records, provenance = previous.load_bound_run(root)
            rows = [rescore_record(record) for record in records]
            report['batches'].append({'run_dir': str(root), 'provenance': provenance,
                'summary': {'records': len(rows), **{
                    f'full_pass_{version}': sum(row[f'score_{version}']['full_pass'] for row in rows)
                    for version in ('original', '0_2_2', '0_2_3')}}, 'rows': rows})
        if args.write:
            data = json.dumps(report, sort_keys=True, indent=2).encode()
            if REPORT.exists():
                if REPORT.read_bytes() != data:
                    raise ValueError('existing re-evaluation differs; preserve it')
            else:
                with REPORT.open('xb') as handle:
                    handle.write(data)
    except (ValueError, OSError, KeyError) as exc:
        print('REVALUATION_REFUSED:', str(exc), file=sys.stderr)
        return 1
    print(json.dumps([batch['summary'] for batch in report['batches']], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
