"""Offline measurement repair; historical traces and execution freezes stay immutable."""
import argparse
import copy
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from quant_rsi.harness import workflow_http_comparison as comparison
from quant_rsi.harness import workflow_transport_batch as core
from quant_rsi.ledger.store import Anchor, _read, verify_events

base, kernel = core.base, core.kernel
PACK = base.ROOT / 'benchmark/agent_workflow_v01/measurement_v023'
VERSION = 'workflow-measurement-v02.3'
PUBLIC_VERSION = 'workflow-public-contract-v02.3'
ORIGINAL_ASSESSED = core.http.assessed
ORIGINAL_VERIFY = core.verify_case


def decode_action(case, text):
    """Return accepted action, deterministic failure, and rejected JSON separately."""
    candidate = None
    try:
        if case['kind'] != 'CODE':
            return base.parse_action(text), None, None
        candidate = json.loads(text, object_pairs_hook=base._unique)
        if (type(candidate) is not dict or set(candidate) != {'code'} or
                type(candidate['code']) is not str or
                len(candidate['code'].encode()) > case['public_code']['submission']['source_bytes_max']):
            raise ValueError('CODE_SCHEMA_INVALID')
        return candidate, None, None
    except json.JSONDecodeError:
        return None, 'ACTION_JSON_INVALID', None
    except (ValueError, TypeError, AttributeError):
        return None, 'ACTION_SCHEMA_INVALID', candidate


def assess_action(case, reply, exchange, config):
    error, resources, cost, cost_status = ORIGINAL_ASSESSED(reply, exchange, config)
    action, rejected = None, None
    if error is None:
        action, error, rejected = decode_action(case, reply.text)
    return action, error, rejected, resources, cost, cost_status


def model_request(store, budget, run_id, case, agent, freeze, tool_contract, step, obs, history, raw, reasons):
    """Repair seam for a future bound entry; no new budget or trace system."""
    core.permit(store.read())
    messages = kernel.messages(case, tool_contract, obs, history, raw, [None] * len(raw))
    body = core.http.public_request(freeze['provider'], messages)
    if len(json.dumps(messages, ensure_ascii=False).encode()) > core.PUBLIC_BYTES:
        raise core.BudgetDenied('INPUT_PREFLIGHT_DENIED')
    attempt = f'CHAT-{run_id}-{step}'
    budget.reserve(run_id, attempt, dict(attempts=1, model_trials=int(step == 1),
        input_tokens=core.REQUEST_INPUT, output_tokens=core.REQUEST_OUTPUT,
        wall_milliseconds=305000, cpu_milliseconds=305000))
    store.append('model-request:' + attempt, 'MODEL_REQUEST', dict(attempt_id=attempt, run_id=run_id,
        task_id=case['task_id'], step=step, messages=messages, messages_hash=base.digest(messages),
        body=body, request_hash=base.digest(body), url=freeze['provider']['url']))
    started = time.process_time()
    try:
        reply, exchange = agent.step(case['task_id'], messages)
    except BaseException:
        reply = core.ProviderReply(False, None, None, 'HTTP_ADAPTER_FAILED_OR_INTERRUPTED',
            None, None, 1, 1, failure_class='HTTP_ADAPTER_FAILED_OR_INTERRUPTED')
        exchange = dict(body=body, envelope={}, raw_hex=None, raw_partial=False,
            observation={'cleanup_confirmed': False})
    exchange['supervisor_cpu_ms'] = max(0, int((time.process_time() - started) * 1000))
    action, error, rejected, resources, cost, status = assess_action(case, reply, exchange, freeze['provider'])
    if exchange['body'] != body:
        action, error = None, 'HTTP_MESSAGES_CHANGED'
    response = dict(run_id=run_id, attempt_id=attempt, reply=asdict(reply), exchange=exchange,
        resources=resources, error=error, action=action, rejected_candidate=rejected,
        cost_amount=cost, currency=freeze['provider']['currency'], cost_status=status)
    store.append('model-response:' + attempt, 'MODEL_RESPONSE', response)
    budget.settle(attempt, 'FAILED' if error else 'SUCCEEDED', resources,
        artifact_hashes={'action': base.digest(action)} if not error else {}, failure=error)
    return response


