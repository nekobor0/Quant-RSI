import copy

import pytest

from quant_rsi.harness.supplement_tasks import TASKS, fact_predicates, static_answer
from quant_rsi.harness.supplement_tools import execute, UnknownToolUsage
from quant_rsi.harness.supplement import run_case, suite, context_for
from quant_rsi.harness.supplement_oracle import replay
from quant_rsi.harness.agent_workflow import digest
from quant_rsi.harness.workflow_chat import messages
from quant_rsi.ledger.store import TraceStore


def run_tools(case):
    observations = []
    for step, tool in enumerate(case['stages']):
        if case['task_id'] == 'Q-AT-02' and observations:
            eligible = observations[0]['result']['eligible']
            if (tool == 'inspect_backup' and eligible) or (tool == 'read_eligible_version' and not eligible):
                continue
        result = execute(case, tool, {'observations': [o['observation_id'] for o in observations]}, observations)
        observations.append(dict(observation_id=f'OBS-{step}', tool=tool, result=result, ok=True))
    return observations


@pytest.mark.parametrize('case_id', ['Q-RD-01', 'Q-RD-02', 'Q-RD-03', 'Q-RD-04'])
def test_rd_references_and_wrong_answer(case_id):
    case = TASKS[case_id]
    public = {k: copy.deepcopy(case[k]) for k in ('task_id', 'input')}
    answer = static_answer(public)
    assert all(fact_predicates(case, answer).values())
    answer[case['wrong_field']] = 'CONTROLLED_WRONG'
    assert not all(fact_predicates(case, answer).values())


def test_rd_equivalent_design_and_purging():
    case = TASKS['Q-RD-03']
    answer = copy.deepcopy(case['reference'])
    answer['control'] = 'industry_size_residualization'
    assert all(fact_predicates(case, answer).values())
    answer['control'] = 'industry_demean_only'
    assert not all(fact_predicates(case, answer).values())
    assert TASKS['Q-RD-02']['reference']['purged_sample_ids'] == ['L2', 'L3']


@pytest.mark.parametrize('case_id', ['Q-DA-01', 'Q-DA-02', 'Q-DA-03', 'Q-DA-04'])
def test_da_actual_computations(case_id):
    case = TASKS[case_id]
    assert all(fact_predicates(case, run_tools(case)[-1]['result']).values())
    with pytest.raises(ValueError):
        execute(case, case['stages'][-1], {'observations': []}, [])


def test_da_asof_counterfactual():
    case = copy.deepcopy(TASKS['Q-DA-04'])
    case['fixture']['versions'].append(dict(id='v0', published='08:00', available='09:00', value=8))
    assert run_tools(case)[-1]['result']['values'] == [8, 10, 10]
    case['fixture']['versions'].append(dict(id='future', published='13:00', available='13:00', value=999))
    assert run_tools(case)[-1]['result']['values'] == [8, 10, 10]


@pytest.mark.parametrize('case_id', ['Q-FA-01', 'Q-FA-02', 'Q-FA-03', 'Q-FA-04'])
def test_fa_computations(case_id):
    case = TASKS[case_id]
    assert all(fact_predicates(case, run_tools(case)[-1]['result']).values())


def test_factor_variants():
    case = copy.deepcopy(TASKS['Q-FA-01'])
    case['fixture']['factors'] = [5, 5]
    with pytest.raises(ValueError, match='ZERO_FACTOR_VARIANCE'):
        run_tools(case)
    case = copy.deepcopy(TASKS['Q-FA-02'])
    case['fixture']['industries'][0] = None
    missing = run_tools(case)[-1]['result']
    assert missing['status'] == 'INSUFFICIENT_EVIDENCE'
    assert missing['industry_means'] is None
    case = copy.deepcopy(TASKS['Q-FA-04'])
    case['fixture']['new_scores'] = [3, 3, 3]
    assert run_tools(case)[-1]['result']['new_weights'] == [.5, .5, 0]


@pytest.mark.parametrize('case_id', ['Q-ST-01', 'Q-ST-02', 'Q-ST-03', 'Q-ST-04'])
def test_statistics_references(case_id):
    case = TASKS[case_id]
    answer = static_answer(case)
    assert all(fact_predicates(case, answer).values())
    answer[case['wrong_field']] = 'WRONG'
    assert not all(fact_predicates(case, answer).values())


