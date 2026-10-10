import pytest

from quant_rsi.harness import cp_acceptance_finalize as final
from quant_rsi.harness import cp_acceptance as cp
from quant_rsi.harness.agent_workflow import read


@pytest.mark.parametrize('task_id', ['Q-CP-01', 'Q-CP-02', 'Q-CP-03', 'Q-CP-04'])
def test_actual_positive_and_negative_code_diagnostics(task_id):
    tasks, result = read(cp.PACK / 'cases.json'), read(cp.PACK / 'results.json')
    for item in result['records']:
        if item['task_id'] != task_id:
            continue
        score = final.diagnose(tasks[task_id], item['evidence'])
        if item['kind'] in ('reference', 'equivalent'):
            assert all(score['vector'].values())
        else:
            assert any(score['vector'].values()) and not all(score['vector'].values())


@pytest.mark.parametrize('kind,input_ok,facts_ok', [('current-lookahead', True, False), ('mutates-input', False, True)])
def test_input_mutation_distinguished_from_numeric_error(kind, input_ok, facts_ok):
    task = read(cp.PACK / 'cases.json')['Q-CP-02']
    record = next(r['evidence'] for r in read(cp.PACK / 'results.json')['records'] if r['kind'] == kind)
    vector = final.diagnose(task, record)['vector']
    assert vector['INPUT_PRESERVED'] is input_ok
    assert vector['RESULT_FACTS_CORRECT'] is facts_ok
    assert vector['INVALID_INPUT_HANDLING'] is True


def test_numeric_error_not_reported_as_input_or_state_mutation():
    tasks = read(cp.PACK / 'cases.json')
    for item in read(cp.PACK / 'results.json')['records']:
        if item['kind'] not in ('wrong-cost', 'compound-sum'):
            continue
        vector = final.diagnose(tasks[item['task_id']], item['evidence'])['vector']
        assert vector['INPUT_PRESERVED'] is True
        assert vector['RESULT_FACTS_CORRECT'] is False
        assert vector['RETURN_STATE_INDEPENDENT'] is True


def test_shared_returns_are_state_faults_with_inputs_preserved():
    task = read(cp.PACK / 'cases.json')['Q-CP-04']
    record = next(r['evidence'] for r in read(cp.PACK / 'results.json')['records'] if r['kind'] == 'shared-return')
    vector = final.diagnose(task, record)['vector']
    assert vector['RETURN_STATE_INDEPENDENT'] is False
    assert vector['INPUT_PRESERVED'] is True


def test_execution_failures_remain_separate():
    task = read(cp.PACK / 'cases.json')['Q-CP-01']
    assert final.diagnose(task, dict(status='WALL_TIMEOUT')) == dict(vector=None, execution_failure='WALL_TIMEOUT')


def test_final_replay_no_docker_and_no_tool_execution(monkeypatch):
    if not (cp.PACK / 'acceptance.json').exists():
        pytest.skip('final diagnostics not generated yet')
    def forbidden(*args, **kwargs):
        raise AssertionError('unexpected execution')
    monkeypatch.setattr(cp.isolation, 'docker', forbidden)
    monkeypatch.setattr(cp, 'execute', forbidden)
    assert final.replay()['sessions'] == 16