def verify_case(case, result, events, *, legacy=False):
    """Reproduce acceptance and rejection from raw replies, never trust stored error."""
    config = core.suite()[0]['provider']
    responses = [e['payload'] for e in events if e['kind'] == 'MODEL_RESPONSE' and
                 e['payload']['run_id'] == result['run_id']]
    for recorded in responses:
        reply = core.ProviderReply(**recorded['reply'])
        action, error, rejected, _, _, _ = assess_action(case, reply, recorded['exchange'], config)
        legacy_rejected = (legacy and case['kind'] == 'CODE' and error == 'ACTION_SCHEMA_INVALID' and
            rejected is not None and recorded['action'] == rejected)
        if recorded['error'] != error or (recorded['action'] != action and not legacy_rejected):
            raise ValueError('RESPONSE_ACCEPTANCE_OR_REJECTION_CHANGED:' + recorded['attempt_id'])
        if legacy_rejected and (result['code_record'] is not None or result['final'] is not None or
                result['status'] != 'INVALID_ACTION'):
            raise ValueError('REJECTED_CANDIDATE_WAS_EXECUTED')
        if 'rejected_candidate' in recorded and recorded['rejected_candidate'] != rejected:
            raise ValueError('REJECTED_CANDIDATE_CHANGED')
    def assessed(reply, exchange, cfg):
        _, error, _, resources, cost, status = assess_action(case, reply, exchange, cfg)
        return error, resources, cost, status
    with patch.object(core.http, 'assessed', assessed):
        return ORIGINAL_VERIFY(case, result, events)


def budget_event_view(events, run_id):
    """Evaluator view scoped by canonical reservations; original events are not edited."""
    roots = {e['payload']['attempt_id']: e['payload']['budget_root_run_id']
             for e in events if e['kind'] == 'ATTEMPT_STARTED'}
    for event in events:
        if event['kind'] == 'ATTEMPT_SETTLED' and event['payload']['attempt_id'] not in roots:
            raise ValueError('SETTLEMENT_WITHOUT_RESERVATION')
    return [e for e in events if e['kind'] != 'ATTEMPT_SETTLED' or
            roots[e['payload']['attempt_id']] == run_id]


def evaluate(case, result, events, observations):
    value = core.contract.evaluate(case, result, budget_event_view(events, result['run_id']), observations)
    value['version'] = VERSION
    if result['status'] == 'PROVIDER_FAILED':
        value['failure_class'] = 'HTTP_PROVIDER_FAILURE_NOT_RESEARCH'
        value['diagnostics'].append('provider:' + result['error'])
    return value


def score(case, result, events):
    return evaluate(case, result, events, verify_case(case, result, events))


def public_context(case, tool_contract, observations, history):
    context = copy.deepcopy(core.public_context(case, tool_contract, observations, history))
    if case['kind'] != 'CODE':
        action_contract = context['action_contract']
        action_contract['version'] = PUBLIC_VERSION
        action_contract['FINAL']['evidence'] = dict(type='array', items={'type': 'string'},
            uniqueItems=True, description='Actual observation/input IDs permitted by citation_policy; strings are not arrays')
        action_contract['format_only_FINAL_example'] = dict(action='FINAL', conclusion={}, evidence=['OBS-EXAMPLE-1'])
        action_contract['example_scope'] = 'Format only; conclusion must match this task schema; example IDs grant no permission'
    return context


def expression_diagnostic(case, result, events, observations):
    """Symmetric offline interpretation only, never an accepted action or score."""
    if case['kind'] == 'CODE' or result['error'] != 'ACTION_SCHEMA_INVALID':
        return None
    response = next(e['payload'] for e in reversed(events) if e['kind'] == 'MODEL_RESPONSE' and
                    e['payload']['run_id'] == result['run_id'])
    try:
        candidate = json.loads(response['reply']['text'], object_pairs_hook=base._unique)
        if type(candidate) is not dict or set(candidate) != {'action', 'conclusion', 'evidence'} or candidate['action'] != 'FINAL':
            return None
        if type(candidate['evidence']) is not str:
            return None
        refs = [part.strip() for part in re.split('[,;]', candidate['evidence'])]
        allowed = {'INPUT:' + case['task_id']} | {o['observation_id'] for o in observations if o['ok']}
        if not refs or len(set(refs)) != len(refs) or not set(refs) <= allowed:
            return None
        candidate['evidence'] = refs
        accepted, error, _ = decode_action(case, json.dumps(candidate))
        if error:
            return None
        hypothetical = copy.deepcopy(result)
        hypothetical['final'] = accepted
        value = evaluate(case, hypothetical, events, observations)
        return dict(admitted_as_score=False, interpretation='EXPLICIT_REFERENCE_STRING_TO_ARRAY_ONLY',
            facts=value['fact_predicates'], evidence=value['evidence_predicates'],
            all_facts_correct=all(value['fact_predicates'].values()),
            references_valid=value['evidence_predicates']['references_valid'])
    except (ValueError, KeyError, TypeError):
        return None


