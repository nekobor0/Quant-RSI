"""Versioned Chat workflow loop. Canonical B1/B2 budgets, tools and facts reused."""
import argparse
import copy
import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from quant_rsi.agents.worker import WorkerRequest
from quant_rsi.contracts.condition import BenchmarkCondition
from quant_rsi.harness import agent_workflow as base
from quant_rsi.harness.workflow_chat import ChatWorkflowAdapter, MockChatTransport, messages
from quant_rsi.harness.workflow_oracle import conclusion_check, observed_support, same, frozen_observation
from quant_rsi.harness.workflow_tools import validate_call
from quant_rsi.harness.providers import ProviderReply
from quant_rsi.ledger.budget import BudgetDenied, _usage
from quant_rsi.ledger.store import TraceStore, verify_events

PACK = base.PACK / 'v02'
PROCESS_PROFILES = {
    'illegal_tool': 'WFA-01-anomaly', 'early_final': 'WFA-01-anomaly',
    'wrong_reference': 'WFA-01-anomaly', 'future_claim': 'WFA-02-available',
    'exhausted_trial': 'WFA-03-exhausted', 'tool_failure_claim': 'WFA-01-normal',
}


def suite():
    old, cases, contract = base.suite()
    freeze = base.read(PACK / 'freeze.json')
    if freeze['base_freeze_sha256'] != sha256((base.PACK / 'freeze.json').read_bytes()).hexdigest():
        raise ValueError('V01_BASE_CHANGED')
    for ref, expected in freeze['sha256'].items():
        if sha256((base.ROOT / ref).read_bytes()).hexdigest() != expected:
            raise ValueError('V02_FREEZE_CHANGED: ' + ref)
    contract = copy.deepcopy(contract)
    contract.update(version='TRACK_A_AGENT_WORKFLOW_V0.2',
        execution_boundary='Supervisor fixture tools and controlled mock Chat only. No network.',
        token_limits=freeze['tokens'], usage_rule='Reasoning is a subset of output, never added twice.')
    cases = copy.deepcopy(cases)
    for case in cases.values():
        case['ledger_task']['budget_limits'].update(
            input_tokens=freeze['tokens']['task_input'], output_tokens=freeze['tokens']['task_output'])
    return freeze, cases, contract


def context_for(case, contract, observations, history):
    return base.public_context(case, contract, observations, history)


def usage_resources(reply):
    values = (reply.input_tokens, reply.output_tokens, reply.reasoning_tokens)
    if any(type(v) is not int or v < 0 for v in values[:2]):
        return None
    if values[2] is not None and (type(values[2]) is not int or not 0 <= values[2] <= values[1]):
        return None
    return {'input_tokens': values[0], 'output_tokens': values[1],
            'wall_milliseconds': reply.wall_ms, 'cpu_milliseconds': 0}


