"""Offline 24-task contract/prompt binding; this is not an execution entry."""
import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from quant_rsi.harness import capability_oracle as oracle, compatibility_pilot_023 as policy
from quant_rsi.harness import evaluator_023 as evaluator, providers
from quant_rsi.harness.comparison import ROOT

DIRECTORY = ROOT / 'benchmark/capability_public/comparison_v023'
FILES = ('contracts.json', 'prompts.json', 'prompt_freeze.json')


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def digest(raw):
    return sha256(raw).hexdigest()


def artifacts():
    evaluator.verify_bindings()
    suite = oracle.suite_fixtures('0.2')
    order = suite['task_order']
    if len(order) != 24 or len(set(order)) != 24 or set(order) != set(suite['tasks']):
        raise ValueError('exact frozen 24-task suite required')
    contracts = {tid: policy.contract(tid) for tid in order}
    users = {tid: providers.build_prompt(tid, suite['tasks'][tid]['public_input'],
                                        contract=contracts[tid]) for tid in order}
    documents = {'contracts.json': encode({'version': policy.CONTRACT_VERSION,
                                         'tasks': contracts}),
                 'prompts.json': encode({'system': policy.SYSTEM_PROMPT, 'user': users})}
    dependencies = json.loads(evaluator.FREEZE.read_bytes())['sha256'].copy()
    for path in (oracle.V02_PATH, evaluator.FREEZE, Path(__file__)):
        dependencies[path.relative_to(ROOT).as_posix()] = digest(path.read_bytes())
    plan = {
        'prepared_on': '2026-10-10',
        'scope': 'PUBLIC_CONTRACT_AND_PROMPTS_ONLY',
        'labels': ['PUBLIC', 'UNSEALED', 'PROVISIONAL'],
        'task_kind': 'STATIC_DIAGNOSTIC',
        'public_contract_version': policy.CONTRACT_VERSION,
        'evaluator_version': evaluator.VERSION,
        'task_ids': order,
        'source_cluster_count': len({t['source_incident_id'] for t in suite['tasks'].values()}),
        'primary_dimension_counts': dict(Counter(t['primary_dimension']
                                                 for t in suite['tasks'].values())),
        'system_prompt_sha256': digest(policy.SYSTEM_PROMPT.encode('utf-8')),
        'messages_per_request': ['system', 'user'],
        'context_policy': 'Independent task context; no other task/model answer or audit report.',
        'sha256': dependencies,
        'artifact_sha256': {name: digest(raw) for name, raw in documents.items()},
        'tasks': {tid: {
            'source_incident_id': suite['tasks'][tid]['source_incident_id'],
            'primary_dimension': suite['tasks'][tid]['primary_dimension'],
            'secondary_dimensions': suite['tasks'][tid]['secondary_dimensions'],
            'public_input_sha256': digest(encode(suite['tasks'][tid]['public_input'])),
            'contract_sha256': digest(encode(contracts[tid])),
            'user_prompt_sha256': digest(users[tid].encode('utf-8')),
        } for tid in order},
        'execution_freeze_status': 'NOT_CREATED',
        'real_execution_authorized': False,
        'budget_authorized': False,
        'execution_entry': None,
        'model_ids': None,
        'segment_schedule': None,
        'target_calls_after_separate_authorization': 48,
        'binding_note': 'Logical task order is inherited; segment dispatch order is not frozen. '
                        'JSON subobject hashes use this module encode(); text hashes use UTF-8. '
                        'This binding does not authorize the old six-task pilot or any API call.',
    }
    documents['prompt_freeze.json'] = encode(plan)
    return documents


def verify(directory=DIRECTORY):
    for name, raw in artifacts().items():
        if (directory / name).read_bytes() != raw:
            raise ValueError('24-task public binding changed: ' + name)
    return digest((directory / 'prompt_freeze.json').read_bytes())


def write(directory=DIRECTORY):
    documents = artifacts()
    for name, raw in documents.items():
        path = directory / name
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('preserve existing binding; create a new version: ' + name)
    directory.mkdir(parents=True, exist_ok=True)
    for name, raw in documents.items():
        path = directory / name
        if not path.exists():
            with path.open('xb') as handle:
                handle.write(raw)
    return verify(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    freeze_sha = write() if args.write else verify()
    print(json.dumps({'status': '24_TASK_PROMPTS_FROZEN_EXECUTION_NOT_PREPARED',
                      'prompt_freeze_sha256': freeze_sha, 'real_calls': 0}))


if __name__ == '__main__':
    main()
