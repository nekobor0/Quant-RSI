"""Four CP contracts: isolated synthetic acceptance, external scoring and replay.

Reuses the pinned executor, SearchBudget and TraceStore without modifying them.
The scoped executor namespace is sequential only; Worker cannot choose the root.
"""
import argparse
import copy
import json
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import patch

from quant_rsi.harness import cp_isolation as isolation
from quant_rsi.harness.agent_workflow import ROOT, read, save, digest
from quant_rsi.harness.cp_acceptance_cases import materials, candidates
from quant_rsi.harness.supplement_tasks import same
from quant_rsi.ledger.store import TraceStore, Anchor, verify_events

PACK = ROOT / 'benchmark/capability_cp_v01'
RUN = 'CP-FULL-ISOLATED-ACCEPTANCE-V01'
ENGINEERING = dict(max_sessions=24, planned_sessions=16, max_test_commands=10,
                   automatic_retries=0, real_model_calls=0, judge_calls=0, data_calls=0)


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def prepare():
    if (PACK / 'freeze.json').exists():
        raise ValueError('FREEZE_EXISTS_DO_NOT_OVERWRITE')
    previous = isolation.frozen()
    PACK.mkdir(parents=True, exist_ok=True)
    (PACK / 'submissions').mkdir(exist_ok=True)
    (PACK / '.gitignore').write_bytes(b'*.sqlite*\nsynthetic_work/\n')
    tasks = materials()
    save(PACK / 'cases.json', tasks)
    contracts = read(ROOT / 'benchmark/capability_supplement_v01/cp_contracts.json')
    public = dict(common=contracts['common'], tasks=contracts['tasks'], version=RUN,
                  future_execution=contracts['future_execution'])
    public['future_execution']['image_digest'] = previous['image']['worker_content_id']
    save(PACK / 'public_contract.json', public)
    save(PACK / 'prompts.json', {task: dict(system='Implement the public pure Python function contract. '
        'Submit Python source only. No network, files, subprocesses or score claims. '
        'Oracle and scoring are external. Inputs must remain unchanged.',
        user=dict(task_id=task, common=public['common'], contract=public['tasks'][task])) for task in tasks})
    campaign = []
    for task, kind, source in candidates():
        label = task.lower() + '-' + kind
        path = PACK / 'submissions' / (label + '.py')
        path.write_bytes(source.encode('utf-8'))
        campaign.append(dict(task_id=task, kind=kind, label=label, source=str(path.relative_to(ROOT)).replace('\\', '/')))
    save(PACK / 'campaign.json', campaign)
    refs = [str(p.relative_to(ROOT)).replace('\\', '/') for p in PACK.glob('*.json')]
    refs += [item['source'] for item in campaign]
    refs += ['src/quant_rsi/harness/cp_acceptance.py', 'src/quant_rsi/harness/cp_acceptance_cases.py',
             'tests/test_cp_acceptance.py', 'benchmark/cp_worker_isolation_v01/freeze.json',
             'benchmark/cp_worker_isolation_v01/results.json', 'benchmark/cp_worker_isolation_v01/trace.json']
    bindings = dict(previous['sha256'])
    bindings.update({ref: sha(ROOT / ref) for ref in refs})
    freeze = dict(version=RUN, created_at=datetime.now(timezone.utc).isoformat(),
        policy=isolation.POLICY, budget_scope=previous['budget_scope'], image=previous['image'],
        sha256=bindings, engineering=ENGINEERING, host_python=platform.python_version(),
        prior_isolation_freeze_sha256=sha(isolation.PACK / 'freeze.json'),
        sample_scope='4 reference implementations, 4 equivalents and 8 authored mutants, NOT real model code',
        scoring='external per-call facts/errors/input/state predicates and 26 property groups; no aggregate model score',
        float_tolerance=1e-8, track_a=['PUBLIC', 'UNSEALED', 'PROVISIONAL'], D05_full=False, D08_verified=False)
    save(PACK / 'freeze.json', freeze)
    return freeze


def verify_freeze():
    freeze = read(PACK / 'freeze.json')
    if freeze['version'] != RUN or freeze['policy'] != isolation.POLICY or freeze['engineering'] != ENGINEERING:
        raise ValueError('FROZEN_POLICY_CHANGED')
    if freeze['host_python'] != platform.python_version():
        raise ValueError('HOST_RUNTIME_CHANGED')
    for ref, expected in freeze['sha256'].items():
        if sha(ROOT / ref) != expected:
            raise ValueError('FROZEN_BINDING_CHANGED:' + ref)
    return freeze


