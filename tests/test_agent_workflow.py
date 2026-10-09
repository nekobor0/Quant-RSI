"""Only scripted providers and frozen fixture tools; all network is forbidden."""
import copy
import json
import urllib.request

import pytest

from quant_rsi.harness import agent_workflow as wf
from quant_rsi.harness import workflow_tools as tools
from quant_rsi.harness.workflow_agents import ScriptedAgent, ChatWorkflowAdapter
from quant_rsi.harness.providers import ChatProvider, ProviderReply
from quant_rsi.ledger.store import TraceStore

CASES = wf.read(wf.PACK / 'cases.json')


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('network forbidden'))


def run(tmp_path, case='WFA-01-anomaly', agent=None, name='RUN-test'):
    store = TraceStore(tmp_path / 'trace.sqlite')
    result = wf.run_workflow(store, case, agent or ScriptedAgent(), name)
    wf.save(tmp_path / 'result.json', result)
    return store, result


class ProbeAgent:
    provider_id = 'scripted-offline'
    model_id = 'scripted-probe-v01'

    def __init__(self, decide):
        self.decide = decide

    def step(self, request, context):
        action = self.decide(context)
        return ProviderReply(True, action if isinstance(action, str) else json.dumps(action),
                             None, None, 0, 0, 0, 1, finish_reason='stop')


def call(tool, **arguments):
    return {'action': 'TOOL_CALL', 'tool': tool, 'arguments': arguments}


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('wrong', [False, True])
def test_complete_observation_driven_workflows_and_replay(tmp_path, monkeypatch, case, wrong):
    store, result = run(tmp_path, case, ScriptedAgent(wrong))
    assert result['status'] == 'COMPLETED'
    assert result['evaluation']['workflow_pass'] is not wrong
    assert result['evaluation']['vector']['FINAL_DECISION_CORRECT'] is not wrong
    assert result['evaluation']['vector']['EVIDENCE_TRACE_COMPLETE']
    assert result['evaluation']['vector']['BUDGET_COMPLIANT']
    assert result['strategy_scientific_pass'] is False
    requests = [e['payload'] for e in store.read() if e['kind'] == 'WORKFLOW_AGENT_REQUEST']
    assert requests[0]['context']['observations'] == []
    assert 'reference' not in requests[0]['context'] and 'fixture' not in requests[0]['context']
    assert requests[1]['context']['observations']  # actual new observation fed into next step
    assert requests[0]['request']['prompt_hash'] != requests[1]['request']['prompt_hash']
    events, anchor = store.read(), store.checkpoint()
    monkeypatch.setattr(tools.FixtureTools, 'execute', lambda *a, **k: pytest.fail('tool re-executed'))
    monkeypatch.setattr(ScriptedAgent, 'step', lambda *a, **k: pytest.fail('Agent called during replay'))
    assert wf.replay(events, result, expected_anchor=anchor)['tool_reexecutions'] == 0
    assert store.read() == events


def test_next_decision_changes_with_previous_observation(tmp_path):
    _, available = run(tmp_path / 'yes', 'WFA-02-available')
    _, unavailable = run(tmp_path / 'no', 'WFA-02-unavailable')
    assert available['final']['conclusion']['selected_vintage'] == 'v1'
    assert unavailable['final']['conclusion']['verdict'] == 'REFUSE'
    _, remaining = run(tmp_path / 'left', 'WFA-03-remaining')
    _, exhausted = run(tmp_path / 'none', 'WFA-03-exhausted')
    assert remaining['tool_calls'] == 4 and exhausted['tool_calls'] == 1
    assert remaining['final']['conclusion']['new_trials'] == 1
    assert exhausted['final']['conclusion']['new_trials'] == 0


@pytest.mark.parametrize('action', [call('shell', command='whoami'),
    call('read_fixture', fixture_id='response', run_id='new-root'),
    call('read_fixture', path='../cases.json'),
    call('check_asof_eligibility', vintage_ids=['v1']),
    {'action': 'TOOL_CALL', 'tool': 'read_fixture', 'arguments': {'fixture_id': 'response'}, 'result': 'success'},
    {'action': 'FINAL', 'conclusion': {}, 'evidence': [], 'tools_succeeded': True},
    '{"action":"FINAL","action":"TOOL_CALL"}',
    {'type': 'FINAL', 'action': 'TOOL_CALL', 'arguments': {}}])