def run_workflow(store, case_id, agent, run_id):
    if type(agent) is not ChatWorkflowAdapter:
        raise ValueError('CONTROLLED_CHAT_ADAPTER_REQUIRED')
    freeze, cases, contract = suite()
    case = cases[case_id]
    # Identity/root claim and synthetic trial setup reuse v0.1 without resetting search.
    budget, run, tools = base.setup_budget(store, case, agent, run_id, freeze, contract)
    store.append('v02-start:' + run_id, 'V02_STARTED', {
        'run_id': run_id, 'case_id': case_id, 'case_hash': base.digest(case),
        'freeze_sha256': sha256((PACK / 'freeze.json').read_bytes()).hexdigest(),
        'contract_hash': base.digest(contract), 'budget_limits': dict(tools.task.budget_limits)})
    observations, history, final = [], [], None
    status, error = 'MAX_STEPS_EXCEEDED', None
    for step in range(1, 9):
        attempt = f'CHAT-{run_id}-{step}'
        envelope = base._envelope(budget, run)
        envelope.update(input_tokens=freeze['tokens']['request_input'],
                        output_tokens=freeze['tokens']['request_output'])
        try:
            budget.reserve(run_id, attempt, envelope)
        except BudgetDenied:
            status, error = 'BUDGET_EXHAUSTED', 'CHAT_BUDGET_DENIED'
            break
        context = context_for(case, contract, observations, history)
        request = WorkerRequest(run_id, 'ACT-' + run_id, 'CTX-' + run_id, agent.provider_id,
            agent.model_id, 'workflow-v02', base.digest(context), base.digest(contract), tuple(case['tools']),
            {'context': base.digest(context), 'case': base.digest(case), 'fixture': base.digest(case['fixture'])})
        store.append('v02-request:' + attempt, 'V02_CHAT_REQUEST',
            {'run_id': run_id, 'step': step, 'attempt_id': attempt,
             'request': request.to_dict(), 'context': copy.deepcopy(context)})
        # Bound the actual serialized input conservatively: UTF-8 bytes upper-bound
        # tokens for these fixtures, rather than relying on a missing native tokenizer.
        if len(json.dumps(messages(context)).encode()) > envelope['input_tokens']:
            status, error = 'BUDGET_EXHAUSTED', 'INPUT_RESERVATION_TOO_SMALL'
            budget.settle(attempt, 'FAILED', dict(input_tokens=0, output_tokens=0,
                wall_milliseconds=0, cpu_milliseconds=0), failure=error)
            break
        try:
            reply = agent.step(request, context)
        except (Exception, KeyboardInterrupt) as exc:
            # Partial exchange + unreconciled reservation survive failures/interruption.
            failure = 'WORKFLOW_INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'CHAT_ADAPTER_FAILED'
            reply = ProviderReply(False, None, None, failure, None, None, 0, 1,
                                  failure_class=failure)
            if not agent.last_exchange or agent.last_exchange['messages_hash'] != base.digest(messages(context)):
                agent.last_exchange = {'messages': messages(context), 'messages_hash': base.digest(messages(context)),
                                       'request_body': None, 'response': None}
        raw, action = reply.text, None
        error = reply.failure_type
        if not error and reply.observed_model != agent.model_id:
            error = 'PROVIDER_MODEL_MISMATCH'
        if not error and reply.finish_reason != 'stop':
            error = 'FINISH_REASON_UNKNOWN'
        if not error:
            try:
                action = base.parse_action(raw)
            except json.JSONDecodeError:
                error = 'ACTION_JSON_INVALID'
            except (ValueError, TypeError):
                error = 'ACTION_SCHEMA_INVALID'
        resources = usage_resources(reply)
        if resources is None:
            error = error or 'USAGE_UNKNOWN_OR_INVALID'
        store.append('v02-action:' + attempt, 'V02_CHAT_ACTION', {
            'run_id': run_id, 'step': step, 'attempt_id': attempt, 'raw': raw,
            'action': action, 'error': error, 'reply': asdict(reply),
            'exchange': agent.last_exchange, 'cost': {'budget_root_run_id': run_id,
                'actual': reply.cost, 'currency': reply.currency, 'state': 'NOT_PRICED_SIMULATION'}})
        budget.settle(attempt, 'FAILED' if error else 'SUCCEEDED', resources,
            artifact_hashes={'action': base.digest(action)} if not error else {}, failure=error)
        history.append(action)
        if error:
            status = 'PROVIDER_FAILED' if error not in ('ACTION_JSON_INVALID', 'ACTION_SCHEMA_INVALID') else 'INVALID_ACTION'
            break
        if budget.capability_accounting(run_id)['blocked']:
            status, error = 'BUDGET_EXHAUSTED', 'CHAT_USAGE_BREACH'
            break
        if action['action'] == 'FINAL':
            final, status = action, 'COMPLETED'
            if any(t['state'] != 'SETTLED' for t in tools.trials.values()):
                status, error = 'INVALID_ACTION', 'FINAL_WITH_UNSETTLED_TRIAL'
            break
        try:
            validate_call(action['tool'], action['arguments'], case['tools'])
        except ValueError:
            status, error = 'INVALID_ACTION', 'TOOL_CONTRACT_REJECTED'
            break
        tool_attempt = f'TOOL-{run_id}-{step}'
        try:
            budget.reserve(run_id, tool_attempt, base._envelope(budget, run, tool=True))
        except BudgetDenied:
            status, error = 'BUDGET_EXHAUSTED', 'TOOL_BUDGET_DENIED'
            break
        observation = {'observation_id': f'OBS-{run_id}-{step}', 'run_id': run_id, 'step': step,
            'tool': action['tool'], 'arguments': action['arguments'], 'attempt_id': tool_attempt,
            'ok': True, 'result': None, 'error': None}
        try:
            observation['result'] = tools.execute(action['tool'], action['arguments'])
        except BudgetDenied:
            observation.update(ok=False, error='TRIAL_BUDGET_DENIED')
        except ValueError:
            observation.update(ok=False, error='TOOL_REFERENCE_OR_STATE_INVALID')
        except Exception:
            observation.update(ok=False, error='TOOL_EXECUTION_FAILED')
        observation = copy.deepcopy(observation)
        store.append('v02-observation:' + tool_attempt, 'WORKFLOW_TOOL_RESULT', observation)
        budget.settle(tool_attempt, 'SUCCEEDED' if observation['ok'] else 'FAILED',
            dict(input_tokens=0, output_tokens=0, wall_milliseconds=0, cpu_milliseconds=0),
            artifact_hashes={'observation': base.digest(observation)} if observation['ok'] else {},
            failure=observation['error'])
        observations.append(observation)
        tools.observations[observation['observation_id']] = observation
        if observation['error'] == 'TRIAL_BUDGET_DENIED':
            status, error = 'BUDGET_EXHAUSTED', 'TRIAL_BUDGET_DENIED'
            break
        # A failed tool observation may be examined next round, never relabelled success.
    payload = {'run_id': run_id, 'case_id': case_id, 'model_id': agent.model_id,
        'status': status, 'error': error, 'final': final, 'steps': len(history), 'tool_calls': len(observations),
        'usage': budget.capability_accounting(run_id),
        'synthetic_trial_accounting': budget.scientific_accounting(run.scientific_family_id),
        'real_agent_ability': 'UNVERIFIED', 'strategy_scientific_pass': False}
    store.append('v02-end:' + run_id, 'V02_COMPLETED', payload)
    payload['evaluation'] = evaluate(case, payload, store.read())
    store.append('v02-eval:' + run_id, 'V02_EVALUATED', {'run_id': run_id, **payload['evaluation']})
    return payload