def score(task, record):
    """Only observed values scored; never admit a Worker-supplied score."""
    if record['status'] != 'COMPLETED':
        return dict(full_pass=False, execution_failure=record['status'], properties=None, calls=[], links=[])
    try:
        observed = isolation.parse_result(record['stdout'])
        if len(observed['records']) != len(task['cases']) or len(observed['retained']) != len(task['cases']):
            raise ValueError('CALL_COUNT_CHANGED')
    except (ValueError, TypeError, RecursionError):
        return dict(full_pass=False, execution_failure='INVALID_RESULT_SCHEMA', properties=None, calls=[], links=[])
    calls, links = [], []
    for index, case in enumerate(task['cases']):
        raw = observed['records'][index]
        value = raw['value']
        valid = type(value) is dict and set(value) == {'result', 'exception', 'before', 'after'} and raw['error'] is None
        expected = case['expected']
        predicates = dict(
            result_and_exception=valid and same(value['result'], expected['result']) and value['exception'] == expected['exception'],
            input_preserved=valid and digest(value['before']) == digest(value['after']) == digest(expected['before']),
            returned_state_independent=same(observed['retained'][index], task['expected_retained'][index]),
            instrumentation_valid=valid and raw['input_unchanged'])
        calls.append(dict(label=case['label'], predicates=predicates, passed=all(predicates.values()),
                          failed_predicates=[k for k, v in predicates.items() if not v]))
    for link in task['links']:
        left = observed['records'][link['left']]['value']
        right = observed['records'][link['right']]['value']
        valid = type(left) is dict and type(right) is dict and 'result' in left and 'result' in right
        a, b = (left['result'], right['result']) if valid else (None, None)
        if valid and link['prefix'] is not None:
            valid = type(a) is list and type(b) is list
            if valid:
                a, b = a[:link['prefix']], b[:link['prefix']]
        links.append(dict(label=link['label'], property=link['property'], passed=valid and same(a, b)))
    properties = {}
    for name in task['property_names']:
        values = [calls[i]['passed'] for i, c in enumerate(task['cases']) if name in c['properties']]
        values += [link['passed'] for link in links if link['property'] == name]
        properties[name] = bool(values) and all(values)
    return dict(full_pass=all(c['passed'] for c in calls) and all(l['passed'] for l in links) and all(properties.values()),
                execution_failure=None, properties=properties, calls=calls, links=links)


def run():
    if (PACK / 'results.json').exists() or (PACK / 'engineering.sqlite').exists():
        raise ValueError('RUN_EXISTS_APPEND_ONLY_DO_NOT_REPEAT')
    freeze = verify_freeze()
    if isolation.docker('image', 'inspect', freeze['image']['worker_content_id'], '--format', '{{.Id}}').strip() != freeze['image']['worker_content_id']:
        raise ValueError('IMAGE_UNAVAILABLE')
    security = json.loads(isolation.docker('info', '--format', '{{json .SecurityOptions}}'))
    if 'name=seccomp,profile=builtin' not in security:
        raise ValueError('DEFAULT_SECCOMP_REQUIRED')
    tasks, campaign = read(PACK / 'cases.json'), read(PACK / 'campaign.json')
    if len(campaign) != ENGINEERING['planned_sessions']:
        raise ValueError('CAMPAIGN_CHANGED')
    store = TraceStore(PACK / 'engineering.sqlite')
    records = []
    # Frozen executor stays byte-identical. One sequential root for the whole campaign.
    with patch.multiple(isolation, PACK=PACK, RUN=RUN):
        budget = isolation.ledger(store, freeze)
        for item in campaign:
            packet = dict(mode='calls', operations=tasks[item['task_id']]['operations'])
            record = isolation.execute(store, budget, freeze, item['label'],
                (ROOT / item['source']).read_text(encoding='utf-8'), packet)
            evaluated = score(tasks[item['task_id']], record)
            payload = dict(**item, score=evaluated, evidence_digest=digest(record))
            store.append('acceptance-score:' + item['label'], 'CP_PROPERTY_SCORE', payload)
            records.append(dict(**item, evidence=record, score=evaluated))
            print(json.dumps(dict(task=item['task_id'], kind=item['kind'], status=record['status'],
                full_pass=evaluated['full_pass'], properties=evaluated['properties'])), flush=True)
        accounting = budget.capability_accounting(RUN)
    anchor = asdict(store.checkpoint())
    references = [r for r in records if r['kind'] == 'reference']
    equivalents = [r for r in records if r['kind'] == 'equivalent']
    mutants = [r for r in records if r['kind'] not in ('reference', 'equivalent')]
    good = len(references) == 4 and all(r['score']['full_pass'] for r in references)
    good = good and len(equivalents) == 4 and all(r['score']['full_pass'] for r in equivalents)
    good = good and len(mutants) == 8 and all(not r['score']['full_pass'] and r['score']['execution_failure'] is None and
        any(r['score']['properties'].values()) and not all(r['score']['properties'].values()) for r in mutants)
    result = dict(status='PASS_CP_FULL_ISOLATED_ENGINEERING' if good else 'CP_ACCEPTANCE_REVIEW_REQUIRED',
        records=records, budget=accounting, anchor=anchor, freeze_sha256=sha(PACK / 'freeze.json'),
        execution_entry_sha256=sha(ROOT / 'src/quant_rsi/harness/cp_acceptance.py'),
        model_calls=0, judge_calls=0, data_calls=0, worker_cpu_total=None,
        D05_full_sealed_qualified=False, D08_verified=False)
    save(PACK / 'results.json', result)
    save(PACK / 'trace.json', store.read())
    save(PACK / 'receipt.json', dict(results_sha256=sha(PACK / 'results.json'), trace_sha256=sha(PACK / 'trace.json'),
        freeze_sha256=sha(PACK / 'freeze.json'), anchor=anchor))
    return result