@contextmanager
def source(profile):
    with (core.selected('luna') if profile == 'luna' else comparison.selected(profile)):
        yield


def review(profile):
    with source(profile):
        core.validate()
        output = core.OUTPUT
        summary, events = base.read(output / 'summary.json'), base.read(output / 'trace.json')
        conn = sqlite3.connect((output / 'trace.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
        try:
            persisted = _read(conn)
        finally:
            conn.close()
        if persisted != events or (output / 'freeze.json').read_bytes() != (core.PACK / 'freeze.json').read_bytes():
            raise ValueError('SOURCE_EXPORT_OR_FREEZE_CHANGED')
        verify_events(events, Anchor(**summary['anchor']))
        freeze, cases, _ = core.suite()
        by = {e['event_id']: e for e in events}
        if (summary['accounting'] != core.projection(events) or
                by['model-start']['payload']['freeze_sha256'] != kernel.sha(core.PACK / 'freeze.json') or
                by['model-end']['payload'] != {k: v for k, v in summary.items() if k not in ('results', 'anchor')}):
            raise ValueError('SOURCE_BATCH_ACCOUNTING_CHANGED')
        rows = []
        with core.contract.execution_bindings(output, core.BATCH, core.LIMITS, core.permit, core.score, core.model_request):
            for index, result in enumerate(summary['results']):
                key, run_id = result['case_key'], result['run_id']
                if key != freeze['case_order'][index] or base.read(output / (key + '.json')) != result:
                    raise ValueError('SOURCE_CASE_ORDER_OR_RESULT_CHANGED')
                if (by['json-end:' + run_id]['payload'] != {k: v for k, v in result.items() if k != 'evaluation'} or
                        by['json-eval:' + run_id]['payload'] != dict(run_id=run_id, **result['evaluation'])):
                    raise ValueError('SOURCE_SCORE_EVENT_CHANGED')
                case = cases[key]
                obs = verify_case(case, result, events, legacy=True)
                if case['kind'] == 'CODE':
                    record, task = result['code_record'], base.read(core.contract.PACK / 'cp_cases.json')[key]
                    value = dict(score=kernel.cp.score(task, record), diagnostic=kernel.cp_diag.diagnose(task, record)) if record else dict(
                        score={'full_pass': False, 'execution_failure': result['status']}, diagnostic={'vector': None})
                    if record:
                        from hashlib import sha256
                        response = next(e['payload'] for e in events if e['kind'] == 'MODEL_RESPONSE' and e['payload']['run_id'] == run_id)
                        packet = dict(mode='calls', operations=task['operations'])
                        if (record['submission_sha256'] != sha256(kernel.wrapped_source(response['action']['code']).encode()).hexdigest() or
                                record['public_sha256'] != sha256(json.dumps(packet, sort_keys=True, indent=2, allow_nan=False).encode()).hexdigest() or
                                by['cp-evidence:' + record['label']]['payload'] != record):
                            raise ValueError('SOURCE_CODE_BINDING_CHANGED')
                        for side in ('before', 'after'):
                            kernel.cp.isolation.check_boundary(record[side], freeze['image']['worker_content_id'])
                    if value != result['evaluation']:
                        raise ValueError('ORIGINAL_CODE_SCORE_CHANGED')
                else:
                    value = evaluate(case, result, events, obs)
                    at_time = events[:by['json-eval:' + run_id]['sequence'] - 1]
                    original = core.score(case, result, at_time)
                    if original != result['evaluation']:
                        raise ValueError('ORIGINAL_CASE_TIME_SCORE_CHANGED')
                diagnostic = expression_diagnostic(case, result, events, obs)
                rows.append(dict(task_id=key, kind=case['kind'], status=result['status'],
                    score_original=result['evaluation'], score_v023=value, expression_review=diagnostic))
        begun = {e['payload']['case_id'] for e in events if e['kind'] == 'JSON_CASE_STARTED'}
        ended = {r['task_id'] for r in rows}
        if (summary['started_case_count'] != len(begun) or summary['terminated_case_count'] != len(ended) or
                summary['interrupted_cases'] != sorted(begun - ended) or
                summary['not_dispatched'] != [k for k in freeze['case_order'] if k not in begun]):
            raise ValueError('SOURCE_PARTIAL_COUNTS_CHANGED')
        return dict(status='OFFLINE_FIXED_MEASUREMENT_REVIEW_VERIFIED', version=VERSION, profile=profile,
            source_root=output.relative_to(base.ROOT).as_posix(), source_anchor=summary['anchor'],
            cases=len(rows), model_calls=0, tool_calls=0, container_calls=0,
            original_scores_unchanged=True, not_dispatched=summary['not_dispatched'],
            strict_pass_count=sum(r['score_v023'].get('task_pass', r['score_v023'].get('score', {}).get('full_pass', False)) for r in rows),
            expression_reviews_not_scores=sum(r['expression_review'] is not None for r in rows), results=rows)


def prepare():
    if (PACK / 'freeze.json').exists():
        raise ValueError('MEASUREMENT_VERSION_ALREADY_FROZEN')
    comparison.validate()
    cases, tools = base.read(comparison.PACK / 'cases.json'), base.read(comparison.PACK / 'action_contract.json')
    public = base.read(comparison.PACK / 'public_initial_messages.json')
    for key, messages in public.items():
        if cases[key]['kind'] == 'CODE':
            continue
        original = json.loads(messages[-1]['content'])
        corrected = public_context(cases[key], tools, [], [])['action_contract']
        original['action_contract'].update({k: corrected[k] for k in ('version', 'FINAL', 'format_only_FINAL_example', 'example_scope')})
        messages[-1]['content'] = json.dumps(original, sort_keys=True)
    PACK.mkdir(parents=True, exist_ok=False)
    base.save(PACK / 'public_initial_messages.json', public)
    base.save(PACK / 'action_contract.json', public_context(cases['Q-DA-01'], tools, [], [])['action_contract'])
    paths = [Path(__file__), base.ROOT / 'tests/test_workflow_measurement_v023.py',
        comparison.PACK / 'freeze.json', core.PACK / 'freeze.json',
        PACK / 'public_initial_messages.json', PACK / 'action_contract.json']
    base.save(PACK / 'freeze.json', dict(version=VERSION, public_contract_version=PUBLIC_VERSION,
        runtime=base.dependency_lock(), sha256={p.relative_to(base.ROOT).as_posix(): kernel.sha(p) for p in paths},
        engineering=dict(max_test_commands=4, real_calls=0), real_execution_authorized=False,
        legacy_policy='Strict failures retained; symmetric expression diagnostics are not admitted scores',
        labels=['PUBLIC', 'UNSEALED', 'PROVISIONAL']))


def validate():
    freeze = base.read(PACK / 'freeze.json')
    if freeze['runtime'] != base.dependency_lock():
        raise ValueError('MEASUREMENT_RUNTIME_CHANGED')
    for path, pin in freeze['sha256'].items():
        if kernel.sha(base.ROOT / path) != pin:
            raise ValueError('MEASUREMENT_BINDING_CHANGED:' + path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'review'])
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare()
        print(json.dumps(dict(status='PREPARED_OFFLINE_ONLY', real_calls=0)))
        return
    validate()
    target = PACK / 'REEVALUATION.json'
    if args.write and target.exists():
        raise ValueError('APPENDED_REVIEW_ALREADY_EXISTS')
    result = dict(version=VERSION, model_calls=0, tool_calls=0, container_calls=0,
        reviews=[review(profile) for profile in ('luna', 'mimo', 'deepseek')])
    if args.write:
        base.save(target, result)
    print(json.dumps([{k: v for k, v in r.items() if k != 'results'} for r in result['reviews']], ensure_ascii=False))


if __name__ == '__main__':
    main()
