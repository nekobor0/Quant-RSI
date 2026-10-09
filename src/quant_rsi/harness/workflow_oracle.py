"""Frozen reference facts and trace checks; no Agent-authored truth or total score."""
from hashlib import sha256

from quant_rsi.agents.worker import WorkerRequest
from quant_rsi.contracts.condition import BenchmarkCondition
from quant_rsi.contracts.data import DataSpec, SnapshotManifest
from quant_rsi.data.pit import PITView, canonical_bytes, instant
from quant_rsi.harness.capability_oracle import _strict_same
from quant_rsi.harness.workflow_tools import validate_call, row_check, vintage_metadata, synthetic_trial
from quant_rsi.ledger.budget import _usage
from quant_rsi.ledger.store import verify_events


def same(value, expected, kind):
    return value is None if expected is None else _strict_same(value, expected, kind)


def conclusion_check(case, conclusion):
    issues, normalized = [], {}
    allowed = set()
    for fact, rule in case['conclusion_contract'].items():
        aliases = rule['aliases']
        allowed.update(aliases)
        values = [conclusion[a] for a in aliases if a in conclusion]
        expected = case['reference']['conclusion'][fact]
        if not values or not all(same(v, expected, rule['type']) for v in values):
            issues.append(fact + ':MISSING_OR_CONTRADICTORY')
        normalized[fact] = values[0] if values else None
    if set(conclusion) - allowed:
        issues.append('UNSUPPORTED_CONCLUSION_FIELDS')
    return not issues, normalized, issues


def observed_support(case, observations):
    seen = {o['tool']: o['result'] for o in observations if o['ok']}
    if case['workflow_id'] == 'WFA-01':
        if not {'read_fixture', 'inspect_response', 'validate_rows'} <= set(seen):
            return None
        rows, meta = seen['validate_rows'], seen['inspect_response']
        return {'verdict': 'ACCEPT' if meta['metadata_consistent'] else 'ACCEPT_WITH_WARNING',
                'effective_rows': rows['effective_rows'], 'accepted_row_ids': rows['accepted_row_ids'],
                'metadata_consistent': meta['metadata_consistent']}
    if case['workflow_id'] == 'WFA-02':
        if not {'list_vintages', 'check_asof_eligibility', 'read_vintage'} <= set(seen):
            return None
        checks = list({c['vintage_id']: c for o in observations
                       if o['tool'] == 'check_asof_eligibility' and o['ok']
                       for c in o['result']['checks']}.values())
        reads = [o['result'] for o in observations if o['tool'] == 'read_vintage' and o['ok']]
        usable_reads = [r for r in reads if r['eligible']]
        row = max(usable_reads, key=lambda r: instant(r['available_at'])) if usable_reads else reads[-1]
        if {c['vintage_id'] for c in checks} != {v['vintage_id'] for v in seen['list_vintages']['vintages']}:
            return None
        chosen = [v for v in checks if v['eligible']]
        if chosen and (not row['eligible'] or row['vintage_id'] not in {c['vintage_id'] for c in chosen}):
            return None
        return {'verdict': 'SELECT_VINTAGE' if chosen else 'REFUSE',
                'selected_vintage': row['vintage_id'] if chosen else None,
                'event_effective_date': row['event_effective_date'] if chosen else None,
                'published_at': row['published_at'] if chosen else None,
                'available_at': row['available_at'] if chosen else None,
                'decision_asof': case['initial']['decision_asof'],
                'future_rejected': all(not c['eligible'] for c in checks
                    if instant(c['available_at']) > instant(case['initial']['decision_asof']))}
    if 'inspect_budget' not in seen:
        return None
    needed = set(case['reference']['required_tools'])
    if not needed <= set(seen):
        return None
    counters = seen.get('settle_trial', seen['inspect_budget'])
    trial = seen.get('run_synthetic_trial', {'evidence_sufficient': False})
    return {'verdict': 'REFUSE_INSUFFICIENT_EVIDENCE', 'used_trials': counters['used_trials'],
            'remaining_trials': counters['remaining_trials'], 'new_trials': int('settle_trial' in seen),
            'evidence_sufficient': trial['evidence_sufficient'], 'strategy_scientific_pass': False}


