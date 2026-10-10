"""Versioned supplement predicates and pure, frozen-observation replay."""
from hashlib import sha256

from quant_rsi.agents.worker import WorkerRequest
from quant_rsi.contracts.condition import AgentBenchmarkRun, BenchmarkCondition
from quant_rsi.harness.agent_workflow import digest, parse_action, read
from quant_rsi.harness.supplement_tasks import fact_predicates, VERSION
from quant_rsi.harness.workflow_chat import messages
from quant_rsi.harness.workflow_v02 import usage_resources
from quant_rsi.harness.providers import ProviderReply
from quant_rsi.ledger.budget import _usage
from quant_rsi.ledger.store import Anchor, verify_events


def verify_record(case, result, events):
    from quant_rsi.harness.supplement import PACK, suite, context_for, ACTION_CONTRACT
    verify_events(events)
    freeze, cases = suite()
    run_id = result['run_id']
    if cases[result['case_key']] != case:
        raise ValueError('CASE_CHANGED')
    by_id = {e['event_id']: e for e in events}
    start = by_id['supp-start:' + run_id]['payload']
    if start != dict(run_id=run_id, case_key=result['case_key'], case_hash=digest(case),
        freeze_hash=sha256((PACK / 'freeze.json').read_bytes()).hexdigest(),
        initial_context_hash=digest(context_for(case, [], []))):
        raise ValueError('START_BINDING_CHANGED')
    registered = AgentBenchmarkRun.from_dict(by_id['run:' + run_id]['payload'])
    condition = BenchmarkCondition.from_dict(by_id['condition:' + registered.condition_hash]['payload'])
    if condition.task.to_dict() != case['ledger_task'] or registered.code_hash != digest(freeze['sha256']):
        raise ValueError('RUN_CONDITION_CHANGED')
    condition.task.verify_frozen_condition(by_id[condition.task.decision_snapshot_ref]['payload'])
    if registered.prompt_hash != start['initial_context_hash'] or registered.dependency_hash != digest(freeze['runtime']):
        raise ValueError('RUN_PROMPT_OR_RUNTIME_CHANGED')
    observations, history = [], []
    requests = [e for e in events if e['kind'] == 'SUPPLEMENT_CHAT_REQUEST' and e['payload']['run_id'] == run_id]
    for step, event in enumerate(requests, 1):
        entry = event['payload']
        context = context_for(case, observations, history)
        worker = WorkerRequest(run_id, 'ACT-' + run_id, 'CTX-' + run_id, registered.provider,
            registered.agent_model, VERSION, digest(context), digest(ACTION_CONTRACT), tuple(context['allowed_tools']),
            {'context': digest(context), 'fixture': digest(case['fixture']), 'case': digest(case)})
        if entry['step'] != step or entry['context'] != context or entry['request'] != worker.to_dict():
            raise ValueError('CONTEXT_CHANGED')
        attempt = entry['attempt_id']
        reservation, settlement = by_id['attempt:' + attempt], by_id['settle:' + attempt]
        if reservation['kind'] != 'ATTEMPT_STARTED' or reservation['payload']['budget_root_run_id'] != run_id:
            raise ValueError('ATTEMPT_ROOT_CHANGED')
        action_event = by_id.get('supp-action:' + attempt)
        if action_event is None:
            if settlement['payload']['failure'] != 'INPUT_RESERVATION_TOO_SMALL':
                raise ValueError('MISSING_RESPONSE')
            continue
        if not reservation['sequence'] < event['sequence'] < action_event['sequence'] < settlement['sequence']:
            raise ValueError('EVENT_ORDER_CHANGED')
        entry = action_event['payload']
        exchange = entry['exchange']
        if (exchange['messages'] != messages(context) or exchange['messages_hash'] != digest(messages(context))
                or exchange['request_body']['messages'] != messages(context)
                or exchange['request_body']['model'] != registered.agent_model
                or exchange['request_body']['max_tokens'] != 2048):
            raise ValueError('CHAT_MESSAGES_CHANGED')
        reply = ProviderReply(**entry['reply'])
        if entry['raw'] != reply.text or settlement['payload']['actual_resources'] != usage_resources(reply):
            raise ValueError('REPLY_OR_USAGE_CHANGED')
        if entry['action'] is not None and parse_action(entry['raw']) != entry['action']:
            raise ValueError('ACTION_CHANGED')
        if not entry['error'] and settlement['payload']['artifact_hashes'].get('action') != digest(entry['action']):
            raise ValueError('ACTION_ARTIFACT_CHANGED')
        history.append(entry['action'])
        observation_event = by_id.get(f'supp-observation:TOOL-{run_id}-{step}')
        if observation_event:
            observation = observation_event['payload']
            action = entry['action']
            tool_attempt = observation['attempt_id']
            reserved, settled = by_id['attempt:' + tool_attempt], by_id['settle:' + tool_attempt]
            if (action['action'] != 'TOOL_CALL' or observation['tool'] != action['tool'] or
                    observation['arguments'] != action['arguments'] or observation['run_id'] != run_id or
                    observation['observation_id'] != f'OBS-{run_id}-{step}' or
                    reserved['payload']['budget_root_run_id'] != run_id or
                    not settlement['sequence'] < reserved['sequence'] < observation_event['sequence'] < settled['sequence']):
                raise ValueError('OBSERVATION_BINDING_CHANGED')
            if observation['ok']:
                if settled['payload']['status'] != 'SUCCEEDED' or settled['payload']['artifact_hashes'].get('observation') != digest(observation):
                    raise ValueError('OBSERVATION_ARTIFACT_CHANGED')
            elif settled['payload']['failure'] != observation['error']:
                raise ValueError('FAILURE_CHANGED')
            observations.append(observation)
    if len(history) != result['steps'] or len(observations) != result['tool_calls']:
        raise ValueError('STEP_COUNTS_CHANGED')
    if result['final'] is not None and (not history or history[-1] != result['final']):
        raise ValueError('FINAL_CHANGED')
    usage, blocked = _usage(events, run_id)
    if result['usage']['usage'] != usage or result['usage']['blocked'] != blocked or result['usage']['budget_root_run_id'] != run_id:
        raise ValueError('BUDGET_ACCOUNTING_CHANGED')
    if result['supervisor'] is not None:
        if by_id['supervisor-stop:' + run_id]['payload'] != dict(run_id=run_id, conclusion=result['supervisor']):
            raise ValueError('SUPERVISOR_RECEIPT_CHANGED')
    return observations