def test_statistics_input_changes():
    case = copy.deepcopy(TASKS['Q-ST-01'])
    case['input']['hac_se'] = .01
    assert static_answer(case)['reject_zero'] is True
    case = copy.deepcopy(TASKS['Q-ST-03'])
    case['input']['p_values'] = [.9, .8, .7, .6]
    assert static_answer(case)['retained'] == []


@pytest.mark.parametrize('case_id', ['Q-EC-01', 'Q-EC-02', 'Q-EC-03', 'Q-EC-04'])
def test_execution_economics(case_id):
    case = TASKS[case_id]
    assert all(fact_predicates(case, run_tools(case)[-1]['result']).values())


@pytest.mark.parametrize('case_id', ['Q-PT-01', 'Q-PT-02', 'Q-PT-03', 'Q-PT-04'])
def test_portfolio_constraints(case_id):
    case = TASKS[case_id]
    assert all(fact_predicates(case, run_tools(case)[-1]['result']).values())


def test_portfolio_and_order_changes():
    case = copy.deepcopy(TASKS['Q-EC-03'])
    case['fixture']['market']['A']['volume'] = 100
    assert run_tools(case)[-1]['result']['fills']['A'] == 20
    case = copy.deepcopy(TASKS['Q-PT-01'])
    case['input']['weight_cap'] = .8
    assert run_tools(case)[-1]['result']['weights'] == pytest.approx([.8, .2], abs=1e-8)
    case = copy.deepcopy(TASKS['Q-PT-03'])
    case['fixture']['wealth'] = [100, 120, 100]
    assert run_tools(case)[-1]['result']['allow_new_risk'] is True


@pytest.mark.parametrize('case_id', ['Q-AT-01', 'Q-AT-02', 'Q-AT-02:future_only',
                                    'Q-AT-04', 'Q-AT-04:input_changed'])
def test_agent_process_operations(case_id):
    case = TASKS[case_id]
    assert all(fact_predicates(case, run_tools(case)[-1]['result']).values())


def test_unknown_usage_is_not_a_research_result():
    with pytest.raises(UnknownToolUsage):
        run_tools(TASKS['Q-AT-03'])


def test_ordered_arrays_and_unordered_declared_sets():
    case = TASKS['Q-ST-03']
    answer = copy.deepcopy(case['reference'])
    answer['retained'].reverse()
    assert all(fact_predicates(case, answer).values())
    answer['rank_ids'].reverse()
    assert not fact_predicates(case, answer)['rank_ids']


def run_chat(tmp_path, key, profile='correct', fault=None):
    store = TraceStore(tmp_path / (key.replace(':', '-') + profile + (fault or '') + '.sqlite'))
    result = run_case(store, key, 'TEST-' + profile + (fault or ''), profile=profile, fault=fault)
    replay(store.read(), result, expected_anchor=store.checkpoint())
    return result, store


@pytest.mark.parametrize('key', ['Q-RD-03', 'Q-DA-01', 'Q-FA-01', 'Q-ST-03', 'Q-EC-03',
    'Q-PT-01', 'Q-AT-01', 'Q-AT-02', 'Q-AT-02:future_only', 'Q-AT-03', 'Q-AT-04:input_changed'])
def test_multiround_completion_and_differentiated_scores(tmp_path, key):
    good, _ = run_chat(tmp_path, key)
    bad, _ = run_chat(tmp_path, key, 'over_budget' if key == 'Q-AT-03' else 'wrong_final')
    assert good['evaluation']['task_pass'], good
    assert not bad['evaluation']['task_pass'], bad
    assert bad['evaluation']['vector']['BUDGET_COMPLIANT'] is (key != 'Q-AT-03')
    assert bad['evaluation']['vector']['EVIDENCE_TRACE_COMPLETE'] is True
    assert good['scientific']['candidate_variant_count'] == 0
    assert good['usage']['usage']['candidate_trials'] == 0