def verify_workflow_trace(case, result, events, contract):
    """Verify recorded observations, not a fresh execution or sampled transcript."""
    from quant_rsi.harness.agent_workflow import digest, parse_action, public_context, PACK
    verify_events(events)
    run_id = result['run_id']
    by_id = {e['event_id']: e for e in events}
    start = by_id['workflow-start:' + run_id]['payload']
    if (start['case_hash'] != digest(case) or start['fixture_hash'] != digest(case['fixture'])
            or start['policy_hash'] != digest(contract)
            or start['freeze_sha256'] != sha256((PACK / 'freeze.json').read_bytes()).hexdigest()):
        raise ValueError('FROZEN_INPUT_OR_BUDGET_CHANGED')
    run = by_id['run:' + run_id]['payload']
    condition = BenchmarkCondition.from_dict(by_id['condition:' + run['condition_hash']]['payload'])
    if condition.task.to_dict() != case['ledger_task'] or start['budget_limits'] != case['ledger_task']['budget_limits']:
        raise ValueError('LEDGER_CONDITION_CHANGED')
    history, observations, trial_states = [], [], {}
    requests = [e for e in events if e['kind'] == 'WORKFLOW_AGENT_REQUEST' and e['payload']['run_id'] == run_id]
    for step, event in enumerate(requests, 1):
        request = event['payload']
        expected = public_context(case, contract, observations, history)
        worker = WorkerRequest.from_dict(request['request'])
        if (request['step'] != step or request['context'] != expected or worker.prompt_hash != digest(expected)
                or dict(worker.input_hashes) != {'context': digest(expected), 'fixture': digest(case['fixture']), 'case': digest(case)}
                or worker.policy_hash != digest(contract) or worker.tools != tuple(case['tools'])
                or worker.run_id != run_id or worker.model_id != run['agent_model']
                or worker.provider != run['provider'] or worker.actor_id != 'ACT-' + run_id
                or worker.context_id != 'CTX-' + run_id or worker.model_version != 'workflow-v01'):
            raise ValueError('WORKER_REQUEST_OR_CONTEXT_CHANGED')
        attempt = request['attempt_id']
        reserve, settle = by_id['attempt:' + attempt], by_id['settle:' + attempt]
        action_event = by_id['workflow-action:' + attempt]
        if not reserve['sequence'] < event['sequence'] < action_event['sequence'] < settle['sequence']:
            raise ValueError('STEP_RESERVE_EXECUTE_SETTLE_ORDER')
        action = action_event['payload']['action']
        try:
            parsed = parse_action(action_event['payload']['raw'])
        except (ValueError, TypeError):
            parsed = None
        if action != parsed and action_event['payload']['error'] != 'STEP_RESOURCE_BREACH':
            raise ValueError('ACTION_PARSE_CHANGED')
        history.append(action)
        tool_id = f'TOOL-{run_id}-{step}'
        observation_event = by_id.get('workflow-observation:' + tool_id)
        if not observation_event:
            continue
        if not action or action['action'] != 'TOOL_CALL':
            raise ValueError('MODEL_SELF_REPORTED_TOOL_RESULT')
        validate_call(action['tool'], action['arguments'], case['tools'])
        observation = observation_event['payload']
        if (observation['tool'] != action['tool'] or observation['arguments'] != action['arguments']
                or observation['observation_id'] != f'OBS-{run_id}-{step}' or observation['step'] != step):
            raise ValueError('TOOL_ACTION_RESULT_MISMATCH')
        reserved, settled = by_id['attempt:' + tool_id], by_id['settle:' + tool_id]
        if not action_event['sequence'] < reserved['sequence'] < observation_event['sequence'] < settled['sequence']:
            raise ValueError('TOOL_RESERVE_EXECUTE_SETTLE_ORDER')
        if observation['ok']:
            expected_result = frozen_observation(case, observation, observations,
                                                  events[:observation_event['sequence'] - 1], run_id)
            if observation['result'] != expected_result:
                raise ValueError('FROZEN_OBSERVATION_CHANGED')
            if settled['payload']['artifact_hashes'] != {'observation': digest(observation)}:
                raise ValueError('OBSERVATION_HASH_CHANGED')
            if observation['tool'] == 'reserve_trial':
                trial = observation['result']['trial_ref']
                reserved_trial = by_id['attempt:' + trial]
                if (trial in trial_states or reserved_trial['payload']['envelope']['candidate_trials'] != 1
                        or not reserved['sequence'] < reserved_trial['sequence'] < observation_event['sequence']):
                    raise ValueError('TRIAL_RESERVATION_STATE_INVALID')
                trial_states[trial] = 'RESERVED'
            elif observation['tool'] == 'run_synthetic_trial':
                trial = observation['arguments']['trial_ref']
                execution = by_id['trial-result:' + trial]
                if (trial_states.get(trial) != 'RESERVED' or execution['payload'] != observation['result']
                        or not reserved['sequence'] < execution['sequence'] < observation_event['sequence']):
                    raise ValueError('TRIAL_EXECUTION_STATE_INVALID')
                trial_states[trial] = 'EXECUTED'
            elif observation['tool'] == 'settle_trial':
                trial = observation['arguments']['trial_ref']
                settlement = by_id['settle:' + trial]
                if (trial_states.get(trial) != 'EXECUTED'
                        or not reserved['sequence'] < settlement['sequence'] < observation_event['sequence']):
                    raise ValueError('TRIAL_SETTLEMENT_STATE_INVALID')
                trial_states[trial] = 'SETTLED'
        elif settled['payload']['status'] != 'FAILED' or not observation['error']:
            raise ValueError('TOOL_FAILURE_DISGUISED')
        observations.append(observation)
    usage, blocked = _usage(events, run['budget_root_run_id'])
    if (result['usage']['usage'] != usage or result['usage']['blocked'] != blocked
            or result['steps'] != len(history) or result['tool_calls'] != len(observations)):
        raise ValueError('CUMULATIVE_BUDGET_OR_EXECUTION_COUNTS_CHANGED')
    if result['final'] is not None and (not history or result['final'] != history[-1]):
        raise ValueError('FINAL_NOT_AGENT_ACTION')
    if result['status'] == 'COMPLETED' and (not result['final'] or
            any(state != 'SETTLED' for state in trial_states.values())):
        raise ValueError('FINAL_STATE_INVALID')
    return observations


