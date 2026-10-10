"""Frozen revised-contract pilot, no default network or credential access.

Launch in a user-operated terminal after separate batch authorization. The
serial runner, failure capture, budget and trace are reused without edits.
"""
import argparse
import json
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from quant_rsi.harness import compatibility_pilot_clarified as base
from quant_rsi.harness import compatibility_pilot as pilot, evaluator_023 as evaluator, providers
from quant_rsi.ledger.store import TraceStore

FREEZE = evaluator.FREEZE
ENTRY = Path(__file__)
CONTRACT_VERSION = 'PUBLIC_ANSWER_CONTRACT_V0.2.3'
SYSTEM_PROMPT = providers.SYSTEM_PROMPT.replace(
    'Use PASS only when the evidence positively supports acting.',
    'Use PASS when the evidence supports the requested scoped decision, including '
    'an execution diagnosis. Diagnostic PASS does not mean provider execution '
    'succeeded, a research conclusion is correct, or a strategy is qualified.')
RUN_ID = 'TRACK_A_V023_PUBLIC_CONTRACT_COMPATIBILITY_PILOT_003'


def contract(task_id):
    result = base.clarified_contract(task_id)
    policy = pilot.load(evaluator.POLICY)
    result['version'] = CONTRACT_VERSION
    result['reason_role'] += ' ' + policy['reason_policy']
    result['verdict_meanings']['PASS'] = policy['verdict_policy']
    result['execution_diagnostics'] = policy['failure_class_catalog']
    result['diagnostic_alias_scope'] = policy['alias_scope']
    return result


def prompts(plan):
    tasks = base.oracle.suite_fixtures('0.2')['tasks']
    return {tid: providers.build_prompt(tid, tasks[tid]['public_input'], contract=contract(tid))
            for tid in plan['task_ids']}


@contextmanager
def bindings():
    class VersionedTrace(TraceStore):
        def append(self, event_id, kind, payload):
            if kind == 'PILOT_STARTED':
                payload.update(evaluator_version=evaluator.VERSION,
                               public_policy_sha256=pilot.digest(evaluator.POLICY.read_bytes()),
                               launch_channel='USER_OPERATED_TERMINAL_NO_PAID_CONTROLLER')
            return super().append(event_id, kind, payload)

    def dispatch(task_id, response_bytes, *, suite='0.1', failure_type=None):
        if suite != '0.2':
            raise ValueError('this pilot only scores suite 0.2')
        return evaluator.adjudicate(task_id, response_bytes, failure_type=failure_type)

    with ExitStack() as stack:
        for module, name, value in (
                (base, 'FREEZE', FREEZE), (base, 'ENTRY', ENTRY),
                (base, 'CONTRACT_VERSION', CONTRACT_VERSION), (base, 'prompts', prompts),
                (base, 'TraceStore', VersionedTrace),
                (providers, 'SYSTEM_PROMPT', SYSTEM_PROMPT),
                (base.oracle, 'adjudicate', dispatch)):
            stack.enter_context(patch.object(module, name, value))
        with base.bindings():
            yield


def validate():
    evaluator.verify_bindings()
    with bindings():
        plan = pilot.validate_freeze()
    if pilot.load(FREEZE.with_name('prompts.json')) != {'system': SYSTEM_PROMPT, 'user': prompts(plan)}:
        raise ValueError('v0.2.3 prompt artifact changed')
    if plan['controller_budget'] != {'paid_controller_calls': 0, 'cap_cny': '0.00',
            'launch_channel': 'USER_OPERATED_TERMINAL_NO_PAID_CONTROLLER'}:
        raise ValueError('no paid controller authorized')
    return plan


def run(run_id, authorization, output_root=None):
    plan = validate()
    with bindings():
        pilot.check_authorization(plan, authorization)
        if (run_id != RUN_ID or authorization.get('run_id') != RUN_ID
                or authorization.get('launch_channel') != 'USER_OPERATED_TERMINAL_NO_PAID_CONTROLLER'
                or authorization.get('total_money_cap_cny') != plan['total_money_cap_cny']
                or sum(map(Decimal, plan['money_caps_cny'].values())) > Decimal(plan['total_money_cap_cny'])):
            raise ValueError('exact new batch ID, budget and user-operated terminal required')
        base.require_offpeak_room(plan)
        return pilot.run(run_id, authorization, output_root)


def replay(root):
    validate()
    with bindings():
        return base.replay(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args(argv)
    if args.replay:
        result = replay(args.replay)
    elif args.authorization:
        if not args.run_id:
            parser.error('--run-id required')
        result = run(args.run_id, pilot.load(args.authorization))
    else:
        validate()
        result = {'status': 'OFFLINE_PREPARED_NOT_AUTHORIZED', 'real_calls': 0,
                  'run_id': RUN_ID, 'freeze_sha256': pilot.digest(FREEZE.read_bytes()),
                  'entry_sha256': pilot.digest(ENTRY.read_bytes())}
    print(json.dumps({key: result[key] for key in ('status', 'calls', 'stop') if key in result}
                     if 'records' in result else result, indent=2))


if __name__ == '__main__':
    main()