def test_invalid_actions_cannot_bypass_tool_layer(tmp_path, action):
    store, result = run(tmp_path, agent=ProbeAgent(lambda c: action))
    assert result['status'] == 'INVALID_ACTION' and result['tool_calls'] == 0
    assert not result['evaluation']['workflow_pass']
    assert result['evaluation']['failure_class'] == 'EXECUTION_FAILURE_NOT_RESEARCH_CONCLUSION'
    assert any(e['kind'] == 'WORKFLOW_AGENT_ACTION' for e in store.read())


def test_tool_failure_is_preserved_not_success_observation(tmp_path):
    store, result = run(tmp_path, agent=ProbeAgent(lambda c: call('inspect_response', response_ref='invented')))
    assert result['status'] == 'TOOL_ERROR' and result['tool_calls'] == 1
    observation = next(e['payload'] for e in store.read() if e['kind'] == 'WORKFLOW_TOOL_RESULT')
    assert not observation['ok'] and observation['result'] is None and observation['error']
    assert next(e['payload'] for e in store.read() if e['event_id'] == 'settle:TOOL-RUN-test-1')['status'] == 'FAILED'
    assert wf.replay(store.read(), result, expected_anchor=store.checkpoint())['status'].endswith('MATCH')


def test_tool_budget_is_cumulative_and_denial_precedes_execution(tmp_path):
    store, result = run(tmp_path, agent=ProbeAgent(lambda c: call('read_fixture', fixture_id='response')))
    assert result['status'] == 'BUDGET_EXHAUSTED'
    assert result['steps'] == 7 and result['tool_calls'] == 6
    assert result['usage']['usage']['validation_queries'] == 6
    assert result['usage']['usage']['attempts'] == 13
    assert len([e for e in store.read() if e['kind'] == 'WORKFLOW_TOOL_RESULT']) == 6
    assert any(e['kind'] == 'ATTEMPT_DENIED' for e in store.read())


def test_max_steps_terminates_without_ninth_agent_call(tmp_path, monkeypatch):
    # A stricter two-step fixture exercises this guard before the six-tool cap.
    # The production eight-step freeze and canonical tool accounting stay intact.
    original = wf.suite
    def stricter():
        freeze, cases, contract = original()
        return dict(freeze, max_steps=2), cases, contract
    monkeypatch.setattr(wf, 'suite', stricter)
    _, result = run(tmp_path, agent=ProbeAgent(lambda c: call('read_fixture', fixture_id='response')))
    assert result['status'] == 'MAX_STEPS_EXCEEDED' and result['steps'] == 2 and result['tool_calls'] == 2
    assert not result['evaluation']['workflow_pass']


def test_agent_failure_is_not_wrong_research_answer(tmp_path):
    def fail(context):
        raise RuntimeError('scripted exception')
    store, result = run(tmp_path, agent=ProbeAgent(fail))
    assert result['status'] == 'AGENT_FAILED'
    assert result['evaluation']['vector']['FINAL_DECISION_CORRECT'] is None
    assert result['evaluation']['failure_class'] == 'EXECUTION_FAILURE_NOT_RESEARCH_CONCLUSION'
    assert any(e['kind'] == 'ATTEMPT_SETTLED' for e in store.read())