def frozen_observation(case, observation, prior, events, run_id):
    """Pure checker for saved observations; never invokes FixtureTools.execute."""
    tool, args = observation['tool'], observation['arguments']
    if tool == 'read_fixture':
        if args['fixture_id'] != 'response':
            raise ValueError('UNKNOWN_FIXTURE')
        return case['fixture']
    if tool in ('inspect_response', 'validate_rows'):
        raw = next(o['result'] for o in prior if o['observation_id'] == args['response_ref']
                   and o['tool'] == 'read_fixture' and o['ok'])
        return (row_check(raw, case['row_policy']) if tool == 'validate_rows' else {
            'declared_count': raw['count'], 'items_len': len(raw['items']),
            'metadata_consistent': raw['count'] == len(raw['items'])})
    if tool == 'list_vintages':
        return {'vintages': [vintage_metadata(row) for row in case['fixture']]}
    if tool in ('read_vintage', 'check_asof_eligibility'):
        task = BenchmarkCondition.from_dict({'task': case['ledger_task']}).task
        view = PITView(task, DataSpec.from_dict(case['data_spec']), SnapshotManifest.from_dict(case['snapshot']),
                       lambda ref: canonical_bytes(case['fixture']))
        at = case['initial']['decision_asof']
        visible = {r.value['vintage_id'] for r in view.at(at)}
        rows = {r['value']['vintage_id']: r for r in case['fixture']}
        checks = []
        ids = [args['vintage_id']] if tool == 'read_vintage' else args['vintage_ids']
        for v in ids:
            meta = vintage_metadata(rows[v])
            reason = ('AVAILABLE_AFTER_DECISION' if instant(meta['available_at']) > instant(at)
                      else 'NOT_EFFECTIVE_OR_SUPERSEDED' if v not in visible else None)
            checks.append(dict(meta, decision_asof=at, eligible=v in visible, rejection_reason=reason))
        return {'checks': checks} if tool == 'check_asof_eligibility' else dict(
            checks[0], value=rows[ids[0]]['value']['estimate'] if checks[0]['eligible'] else None)
    usage, _ = _usage(events, run_id)
    counters = {'used_trials': usage['candidate_trials'],
                'trial_limit': case['ledger_task']['budget_limits']['candidate_trials'],
                'remaining_trials': case['ledger_task']['budget_limits']['candidate_trials'] - usage['candidate_trials'],
                'synthetic_only': True}
    if tool == 'inspect_budget':
        return counters
    if tool == 'reserve_trial':
        attempt = next(e['payload']['attempt_id'] for e in reversed(events)
                       if e['kind'] == 'ATTEMPT_STARTED' and e['payload']['benchmark_run_id'] == run_id
                       and e['payload']['scientific_variant_id'] is not None)
        return {'trial_ref': attempt, 'state': 'RESERVED', **counters}
    if tool == 'run_synthetic_trial':
        return {'trial_ref': args['trial_ref'], **synthetic_trial(case['fixture'])}
    if tool == 'settle_trial':
        settled = next(e['payload'] for e in events if e['event_id'] == 'settle:' + args['trial_ref'])
        if settled['status'] != 'FAILED':
            raise ValueError('INVALID_TRIAL_SETTLEMENT')
        return {'trial_ref': args['trial_ref'], 'state': 'SETTLED', **counters}
    raise ValueError('UNSUPPORTED_REPLAY_TOOL')