@pytest.mark.parametrize('profile', ['illegal_tool', 'wrong_arguments', 'early_final', 'wrong_reference', 'redundant'])
def test_process_error_vectors(tmp_path, profile):
    result, _ = run_chat(tmp_path, 'Q-DA-01', profile)
    vector = result['evaluation']['vector']
    if profile == 'redundant':
        assert result['evaluation']['task_pass']
        assert 'REDUNDANT_LEGAL_TOOL_CALL' in result['evaluation']['diagnostics']
    else:
        assert not result['evaluation']['task_pass']
        assert any(v is True for v in vector.values())
    if profile in ('illegal_tool', 'wrong_arguments'):
        assert vector['TOOL_SELECTION_VALID'] is False
    if profile == 'wrong_reference':
        assert vector['FINAL_DECISION_CORRECT'] is True
        assert vector['TOOL_RESULT_USED_CORRECTLY'] is False


@pytest.mark.parametrize('fault', ['http', 'timeout', 'business', 'empty', 'truncated', 'json',
                                  'action', 'usage_missing', 'usage_breach', 'model_mismatch'])
def test_provider_failure_classification_and_no_retry(tmp_path, fault):
    result, _ = run_chat(tmp_path, 'Q-DA-01', fault=fault)
    assert not result['evaluation']['task_pass']
    assert result['transport_calls'] == 1
    assert result['tool_calls'] == 0
    assert result['evaluation']['vector']['FINAL_DECISION_CORRECT'] is None
    if fault not in ('json', 'action', 'usage_breach'):
        assert result['evaluation']['failure_class'] == 'PROVIDER_FAILURE_NOT_RESEARCH'
    if fault in ('http', 'timeout', 'business', 'usage_missing'):
        assert result['usage']['blocked']
        assert result['usage']['usage']['input_tokens'] == 32768


def test_native_usage_and_budget_rename_denial(tmp_path):
    result, store = run_chat(tmp_path, 'Q-DA-01', fault='native_reasoning')
    assert result['evaluation']['task_pass']
    assert result['usage']['usage']['output_tokens'] == result['steps'] * 160
    with pytest.raises(ValueError, match='BUDGET_ROOT_ALREADY_CLAIMED'):
        run_case(store, 'Q-DA-01', 'RENAMED', fault='native_reasoning')
    assert store.read()[-1]['kind'] == 'SUPPLEMENT_RENAME_DENIED'


def test_counterfactual_initial_prompt_and_next_action(tmp_path):
    _, cases = suite()
    assert messages(context_for(cases['Q-AT-02'], [], [])) == messages(context_for(cases['Q-AT-02:future_only'], [], []))
    a, store_a = run_chat(tmp_path, 'Q-AT-02')
    b, store_b = run_chat(tmp_path, 'Q-AT-02:future_only')
    assert a['final']['conclusion']['value'] == 10
    assert b['final']['conclusion']['verdict'] == 'REFUSE'
    actions_a = [e['payload']['action'] for e in store_a.read() if e['kind'] == 'SUPPLEMENT_CHAT_ACTION']
    actions_b = [e['payload']['action'] for e in store_b.read() if e['kind'] == 'SUPPLEMENT_CHAT_ACTION']
    assert actions_a[1]['tool'] == 'read_eligible_version'
    assert actions_b[1]['tool'] == 'inspect_backup'
    contexts_a = [e['payload']['context'] for e in store_a.read() if e['kind'] == 'SUPPLEMENT_CHAT_REQUEST']
    contexts_b = [e['payload']['context'] for e in store_b.read() if e['kind'] == 'SUPPLEMENT_CHAT_REQUEST']
    assert digest(contexts_a[0]) == digest(contexts_b[0])
    assert digest(contexts_a[1]) != digest(contexts_b[1])
    assert len({digest(c) for c in contexts_a}) == len(contexts_a)


def test_future_claim_and_unknown_usage_stop(tmp_path):
    result, _ = run_chat(tmp_path, 'Q-AT-02:future_only', 'future_claim')
    assert 'FUTURE_VINTAGE_CLAIM' in result['evaluation']['diagnostics']
    assert result['evaluation']['vector']['STATE_TRANSITION_VALID'] is False
    stopped, store = run_chat(tmp_path, 'Q-AT-03')
    assert stopped['status'] == 'EXECUTION_INCOMPLETE'
    assert stopped['transport_calls'] == stopped['tool_calls'] == 1
    assert stopped['evaluation']['vector']['FINAL_DECISION_CORRECT'] is None
    assert stopped['supervisor']['actual_usage'] is None
    settlement = next(e['payload'] for e in store.read() if e['event_id'].startswith('settle:TOOL-'))
    assert settlement['usage_state'] == 'UNKNOWN'
    assert stopped['usage']['usage']['wall_milliseconds'] >= 1000


