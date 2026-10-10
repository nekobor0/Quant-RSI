"""Append orthogonal CP diagnostics to preserved composite property scores.

No container/code execution: reads actual saved observations, never infers
input mutation from a wrong numeric result. No original result is overwritten.
"""
import argparse
import copy
from dataclasses import asdict

from quant_rsi.harness import cp_acceptance as cp
from quant_rsi.harness.agent_workflow import ROOT, read, save, digest
from quant_rsi.harness.supplement_tasks import same
from quant_rsi.ledger.budget import SearchBudget
from quant_rsi.ledger.store import TraceStore, Anchor, verify_events

PACK = cp.PACK
VERSION = 'CP-ORTHOGONAL-DIAGNOSTICS-V01'


def diagnose(task, record):
    original = cp.score(task, record)
    if original['execution_failure'] is not None:
        return dict(vector=None, execution_failure=original['execution_failure'])
    observed = cp.isolation.parse_result(record['stdout'])
    # State checks compare each return with its own original observation, not
    # with Oracle numeric correctness. Apply only the deliberate caller edits.
    retained_expected = [copy.deepcopy(r['value']) for r in observed['records']]
    for op in task['operations']:
        if 'mutate_previous' in op:
            change = op['mutate_previous']
            obj = retained_expected[change['index']]
            for key in change['path'][:-1]:
                obj = obj[key]
            obj[change['path'][-1]] = change['value']
    valid, invalid, inputs, states = [], [], [], []
    for index, case in enumerate(task['cases']):
        expected = case['expected']
        fact = original['calls'][index]['predicates']['result_and_exception']
        (invalid if expected['exception'] else valid).append(fact)
        inputs.append(original['calls'][index]['predicates']['input_preserved'])
        returned = observed['retained'][index]
        target = retained_expected[index]
        states.append(type(returned) is dict and set(returned) == set(target) and
            same(returned['result'], target['result']) and returned['exception'] == target['exception'])
    vector = dict(RESULT_FACTS_CORRECT=all(valid), INVALID_INPUT_HANDLING=all(invalid),
        INPUT_PRESERVED=all(inputs), RETURN_STATE_INDEPENDENT=all(states),
        METAMORPHIC_RELATIONS_VALID=all(link['passed'] for link in original['links']),
        OBSERVATION_SCHEMA_VALID=all(c['predicates']['instrumentation_valid'] for c in original['calls']))
    return dict(vector=vector, execution_failure=None, failed_dimensions=[k for k, v in vector.items() if not v])


def verify():
    freeze = read(PACK / 'final_freeze.json')
    if freeze['version'] != VERSION:
        raise ValueError('DIAGNOSTIC_VERSION_CHANGED')
    for ref, expected in freeze['sha256'].items():
        if cp.sha(ROOT / ref) != expected:
            raise ValueError('FINAL_FREEZE_CHANGED:' + ref)
    cp.replay()
    return freeze


def freeze():
    if (PACK / 'final_freeze.json').exists():
        raise ValueError('FINAL_FREEZE_EXISTS')
    cp.replay()
    refs = ['src/quant_rsi/harness/cp_acceptance_finalize.py', 'tests/test_cp_acceptance_finalize.py']
    refs += ['benchmark/capability_cp_v01/' + name for name in ('freeze.json', 'results.json', 'trace.json', 'receipt.json')]
    value = dict(version=VERSION, sample_scope='4 synthetic tasks, 16 isolated sessions, authored code only',
        execution_freeze_sha256=cp.sha(PACK / 'freeze.json'),
        sha256={ref: cp.sha(ROOT / ref) for ref in refs},
        scoring='Original full-pass/composite property scores retained; orthogonal diagnostic vector appended',
        budgets=cp.ENGINEERING, track_a=['PUBLIC', 'UNSEALED', 'PROVISIONAL'])
    save(PACK / 'final_freeze.json', value)
    return value