def evaluate_workflow(case, result, events):
    from quant_rsi.harness.agent_workflow import read, PACK
    mine = [e for e in events if e['payload'].get('run_id') == result['run_id']]
    observations = [e['payload'] for e in mine if e['kind'] == 'WORKFLOW_TOOL_RESULT']
    trace_ok = True
    try:
        verify_workflow_trace(case, result, events, read(PACK / 'action_contract.json'))
    except (ValueError, KeyError, TypeError, StopIteration):
        trace_ok = False
    final = result['final']
    conclusion_ok, normalized, issues = conclusion_check(case, final['conclusion']) if final else (None, {}, ['NO_FINAL'])
    support = observed_support(case, observations)
    successful = {o['observation_id']: o for o in observations if o['ok']}
    cited = set(final['evidence']) if final else set()
    required_evidence = {'WFA-01': {'inspect_response', 'validate_rows'},
                         'WFA-02': {'check_asof_eligibility', 'read_vintage'},
                         'WFA-03': {'settle_trial', 'run_synthetic_trial'} if case.get('prior_trials') == 1 else {'inspect_budget'}}[case['workflow_id']]
    evidence_ok = cited <= set(successful) and required_evidence <= {
        successful[ref]['tool'] for ref in cited if ref in successful}
    # The cited eligibility observations must cover every listed version.
    if evidence_ok and case['workflow_id'] == 'WFA-02':
        checked = {c['vintage_id'] for ref in cited if successful[ref]['tool'] == 'check_asof_eligibility'
                   for c in successful[ref]['result']['checks']}
        listed = {v['vintage_id'] for o in observations if o['tool'] == 'list_vintages' and o['ok']
                  for v in o['result']['vintages']}
        evidence_ok = checked == listed
    used_ok = bool(final and support is not None and evidence_ok and
        all(same(normalized.get(f), v, case['conclusion_contract'][f]['type']) for f, v in support.items()))
    denied = any(e['kind'] == 'ATTEMPT_DENIED' and e['payload']['benchmark_run_id'] == result['run_id'] for e in events)
    compliant = (not denied and not result['usage']['blocked'] and result['steps'] <= 8
                 and result['tool_calls'] <= 6 and all(result['usage']['usage'][k] <= v
                     for k, v in case['ledger_task']['budget_limits'].items()))
    selection_ok = result['error'] not in ('TOOL_CONTRACT_REJECTED', 'ACTION_CONTRACT_REJECTED')
    transitions = result['status'] == 'COMPLETED' and all(o['ok'] for o in observations)
    vector = {'FINAL_DECISION_CORRECT': conclusion_ok, 'TOOL_SELECTION_VALID': selection_ok,
              'TOOL_RESULT_USED_CORRECTLY': used_ok if final else None,
              'STATE_TRANSITION_VALID': transitions, 'BUDGET_COMPLIANT': compliant,
              'EVIDENCE_TRACE_COMPLETE': trace_ok}
    return {'vector': vector, 'workflow_pass': all(v is True for v in vector.values()),
            'hard_gates': {'execution_completed': result['status'] == 'COMPLETED',
                           'actual_required_tools': set(case['reference']['required_tools']) <= {o['tool'] for o in observations if o['ok']},
                           'trace_and_budget': trace_ok and compliant},
            'failed_predicates': issues,
            'failure_class': 'EXECUTION_FAILURE_NOT_RESEARCH_CONCLUSION' if result['status'] != 'COMPLETED'
                             else None if conclusion_ok else 'WRONG_RESEARCH_CONCLUSION',
            'single_total_score': None, 'strategy_scientific_pass': False,
            'identity_independence': False, 'D08_achieved': False}