def evaluate(case, result, events):
    trace_ok = True
    try:
        observations = verify_record(case, result, events)
    except (ValueError, KeyError, TypeError):
        trace_ok = False
        observations = [e['payload'] for e in events if e['kind'] == 'SUPPLEMENT_TOOL_RESULT'
                        and e['payload']['run_id'] == result['run_id']]
    final = result['final']
    conclusion = final['conclusion'] if final else result['supervisor']
    predicates = fact_predicates(case, conclusion)
    correct = all(predicates.values()) if conclusion is not None else None
    successful = {o['observation_id']: o for o in observations if o['ok']}
    actions = [e['payload']['action'] for e in events if e['kind'] == 'SUPPLEMENT_CHAT_ACTION'
               and e['payload']['run_id'] == result['run_id']]
    legal_selection = not any(a and a['action'] == 'TOOL_CALL' and
        (a['tool'] not in case['stages'] + case.get('optional_tools', []) or
         set(a['arguments']) != {'observations'}) for a in actions)
    required = set(case['stages'])
    if case['task_id'] == 'Q-AT-02':
        versions = next((o['result'] for o in observations if o['tool'] == 'inspect_versions' and o['ok']), None)
        required = {'inspect_versions', 'read_eligible_version' if versions and versions['eligible'] else 'inspect_backup'}
    actual_tools = {o['tool'] for o in observations if o['ok']}
    refs = set(final['evidence']) if final else set()
    if case['kind'] == 'STRUCTURED':
        refs_valid = bool(final) and refs == {'INPUT:' + case['task_id']}
        used = refs_valid and bool(correct)
        required_ok = True
    else:
        terminal_obs = next((o for o in reversed(observations) if o['ok']), None)
        refs_valid = bool(final and refs and refs <= set(successful))
        direct_tools = {successful[r]['tool'] for r in refs if r in successful}
        refs_valid = bool(refs_valid and terminal_obs and terminal_obs['observation_id'] in refs
                          and set(case['required_direct_citations']) <= direct_tools)
        required_ok = required <= actual_tools
        used = bool(final and refs_valid and required_ok and terminal_obs and
                    all(fact_predicates({**case, 'reference': terminal_obs['result']}, final['conclusion']).values()))
    denied = any(e['kind'] == 'ATTEMPT_DENIED' and e['payload']['budget_root_run_id'] == result['run_id'] for e in events)
    stopped = (case['task_id'] == 'Q-AT-03' and result['status'] == 'EXECUTION_INCOMPLETE' and
        result['supervisor'] is not None and result['usage']['blocked'] and result['tool_calls'] == 1 and
        result['transport_calls'] == 1 and not denied and trace_ok and bool(correct))
    settlements = [e for e in events if e['kind'] == 'ATTEMPT_SETTLED' and
                   result['run_id'] in e['payload']['attempt_id']]
    breach = any(e['payload']['usage_state'] == 'BREACH' for e in settlements)
    unknown_stopped = all(not any(e['kind'] == 'ATTEMPT_STARTED' and
        e['payload']['budget_root_run_id'] == result['run_id'] and e['sequence'] > s['sequence'] for e in events)
        for s in settlements if s['payload']['usage_state'] == 'UNKNOWN')
    compliant = not denied and not breach and unknown_stopped and result['steps'] <= 8 and result['tool_calls'] <= 6
    state_ok = bool(final and required_ok and refs_valid and all(o['ok'] for o in observations)) or stopped
    future_claim = bool(final and case['task_id'] == 'Q-AT-02' and
        final['conclusion'].get('selected_vintage') in {v['id'] for v in case['fixture']['versions']
                                                     if v['available'] > case['input']['cutoff']})
    if future_claim:
        state_ok = False
    tags = []
    if not legal_selection:
        tags.append('ILLEGAL_TOOL_OR_ARGUMENT')
    if any(o['error'] == 'INVALID_OBSERVATION_REFERENCE' for o in observations) or (final and not refs_valid):
        tags.append('INVALID_OBSERVATION_REFERENCE')
    if final and not required_ok:
        tags.append('FINAL_WITHOUT_REQUIRED_OBSERVATIONS')
    if any(not o['ok'] for o in observations):
        tags.append('TOOL_EXECUTION_FAILED')
        if final:
            tags.append('FINAL_AFTER_UNRESOLVED_TOOL_FAILURE')
    if future_claim:
        tags.append('FUTURE_VINTAGE_CLAIM')
    if not compliant:
        tags.append('BUDGET_VIOLATION_OR_UNRESOLVED_USAGE')
    elif result['usage']['blocked']:
        tags.append('UNKNOWN_USAGE_STOPPED_RESERVATION_RETAINED')
    if final and correct is False:
        tags.append('WRONG_RESEARCH_CONCLUSION')
    tool_names = [a['tool'] for a in actions if a and a['action'] == 'TOOL_CALL']
    if len(tool_names) != len(set(tool_names)):
        tags.append('REDUNDANT_LEGAL_TOOL_CALL' if legal_selection else 'REPEATED_ILLEGAL_TOOL_CALL')
    if any(t in case.get('optional_tools', []) for t in tool_names):
        tags.append('LEGAL_OPTIONAL_AUDIT_SUBOPTIMAL_COST')
    supervisor_case = case['task_id'] == 'Q-AT-03'
    supervisor_evidence = (supervisor_case and trace_ok and bool(correct) and len(observations) == 1 and
                           not observations[0]['ok'] and result['supervisor'] is not None)
    vector = dict(FINAL_DECISION_CORRECT=None if supervisor_case else correct,
        TOOL_SELECTION_VALID=legal_selection if case['stages'] else None,
        TOOL_RESULT_USED_CORRECTLY=None if supervisor_case else used,
        STATE_TRANSITION_VALID=state_ok, BUDGET_COMPLIANT=compliant,
        EVIDENCE_TRACE_COMPLETE=trace_ok and (supervisor_evidence if supervisor_case else refs_valid))
    method_ok = all(predicates.get(k, False) for k in case['method_fields']) if conclusion is not None else None
    if supervisor_case:
        task_pass = stopped and compliant
    else:
        task_pass = bool(correct) and all(v is True for v in vector.values() if v is not None)
    provider_failed = result['status'] == 'PROVIDER_FAILED'
    return dict(version=VERSION, vector=vector, fact_predicates=predicates,
        method_predicates={k: predicates[k] for k in case['method_fields']}, method_ok=method_ok,
        evidence_predicates=dict(actual_required_observations=required_ok, references_valid=refs_valid,
                                 trace_integrity=trace_ok),
        task_pass=task_pass, diagnostics=tags, failed_predicates=[k for k, v in predicates.items() if v is False]
            if conclusion is not None else ['NO_ASSESSABLE_FINAL'],
        failure_class='PROVIDER_FAILURE_NOT_RESEARCH' if provider_failed else
            'EXECUTION_FAILURE_NOT_RESEARCH' if any(not o['ok'] for o in observations) and not supervisor_case else
            'EXECUTION_FAILURE_NOT_RESEARCH' if result['status'] not in ('COMPLETED', 'EXECUTION_INCOMPLETE') else
            'EXPECTED_SUPERVISOR_STOP_AGENT_DECISION_UNOBSERVABLE' if supervisor_case else
            'WRONG_RESEARCH_CONCLUSION' if correct is False else None,
        final_fact_assessed=conclusion is not None, single_total_score=None,
        real_agent_ability='UNVERIFIED', D08_achieved=False)