def verify_trace(case, result, events, contract):
    """Pure frozen-observation validation; no tool/provider execution during replay."""
    verify_events(events)
    run_id = result['run_id']
    by_id = {e['event_id']: e for e in events}
    start = by_id['v02-start:' + run_id]['payload']
    if start != {'run_id': run_id, 'case_id': case['case_id'], 'case_hash': base.digest(case),
            'freeze_sha256': sha256((PACK / 'freeze.json').read_bytes()).hexdigest(),
            'contract_hash': base.digest(contract), 'budget_limits': case['ledger_task']['budget_limits']}:
        raise ValueError('V02_BINDING_CHANGED')
    registered = by_id['run:' + run_id]['payload']
    condition = BenchmarkCondition.from_dict(by_id['condition:' + registered['condition_hash']]['payload'])
    if condition.task.to_dict() != case['ledger_task']:
        raise ValueError('CONDITION_CHANGED')
    observations, history, trials = [], [], {}
    requests = [e for e in events if e['kind'] == 'V02_CHAT_REQUEST' and e['payload']['run_id'] == run_id]
    for step, event in enumerate(requests, 1):
        recorded = event['payload']
        expected = context_for(case, contract, observations, history)
        worker = WorkerRequest.from_dict(recorded['request'])
        expected_worker = WorkerRequest(run_id, 'ACT-' + run_id, 'CTX-' + run_id,
            registered['provider'], registered['agent_model'], 'workflow-v02', base.digest(expected),
            base.digest(contract), tuple(case['tools']),
            {'context': base.digest(expected), 'case': base.digest(case), 'fixture': base.digest(case['fixture'])})
        if worker != expected_worker or recorded['context'] != expected or recorded['step'] != step:
            raise ValueError('CONTEXT_OR_WORKER_CHANGED')
        attempt = recorded['attempt_id']
        reserved, settled = by_id['attempt:' + attempt], by_id['settle:' + attempt]
        action_event = by_id.get('v02-action:' + attempt)
        if not action_event:  # Input preflight denial: no dispatch, actual zero.
            if settled['payload']['failure'] != 'INPUT_RESERVATION_TOO_SMALL':
                raise ValueError('MISSING_CHAT_RESPONSE')
            continue
        if not reserved['sequence'] < event['sequence'] < action_event['sequence'] < settled['sequence']:
            raise ValueError('RESERVATION_ORDER_CHANGED')
        response = action_event['payload']
        exchange = response['exchange']
        if exchange['messages'] != messages(expected) or exchange['messages_hash'] != base.digest(messages(expected)):
            raise ValueError('CHAT_TRANSCRIPT_CHANGED')
        body = exchange['request_body']
        if body is None and response['error'] not in ('CHAT_ADAPTER_FAILED', 'WORKFLOW_INTERRUPTED'):
            raise ValueError('MISSING_CHAT_BODY')
        if body is not None and (body['messages'] != messages(expected) or body['model'] != registered['agent_model']
                or body['max_tokens'] != 2048 or body['stream'] is not False):
            raise ValueError('CHAT_BODY_CHANGED')
        reply = ProviderReply(**response['reply'])
        if settled['payload']['actual_resources'] != usage_resources(reply) or response['raw'] != reply.text:
            raise ValueError('USAGE_OR_RAW_CHANGED')
        native = exchange['response']
        if native and native.get('choices') and not native.get('error'):
            choice = native['choices'][0]
            usage = native.get('usage') or {}
            content = choice['message'].get('content')
            content = content if isinstance(content, str) and content.strip() else None
            reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens', usage.get('reasoning_tokens'))
            if (reply.text != content or reply.finish_reason != choice.get('finish_reason')
                    or reply.input_tokens != usage.get('prompt_tokens')
                    or reply.output_tokens != usage.get('completion_tokens')
                    or reply.reasoning_tokens != reasoning or reply.observed_model != native.get('model')):
                raise ValueError('NATIVE_RESPONSE_CHANGED')
        try:
            parsed = base.parse_action(response['raw']) if not reply.failure_type and reply.finish_reason == 'stop' and reply.observed_model == registered['agent_model'] else None
        except (ValueError, TypeError):
            parsed = None
        action = response['action']
        if action != parsed:
            raise ValueError('ACTION_CHANGED')
        if not response['error'] and settled['payload']['artifact_hashes'] != {'action': base.digest(action)}:
            raise ValueError('ACTION_HASH_CHANGED')
        history.append(action)
        tool_id = f'TOOL-{run_id}-{step}'
        observation_event = by_id.get('v02-observation:' + tool_id)
        if not observation_event:
            continue
        if not action or action['action'] != 'TOOL_CALL':
            raise ValueError('UNAUTHORIZED_OBSERVATION')
        validate_call(action['tool'], action['arguments'], case['tools'])
        observation = observation_event['payload']
        tr, ts = by_id['attempt:' + tool_id], by_id['settle:' + tool_id]
        if (observation['tool'] != action['tool'] or observation['arguments'] != action['arguments']
                or observation['observation_id'] != f'OBS-{run_id}-{step}'
                or not action_event['sequence'] < tr['sequence'] < observation_event['sequence'] < ts['sequence']):
            raise ValueError('TOOL_ORDER_OR_BINDING_CHANGED')
        if observation['ok']:
            expected_result = frozen_observation(case, observation, observations,
                events[:observation_event['sequence'] - 1], run_id)
            if observation['result'] != expected_result or ts['payload']['artifact_hashes'] != {'observation': base.digest(observation)}:
                raise ValueError('FROZEN_OBSERVATION_CHANGED')
            name = observation['tool']
            if name == 'reserve_trial':
                trial = observation['result']['trial_ref']
                trial_reserve = by_id['attempt:' + trial]
                if (trial in trials or trial_reserve['payload']['envelope']['candidate_trials'] != 1
                        or not tr['sequence'] < trial_reserve['sequence'] < observation_event['sequence']):
                    raise ValueError('TRIAL_RESERVE_INVALID')
                trials[trial] = 'RESERVED'
            elif name in ('run_synthetic_trial', 'settle_trial'):
                trial = observation['arguments']['trial_ref']
                required = 'RESERVED' if name == 'run_synthetic_trial' else 'EXECUTED'
                if trials.get(trial) != required:
                    raise ValueError('TRIAL_TRANSITION_INVALID')
                mid = by_id[('trial-result:' if name == 'run_synthetic_trial' else 'settle:') + trial]
                if not tr['sequence'] < mid['sequence'] < observation_event['sequence']:
                    raise ValueError('TRIAL_EVENT_ORDER_INVALID')
                trials[trial] = 'EXECUTED' if name == 'run_synthetic_trial' else 'SETTLED'
        elif observation['result'] is not None or ts['payload']['status'] != 'FAILED' or not observation['error']:
            raise ValueError('TOOL_FAILURE_DISGUISED')
        observations.append(observation)
    used, blocked = _usage(events, registered['budget_root_run_id'])
    if (used != result['usage']['usage'] or blocked != result['usage']['blocked']
            or result['steps'] != len(history) or result['tool_calls'] != len(observations)):
        raise ValueError('COUNTS_CHANGED')
    if result['final'] is not None and (not history or result['final'] != history[-1]):
        raise ValueError('FINAL_CHANGED')
    if result['status'] == 'COMPLETED' and any(v != 'SETTLED' for v in trials.values()):
        raise ValueError('UNSETTLED_TRIAL')
    return observations