def run():
    verify()
    if (PACK / 'acceptance.json').exists():
        raise ValueError('FINAL_ACCEPTANCE_EXISTS')
    raw, tasks = read(PACK / 'results.json'), read(PACK / 'cases.json')
    store = TraceStore(PACK / 'engineering.sqlite', Anchor(**raw['anchor']))
    rows = []
    for item in raw['records']:
        result = diagnose(tasks[item['task_id']], item['evidence'])
        row = dict(label=item['label'], task_id=item['task_id'], kind=item['kind'],
            original_full_pass=item['score']['full_pass'], original_score_ref='results.json#'+item['label'], **result)
        store.append('cp-diagnostic:' + item['label'], 'CP_ORTHOGONAL_DIAGNOSTIC', row)
        rows.append(row)
    passed = raw['status'] == 'PASS_CP_FULL_ISOLATED_ENGINEERING'
    passed = passed and all(all(row['vector'].values()) if row['kind'] in ('reference', 'equivalent') else
        not all(row['vector'].values()) and any(row['vector'].values()) for row in rows)
    value = dict(status='PASS_CP_FULL_ISOLATED_ENGINEERING' if passed else 'CP_DIAGNOSTIC_REVIEW_REQUIRED',
        rows=rows, published_property_groups=26, fixture_calls_per_session={k: len(t['cases']) for k, t in tasks.items()},
        anchor=asdict(store.checkpoint()), execution_attempts=raw['total_attempts'], completed_sessions=16,
        budget=SearchBudget(store).capability_accounting(cp.RUN),
        predecessor_budget=SearchBudget(store).capability_accounting(cp.PREDECESSOR),
        final_freeze_sha256=cp.sha(PACK / 'final_freeze.json'),
        model_calls=0, judge_calls=0, data_calls=0, D05_full_sealed_qualified=False, D08_verified=False)
    save(PACK / 'acceptance.json', value)
    save(PACK / 'diagnostic_trace.json', store.read())
    save(PACK / 'final_receipt.json', dict(anchor=value['anchor'],
        sha256={name: cp.sha(PACK / name) for name in ('acceptance.json', 'diagnostic_trace.json', 'final_freeze.json')}))
    return value


def replay():
    verify()
    result, receipt = read(PACK / 'acceptance.json'), read(PACK / 'final_receipt.json')
    for name, expected in receipt['sha256'].items():
        if cp.sha(PACK / name) != expected:
            raise ValueError('FINAL_RECEIPT_CHANGED:' + name)
    trace, original = read(PACK / 'diagnostic_trace.json'), read(PACK / 'trace.json')
    if trace[:len(original)] != original or verify_events(trace, Anchor(**receipt['anchor'])) != Anchor(**result['anchor']):
        raise ValueError('ORIGINAL_TRACE_OR_ANCHOR_CHANGED')
    events = {event['event_id']: event['payload'] for event in trace}
    tasks, raw = read(PACK / 'cases.json'), read(PACK / 'results.json')
    for row, item in zip(result['rows'], raw['records']):
        expected = dict(label=item['label'], task_id=item['task_id'], kind=item['kind'],
            original_full_pass=item['score']['full_pass'], original_score_ref='results.json#'+item['label'],
            **diagnose(tasks[item['task_id']], item['evidence']))
        if row != expected or events['cp-diagnostic:' + row['label']] != expected:
            raise ValueError('DIAGNOSTIC_CHANGED')
    if len(result['rows']) != len(raw['records']):
        raise ValueError('DIAGNOSTIC_COUNT_CHANGED')
    class FrozenTrace:
        def read(self):
            return trace
    budget = SearchBudget(FrozenTrace())
    if budget.capability_accounting(cp.RUN) != result['budget'] or budget.capability_accounting(cp.PREDECESSOR) != result['predecessor_budget']:
        raise ValueError('FINAL_BUDGET_CHANGED')
    return dict(status='OFFLINE_REPLAY_VERIFIED', sessions=16, containers_started=0, model_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['freeze', 'run', 'replay'])
    args = parser.parse_args()
    result = dict(freeze=freeze, run=run, replay=replay)[args.operation]()
    print({k: result[k] for k in ('status', 'sessions', 'model_calls') if k in result})


if __name__ == '__main__':
    main()