def replay(events, result, *, expected_anchor):
    from quant_rsi.harness.supplement import suite
    verify_events(events, expected_anchor)
    _, cases = suite()
    case = cases[result['case_key']]
    verify_record(case, result, events)
    by_id = {e['event_id']: e['payload'] for e in events}
    if by_id['supp-end:' + result['run_id']] != {k: v for k, v in result.items() if k != 'evaluation'}:
        raise ValueError('RESULT_CHANGED')
    scored = evaluate(case, result, events)
    if result['evaluation'] != scored or by_id['supp-eval:' + result['run_id']] != dict(run_id=result['run_id'], **scored):
        raise ValueError('SCORE_CHANGED')
    return dict(status='FROZEN_OBSERVATIONS_REPLAY_MATCH', model_calls=0, tool_reexecutions=0)


def replay_saved(output):
    from quant_rsi.harness.supplement import PACK, suite
    suite()
    manifest = read(output / 'manifest.json')
    if manifest['freeze_hash'] != sha256((PACK / 'freeze.json').read_bytes()).hexdigest():
        raise ValueError('RUN_FREEZE_CHANGED')
    for ref, expected in manifest['sha256'].items():
        if sha256((output / ref).read_bytes()).hexdigest() != expected:
            raise ValueError('RETAINED_ARTIFACT_CHANGED')
    records, traces = read(output / 'results.json'), read(output / 'trace.json')
    if len(records) != manifest['records']:
        raise ValueError('RECORD_COUNT_CHANGED')
    for entry in records:
        result = entry['result']
        replay(traces[result['run_id']], result, expected_anchor=Anchor(**entry['anchor']))
    return dict(replay_matches=len(records), model_calls=0, tool_reexecutions=0)