def evaluate(case, result, events):
    _, _, contract = suite()
    trace_ok = True
    try:
        observations = verify_trace(case, result, events, contract)
    except (ValueError, KeyError, TypeError, StopIteration):
        trace_ok = False
        observations = [e['payload'] for e in events if e['kind'] == 'WORKFLOW_TOOL_RESULT'
                        and e['payload']['run_id'] == result['run_id']]
    final = result['final']
    correct, normalized, issues = conclusion_check(case, final['conclusion']) if final else (None, {}, ['NO_FINAL'])
    successful = {o['observation_id']: o for o in observations if o['ok']}
    cited = set(final['evidence']) if final else set()
    refs_valid = bool(final) and cited <= set(successful)
    support = observed_support(case, list(successful.values()))
    cited_support = observed_support(case, [successful[r] for r in cited if r in successful])
    # WFA-01/02 support needs the setup observation as well, even when citations
    # need only the derived checks; augment setup only, never omitted fact evidence.
    setup = {'WFA-01': 'read_fixture', 'WFA-02': 'list_vintages', 'WFA-03': None}[case['workflow_id']]
    supplemented = [successful[r] for r in cited if r in successful] + [
        o for o in successful.values() if o['tool'] == setup]
    if case['workflow_id'] == 'WFA-03' and case.get('prior_trials') == 1:
        supplemented += [o for o in successful.values() if o['tool'] in ('inspect_budget', 'reserve_trial')]
    cited_support = observed_support(case, supplemented)
    used = bool(final and refs_valid and cited_support is not None and all(
        same(normalized.get(f), v, case['conclusion_contract'][f]['type']) for f, v in cited_support.items()))
    required = set(case['reference']['required_tools']) <= {o['tool'] for o in successful.values()}
    failed_tools = any(not o['ok'] for o in observations)
    denied = any(e['kind'] == 'ATTEMPT_DENIED' and e['payload']['benchmark_run_id'] == result['run_id'] for e in events)
    compliant = not denied and not result['usage']['blocked'] and result['steps'] <= 8 and result['tool_calls'] <= 6
    actions = [e['payload']['action'] for e in events if e['kind'] == 'V02_CHAT_ACTION'
               and e['payload']['run_id'] == result['run_id']]
    selection = result['error'] not in ('TOOL_CONTRACT_REJECTED', 'ACTION_SCHEMA_INVALID')
    selection = selection and not any(o['error'] == 'TOOL_REFERENCE_OR_STATE_INVALID' for o in observations)
    state_valid = result['status'] == 'COMPLETED' and required and not failed_tools and refs_valid
    tags = []
    if not selection:
        tags.append('ILLEGAL_TOOL_OR_ARGUMENT')
    if final and not required:
        tags.append('FINAL_WITHOUT_REQUIRED_OBSERVATIONS')
    if final and not refs_valid:
        tags.append('INVALID_OBSERVATION_REFERENCE')
    if failed_tools:
        tags.append('TOOL_EXECUTION_FAILED')
        if final:
            tags.append('FINAL_AFTER_UNRESOLVED_TOOL_FAILURE')
    if not compliant:
        tags.append('BUDGET_VIOLATION_OR_UNRESOLVED_USAGE')
    if final and correct is False:
        tags.append('WRONG_RESEARCH_CONCLUSION')
    if final and case['workflow_id'] == 'WFA-02' and normalized.get('selected_vintage'):
        chosen = normalized['selected_vintage']
        rejected = {c['vintage_id'] for o in successful.values() if o['tool'] == 'check_asof_eligibility'
                    for c in o['result']['checks'] if not c['eligible']}
        if chosen in rejected:
            tags.append('FUTURE_OR_INELIGIBLE_VINTAGE_CLAIM')
            state_valid = False
    signatures = [(a['tool'], base.digest(a['arguments'])) for a in actions if a and a['action'] == 'TOOL_CALL']
    if len(signatures) != len(set(signatures)):
        tags.append('REDUNDANT_LEGAL_TOOL_CALL')
    if any(o['tool'] == 'read_vintage' and o['ok'] and not o['result']['eligible'] for o in observations) and correct:
        tags.append('LEGAL_REJECTED_VINTAGE_AUDIT')
    vector = {'FINAL_DECISION_CORRECT': correct, 'TOOL_SELECTION_VALID': selection,
        'TOOL_RESULT_USED_CORRECTLY': used if final else None, 'STATE_TRANSITION_VALID': state_valid,
        'BUDGET_COMPLIANT': compliant, 'EVIDENCE_TRACE_COMPLETE': trace_ok and (refs_valid if final else True)}
    return {'version': 'workflow-evaluator-v02', 'vector': vector,
        'hard_gates': {'execution_completed': result['status'] == 'COMPLETED' and not failed_tools,
                       'actual_required_tools': required, 'trace_and_budget': trace_ok and compliant},
        'workflow_pass': all(v is True for v in vector.values()), 'diagnostics': tags,
        'failed_predicates': issues, 'trace_integrity': trace_ok,
        'failure_class': 'PROVIDER_FAILURE_NOT_RESEARCH' if result['status'] == 'PROVIDER_FAILED' else
            'EXECUTION_FAILURE_NOT_RESEARCH' if result['status'] != 'COMPLETED' else
            'WRONG_RESEARCH_CONCLUSION' if correct is False else None,
        'single_total_score': None, 'strategy_scientific_pass': False, 'D08_achieved': False}