def test_replay_is_read_only_and_detects_tamper(tmp_path, monkeypatch):
    result, store = run_chat(tmp_path, 'Q-DA-01')
    events, anchor = store.read(), store.checkpoint()
    def forbidden(*args, **kwargs):
        raise AssertionError('REPLAY_EXECUTED_PROVIDER_OR_TOOL')
    monkeypatch.setattr('quant_rsi.harness.supplement.execute', forbidden)
    monkeypatch.setattr('quant_rsi.harness.supplement_chat.SupplementChatAdapter.step', forbidden)
    assert replay(events, result, expected_anchor=anchor)['tool_reexecutions'] == 0
    changed = copy.deepcopy(events)
    changed[-1]['payload']['task_pass'] = False
    with pytest.raises(ValueError):
        replay(changed, result, expected_anchor=anchor)
    changed_result = copy.deepcopy(result)
    changed_result['usage']['usage']['input_tokens'] = 0
    with pytest.raises(ValueError):
        replay(events, changed_result, expected_anchor=anchor)
    changed_result = copy.deepcopy(result)
    changed_result['evaluation']['task_pass'] = False
    with pytest.raises(ValueError):
        replay(events, changed_result, expected_anchor=anchor)


def test_prompt_contains_schema_not_private_references():
    _, cases = suite()
    for key, case in cases.items():
        context = context_for(case, [], [])
        assert 'reference' not in context
        assert 'fixture' not in context
        assert 'ledger_task' not in context
        assert context['allowed_tools'] == case['stages'] + case.get('optional_tools', [])
        assert 'fields' in context['conclusion_contract']


def test_legal_suboptimal_tool_and_double_budget(tmp_path):
    result, optional_store = run_chat(tmp_path, 'Q-AT-02', 'suboptimal')
    assert result['evaluation']['task_pass']
    assert 'LEGAL_OPTIONAL_AUDIT_SUBOPTIMAL_COST' in result['evaluation']['diagnostics']
    for event in optional_store.read():
        if event['kind'] == 'SUPPLEMENT_CHAT_REQUEST':
            assert event['payload']['request']['tools'] == event['payload']['context']['allowed_tools']
    repeated, store = run_chat(tmp_path, 'Q-DA-01', 'repeat_tool')
    assert repeated['tool_calls'] == 6
    assert repeated['status'] == 'BUDGET_EXHAUSTED'
    assert any(e['kind'] == 'ATTEMPT_DENIED' for e in store.read())
    assert repeated['evaluation']['vector']['BUDGET_COMPLIANT'] is False


def test_tool_failure_then_false_success(tmp_path):
    result, _ = run_chat(tmp_path, 'Q-DA-01', 'tool_failure_claim', 'tool_failure')
    assert result['transport_calls'] == 2
    assert result['tool_calls'] == 1
    assert not result['evaluation']['task_pass']
    assert result['evaluation']['vector']['TOOL_SELECTION_VALID'] is True
    assert result['evaluation']['vector']['BUDGET_COMPLIANT'] is True
    assert 'FINAL_AFTER_UNRESOLVED_TOOL_FAILURE' in result['evaluation']['diagnostics']
    assert result['evaluation']['failure_class'] == 'EXECUTION_FAILURE_NOT_RESEARCH'