def replay():
    """No Docker, model or tool invocation; same external predicates over saved bytes."""
    verify_freeze()
    result, trace, receipt = read(PACK / 'results.json'), read(PACK / 'trace.json'), read(PACK / 'receipt.json')
    for name in ('results', 'trace', 'freeze'):
        if sha(PACK / (name + '.json')) != receipt[name + '_sha256']:
            raise ValueError('RECEIPT_CHANGED:' + name)
    if verify_events(trace, Anchor(**receipt['anchor'])) != Anchor(**result['anchor']):
        raise ValueError('TRACE_ANCHOR_CHANGED')
    tasks = read(PACK / 'cases.json')
    campaign = read(PACK / 'campaign.json')
    if [{k: r[k] for k in ('task_id', 'kind', 'label', 'source')} for r in result['records']] != campaign:
        raise ValueError('CAMPAIGN_RESULT_CHANGED')
    events = {e['event_id']: e['payload'] for e in trace}
    for item in result['records']:
        evidence, label = item['evidence'], item['label']
        if evidence != events['cp-evidence:' + label] or item['score'] != score(tasks[item['task_id']], evidence):
            raise ValueError('OBSERVATION_OR_SCORE_CHANGED:' + label)
        expected = dict(**{k: item[k] for k in ('task_id', 'kind', 'label', 'source')},
            score=item['score'], evidence_digest=digest(evidence))
        if events['acceptance-score:' + label] != expected:
            raise ValueError('TRACE_SCORE_CHANGED:' + label)
        if evidence['freeze_sha256'] != result['freeze_sha256'] or evidence['submission_sha256'] != sha(ROOT / item['source']):
            raise ValueError('EXECUTION_BINDING_CHANGED:' + label)
        packet = dict(mode='calls', operations=tasks[item['task_id']]['operations'])
        if evidence['public_sha256'] != sha256(json.dumps(packet, sort_keys=True, indent=2, allow_nan=False).encode()).hexdigest():
            raise ValueError('PUBLIC_INPUT_CHANGED:' + label)
    # Rehydrate the existing budget projection, not a second accounting system.
    from quant_rsi.ledger.budget import SearchBudget
    class FrozenTrace:
        def read(self):
            return copy.deepcopy(trace)
    if SearchBudget(FrozenTrace()).capability_accounting(RUN) != result['budget']:
        raise ValueError('BUDGET_PROJECTION_CHANGED')
    return dict(status='OFFLINE_REPLAY_VERIFIED', sessions=len(result['records']), model_calls=0, tool_executions=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'run', 'replay'])
    args = parser.parse_args()
    value = dict(prepare=prepare, run=run, replay=replay)[args.operation]()
    print(json.dumps({k: value[k] for k in ('status', 'sessions', 'model_calls') if k in value}))


if __name__ == '__main__':
    main()