def test_pit_future_is_denied_and_legal_version_remains_usable(tmp_path):
    store, result = run(tmp_path, 'WFA-02-available')
    observations = [e['payload'] for e in store.read() if e['kind'] == 'WORKFLOW_TOOL_RESULT']
    checks = next(o['result']['checks'] for o in observations if o['tool'] == 'check_asof_eligibility')
    assert {c['vintage_id']: c['eligible'] for c in checks} == {'v1': True, 'v2': False, 'v3': False, 'v4': False}
    assert next(c for c in checks if c['vintage_id'] == 'v2')['published_at'] < CASES['WFA-02-available']['initial']['decision_asof']
    assert result['evaluation']['workflow_pass']
    future = ProbeAgent(lambda c: call('list_vintages') if not c['observations'] else
        call('read_vintage', vintage_id='v2') if len(c['observations']) == 1 else {
            'action': 'FINAL', 'conclusion': CASES['WFA-02-available']['reference']['conclusion'],
            'evidence': [o['observation_id'] for o in c['observations']]})
    other, denied = run(tmp_path / 'future', 'WFA-02-available', future)
    observed = next(e['payload'] for e in other.read() if e['kind'] == 'WORKFLOW_TOOL_RESULT' and e['payload']['tool'] == 'read_vintage')
    assert observed['ok'] and not observed['result']['eligible'] and observed['result']['value'] is None
    assert not denied['evaluation']['workflow_pass']


def test_correct_final_without_real_tools_does_not_pass(tmp_path):
    answer = {'action': 'FINAL', 'conclusion': CASES['WFA-01-anomaly']['reference']['conclusion'], 'evidence': []}
    _, result = run(tmp_path, agent=ProbeAgent(lambda c: answer))
    assert result['evaluation']['vector']['FINAL_DECISION_CORRECT']
    assert not result['evaluation']['vector']['TOOL_RESULT_USED_CORRECTLY']
    assert not result['evaluation']['workflow_pass']


def test_budget_rename_trial_and_task_override_are_rejected(tmp_path):
    store, result = run(tmp_path, 'WFA-03-remaining')
    assert result['usage']['usage']['candidate_trials'] == 2
    assert result['synthetic_trial_accounting']['candidate_variant_count'] == 2
    with pytest.raises(ValueError, match='rename cannot reset'):
        wf.run_workflow(store, 'WFA-03-remaining', ScriptedAgent(), 'RUN-renamed')
    assert any(e['kind'] == 'WORKFLOW_RENAME_DENIED' for e in store.read())
    for params in ({'run_id': 'new'}, {'task_id': 'new'}, {'scientific_variant_id': 'new'}):
        with pytest.raises(ValueError):
            tools.validate_call('reserve_trial', params, CASES['WFA-03-remaining']['tools'])


def test_exhausted_trial_budget_no_trial_execution(tmp_path):
    store, result = run(tmp_path, 'WFA-03-exhausted', ProbeAgent(lambda c: call('reserve_trial')))
    assert result['status'] == 'BUDGET_EXHAUSTED' and result['usage']['usage']['candidate_trials'] == 2
    assert not any(e['kind'] == 'WORKFLOW_TRIAL_RESULT' for e in store.read())


def test_context_mutation_and_fixture_instructions_have_no_authority(tmp_path):
    correct = ScriptedAgent()
    def mutate(context):
        context['limits']['max_steps'] = 1000
        context['allowed_tools'].append('shell')
        return correct.decide(context)
    store, result = run(tmp_path, agent=ProbeAgent(mutate))
    assert result['evaluation']['workflow_pass']
    contexts = [e['payload']['context'] for e in store.read() if e['kind'] == 'WORKFLOW_AGENT_REQUEST']
    assert all(c['limits']['max_steps'] == 8 and 'shell' not in c['allowed_tools'] for c in contexts)
    assert result['final']['conclusion']['effective_rows'] == 1


def test_public_action_and_fact_aliases_are_accepted_without_drift(tmp_path):
    good = ScriptedAgent()
    def alias(context):
        action = good.decide(context)
        action['type'] = action.pop('action')
        if action['type'] == 'TOOL_CALL':
            action['args'] = action.pop('arguments')
        else:
            conclusion = action.pop('conclusion')
            conclusion['valid_rows'] = str(conclusion.pop('effective_rows'))
            action['result'] = conclusion
        return '```json\n' + json.dumps(action) + '\n```'
    _, result = run(tmp_path, agent=ProbeAgent(alias))
    assert result['evaluation']['workflow_pass']