def test_interruption_retains_reservation(tmp_path, monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr('quant_rsi.harness.supplement_chat.SupplementChatAdapter.step', interrupted)
    result, store = run_chat(tmp_path, 'Q-DA-01')
    assert result['error'] == 'WORKFLOW_INTERRUPTED'
    assert result['usage']['blocked']
    assert result['usage']['usage']['output_tokens'] == 2048
    assert any(e['kind'] == 'ATTEMPT_SETTLED' and e['payload']['actual_resources'] is None for e in store.read())


def test_adapter_does_not_resolve_environment_credentials(tmp_path, monkeypatch):
    import os
    from quant_rsi.harness.supplement_chat import SupplementChatAdapter
    def forbidden(*args, **kwargs):
        raise AssertionError('CREDENTIAL_OR_REAL_TRANSPORT_ACCESS')
    monkeypatch.setattr(os.environ, 'get', forbidden)
    with pytest.raises(ValueError):
        SupplementChatAdapter(object())
    result, _ = run_chat(tmp_path, 'Q-DA-01')
    assert result['evaluation']['task_pass']


def test_published_vocabulary_and_observation_schemas():
    _, cases = suite()
    for key, case in cases.items():
        public = context_for(case, [], [])
        assert all('output_schema' in spec for spec in public['tool_contracts'].values())
    assert 'INCONCLUSIVE' in context_for(cases['Q-ST-02'], [], [])['conclusion_contract']['categorical_vocabulary']['terminal']
    assert messages(context_for(cases['Q-AT-04'], [], [])) == messages(context_for(cases['Q-AT-04:input_changed'], [], []))


def test_action_aliases_and_equivalent_float_output(tmp_path, monkeypatch):
    from quant_rsi.harness import supplement_chat
    original = supplement_chat.decide
    def aliases(context, profile):
        action = original(context, profile)
        action['type'] = action.pop('action')
        if action['type'] == 'TOOL_CALL':
            action['args'] = action.pop('arguments')
        else:
            action['result'] = action.pop('conclusion')
            if 'variance' in action['result']:
                action['result']['variance'] += 5e-9
        return action
    monkeypatch.setattr(supplement_chat, 'decide', aliases)
    result, _ = run_chat(tmp_path, 'Q-PT-01')
    assert result['evaluation']['task_pass']


def test_wrong_derived_fact_stays_failed():
    case = TASKS['Q-PT-01']
    answer = copy.deepcopy(case['reference'])
    answer['variance'] += 1e-5
    assert fact_predicates(case, answer)['variance'] is False
    answer = copy.deepcopy(case['reference'])
    answer['weights'] = [.8, .2]
    assert fact_predicates(case, answer)['weights'] is False


def test_integer_counts_do_not_use_float_tolerance():
    case = TASKS['Q-DA-01']
    answer = copy.deepcopy(case['reference'])
    answer['final_rows'] += 1e-9
    assert fact_predicates(case, answer)['final_rows'] is False
    answer['final_rows'] = 2.0
    assert fact_predicates(case, answer)['final_rows'] is True
    answer['final_rows'] = True
    assert fact_predicates(case, answer)['final_rows'] is False
    case = TASKS['Q-EC-03']
    answer = copy.deepcopy(case['reference'])
    answer['fills']['A'] += 1e-9
    assert fact_predicates(case, answer)['fills'] is False


def test_minimal_sufficient_citations_and_optional_audit(tmp_path, monkeypatch):
    from quant_rsi.harness import supplement_chat
    original = supplement_chat.decide
    def minimal(context, profile):
        action = original(context, profile)
        if action['action'] == 'FINAL' and context['task']['kind'] == 'WORKFLOW':
            observations = context['observations']
            required = set(context['citation_policy']['required_direct_citation_tools'])
            action['evidence'] = [o['observation_id'] for o in observations
                                  if o['tool'] in required or o is observations[-1]]
        return action
    monkeypatch.setattr(supplement_chat, 'decide', minimal)
    result, _ = run_chat(tmp_path, 'Q-AT-02', 'suboptimal')
    assert result['evaluation']['task_pass']
    assert len(result['final']['evidence']) == 1
    result, _ = run_chat(tmp_path, 'Q-DA-01')
    assert result['evaluation']['task_pass']
    assert len(result['final']['evidence']) == 3


def test_unknown_usage_not_budget_misconduct(tmp_path):
    result, _ = run_chat(tmp_path, 'Q-DA-01', fault='usage_missing')
    assert result['evaluation']['vector']['BUDGET_COMPLIANT'] is True
    assert 'UNKNOWN_USAGE_STOPPED_RESERVATION_RETAINED' in result['evaluation']['diagnostics']
    assert result['evaluation']['failed_predicates'] == ['NO_ASSESSABLE_FINAL']
    assert all(v is None for v in result['evaluation']['fact_predicates'].values())