def replay(events, result, *, expected_anchor):
    verify_events(events, expected_anchor)
    _, cases, contract = suite()
    verify_trace(cases[result['case_id']], result, events, contract)
    by_id = {e['event_id']: e['payload'] for e in events}
    if by_id['v02-end:' + result['run_id']] != {k: v for k, v in result.items() if k != 'evaluation'}:
        raise ValueError('RESULT_CHANGED')
    scored = evaluate(cases[result['case_id']], result, events)
    if scored != result['evaluation'] or by_id['v02-eval:' + result['run_id']] != {'run_id': result['run_id'], **scored}:
        raise ValueError('SCORE_CHANGED')
    return {'run_id': result['run_id'], 'status': 'FROZEN_REPLAY_MATCH', 'model_calls': 0, 'tool_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PACK / 'offline_run')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    freeze, _, _ = suite()
    store = TraceStore(args.output / 'trace.sqlite')
    profiles = [(case, profile) for case in freeze['case_order'] for profile in ('correct', 'wrong_final')]
    profiles += [(case, profile) for profile, case in PROCESS_PROFILES.items()]
    results = [run_workflow(store, case, ChatWorkflowAdapter(MockChatTransport(profile)),
        'RUN-v02-' + case + '-' + profile) for case, profile in profiles]
    events, anchor = store.read(), store.checkpoint()
    replayed = [replay(events, r, expected_anchor=anchor) for r in results]
    paired = [r for r in results if r['case_id'].startswith('WFA-02') and r['model_id'] == 'simulated-chat-correct']
    first = [next(e['payload'] for e in events if e['kind'] == 'V02_CHAT_REQUEST'
                  and e['payload']['run_id'] == r['run_id']) for r in paired]
    counterfactual = {'same_initial_context': first[0]['context'] == first[1]['context'],
        'initial_prompt_hashes': [p['request']['prompt_hash'] for p in first],
        'same_first_action': all(next(e['payload']['action'] for e in events if e['kind'] == 'V02_CHAT_ACTION'
            and e['payload']['run_id'] == r['run_id']) == {'action': 'TOOL_CALL', 'tool': 'list_vintages', 'arguments': {}} for r in paired),
        'changed_final': paired[0]['final']['conclusion'] != paired[1]['final']['conclusion'],
        'fixture_variants': [r['case_id'] for r in paired], 'interpretation': 'mock_response_dependence_only'}
    report = {'status': 'OFFLINE_CHAT_ENGINEERING_EXECUTED', 'labels': ['PUBLIC', 'UNSEALED', 'PROVISIONAL'],
        'results': results, 'replays': replayed, 'counterfactual': counterfactual,
        'trace_anchor': asdict(anchor), 'real_api_calls': 0, 'real_agent_ability': 'UNVERIFIED',
        'D08': 'NOT_IMPLEMENTED', 'freeze_sha256': sha256((PACK / 'freeze.json').read_bytes()).hexdigest()}
    base.save(args.output / 'results.json', report)
    base.save(args.output / 'trace.json', events)
    print(json.dumps({'executions': len(results), 'replays': len(replayed), 'real_api_calls': 0,
                      'counterfactual': counterfactual}, indent=2))


if __name__ == '__main__':
    main()