@pytest.mark.parametrize('attack', ['trace', 'input_hash', 'budget', 'final', 'score'])
def test_replay_detects_trace_input_budget_and_final_drift(tmp_path, attack):
    store, result = run(tmp_path)
    events, anchor = copy.deepcopy(store.read()), store.checkpoint()
    altered = copy.deepcopy(result)
    if attack == 'trace':
        events[-1]['payload']['workflow_pass'] = False
    elif attack == 'input_hash':
        event = next(e for e in events if e['kind'] == 'WORKFLOW_AGENT_REQUEST')
        event['payload']['request']['input_hashes']['context'] = 'f' * 64
    elif attack == 'budget':
        altered['usage']['usage']['validation_queries'] = 0
    elif attack == 'final':
        altered['final']['conclusion']['effective_rows'] = 0
    else:
        altered['evaluation']['workflow_pass'] = False
    with pytest.raises(ValueError):
        wf.replay(events, altered, expected_anchor=anchor)


def test_real_chat_seam_is_explicitly_disabled_without_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(ChatProvider, '_resolve_key', lambda p: pytest.fail('credential read'))
    adapter = ChatWorkflowAdapter(ChatProvider('future', 'future-model', 'https://example.invalid', 'UNUSED'))
    with pytest.raises(ValueError, match='prohibits real'):
        wf.run_workflow(TraceStore(tmp_path / 'trace.sqlite'), 'WFA-01-anomaly', adapter, 'RUN-real')
    with pytest.raises(RuntimeError, match='NOT_AUTHORIZED'):
        adapter.step(None, {})


def test_provider_value_error_stays_agent_failed(tmp_path):
    def fail(context):
        raise ValueError('provider implementation error')
    _, result = run(tmp_path, agent=ProbeAgent(fail))
    assert result['status'] == 'AGENT_FAILED' and result['error'] == 'AGENT_PROVIDER_FAILED'


def test_subset_citations_and_incremental_vintage_checks_are_legal(tmp_path):
    good = ScriptedAgent()
    def fewer(context):
        action = good.decide(context)
        if action['action'] == 'FINAL':
            refs = {o['observation_id'] for o in context['observations'] if o['tool'] != 'read_fixture'}
            action['evidence'] = sorted(refs)
        return action
    _, result = run(tmp_path / 'citations', agent=ProbeAgent(fewer))
    assert result['evaluation']['workflow_pass']
    def incremental(context):
        observations = context['observations']
        if not observations:
            return call('list_vintages')
        ids = [v['vintage_id'] for v in observations[0]['result']['vintages']]
        checked = {c['vintage_id'] for o in observations if o['tool'] == 'check_asof_eligibility'
                   for c in o['result']['checks']}
        if set(ids) - checked:
            return call('check_asof_eligibility', vintage_ids=[next(v for v in ids if v not in checked)])
        if not any(o['tool'] == 'read_vintage' for o in observations):
            return call('read_vintage', vintage_id='v1')
        return {'action': 'FINAL', 'conclusion': CASES['WFA-02-available']['reference']['conclusion'],
                'evidence': [o['observation_id'] for o in observations if o['tool'] != 'list_vintages']}
    _, result = run(tmp_path / 'incremental', 'WFA-02-available', ProbeAgent(incremental))
    assert result['tool_calls'] == 6 and result['evaluation']['workflow_pass']


def test_unsettled_trial_cannot_be_finalized(tmp_path):
    def unfinished(context):
        if not context['observations']:
            return call('reserve_trial')
        return {'action': 'FINAL', 'conclusion': CASES['WFA-03-remaining']['reference']['conclusion'],
                'evidence': [o['observation_id'] for o in context['observations']]}
    _, result = run(tmp_path, 'WFA-03-remaining', ProbeAgent(unfinished))
    assert result['status'] == 'INVALID_ACTION' and result['error'] == 'FINAL_WITH_UNSETTLED_TRIAL'
    assert not result['evaluation']['workflow_pass']


def test_public_pit_contract_declares_selected_version_scope_and_nullability():
    for name in ('WFA-02-available', 'WFA-02-unavailable'):
        fields = CASES[name]['conclusion_contract']
        for fact in ('selected_vintage', 'published_at', 'available_at', 'event_effective_date'):
            assert fields[fact]['nullable'] is True
            assert 'selected' in fields[fact]['meaning']
    assert wf.read(wf.PACK / 'action_contract.json')['conclusion_value_rules']
