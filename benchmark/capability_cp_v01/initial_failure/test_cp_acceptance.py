import copy
import json
import shutil

import pytest

from quant_rsi.harness import cp_acceptance as cp
from quant_rsi.harness.cp_acceptance_cases import materials, candidates
from quant_rsi.harness.agent_workflow import ROOT, read, save


def observation(task):
    return dict(status='COMPLETED', stdout=json.dumps(dict(records=[dict(value=copy.deepcopy(case['expected']),
        error=None, input_unchanged=True) for case in task['cases']], retained=copy.deepcopy(task['expected_retained']))))


@pytest.mark.parametrize('task_id', [f'Q-CP-{n:02}' for n in range(1, 5)])
def test_every_frozen_property_has_observations_and_expected_scores(task_id):
    task = materials()[task_id]
    actual = cp.score(task, observation(task))
    assert actual['full_pass'] and all(actual['properties'].values())
    assert set(actual['properties']) == set(read(ROOT / 'benchmark/capability_supplement_v01/cp_contracts.json')['tasks'][task_id]['properties'])
    assert all(c['properties'] for c in task['cases'])
    assert len(task['operations']) == len(task['cases']) + int(task_id == 'Q-CP-04')


def test_invalid_non_json_fixtures_and_no_oracle_release():
    tasks = materials()
    for task in tasks.values():
        packet = dict(mode='calls', operations=task['operations'])
        text = json.dumps(packet, allow_nan=False)
        assert '$float' in text and '$tuple' in text
        assert 'expected' not in text and 'property_names' not in text
    campaign = list(candidates())
    assert len(campaign) == 16
    assert all(len(source.encode()) < 65536 for _, _, source in campaign)
    assert sum(kind == 'reference' for _, kind, _ in campaign) == 4


@pytest.mark.parametrize('corruption', ['input', 'state', 'fact', 'exception', 'identity', 'bool', 'extra'])
def test_external_predicates_reject_precise_faults_without_all_zero(corruption):
    task = materials()['Q-CP-01']
    record = observation(task)
    obj = json.loads(record['stdout'])
    value = obj['records'][1]['value']
    if corruption == 'input':
        value['after'][0][0]['price'] += 1e-10
    elif corruption == 'state':
        obj['retained'][1]['result'][0]['price'] = 99
    elif corruption == 'fact':
        value['result'][0]['price'] = 99
    elif corruption == 'exception':
        value['exception'] = 'TypeError'
    elif corruption == 'identity':
        value['result'][0]['security'] = 'a'
    elif corruption == 'bool':
        value['result'][0]['price'] = True
    else:
        value['result'][0]['extra'] = 1
    record['stdout'] = json.dumps(obj)
    result = cp.score(task, record)
    assert not result['full_pass']
    assert any(result['properties'].values()) and not all(result['properties'].values())


@pytest.mark.parametrize('delta,passed', [(1e-8, True), (1.01e-8, False)])
def test_absolute_numeric_tolerance(delta, passed):
    task = materials()['Q-CP-03']
    record = observation(task)
    obj = json.loads(record['stdout'])
    for collection in ('records', 'retained'):
        value = obj[collection][1]['value'] if collection == 'records' else obj[collection][1]
        value['result']['pnl'][0] = delta
    record['stdout'] = json.dumps(obj)
    assert cp.score(task, record)['full_pass'] is passed


@pytest.mark.parametrize('failure', ['WALL_TIMEOUT', 'WORKER_OOM', 'OUTPUT_LIMIT_EXCEEDED', 'WORKER_FAILED'])
def test_execution_failure_is_not_research_all_zero(failure):
    value = cp.score(materials()['Q-CP-01'], dict(status=failure))
    assert value['execution_failure'] == failure and value['properties'] is None


@pytest.mark.parametrize('text', ['{"score":"PASS"}', '{bad',
    '{"records":[],"records":[],"retained":[]}', '{"records":[],"retained":[]}'])
def test_invalid_result_cannot_supply_score(text):
    value = cp.score(materials()['Q-CP-01'], dict(status='COMPLETED', stdout=text))
    assert value['execution_failure'] == 'INVALID_RESULT_SCHEMA'


def test_cp04_expected_state_after_return_mutation():
    task = materials()['Q-CP-04']
    first = task['cases'][1]['expected']['result'][0]
    assert first['amount'] == 2
    assert task['expected_retained'][1]['result'][0]['amount'] == 999
    assert task['expected_retained'][2]['result'][0]['amount'] == 2
    assert task['expected_retained'][5]['result'][0]['amount'] == 2


def completed():
    if not (cp.PACK / 'results.json').exists():
        pytest.skip('isolated campaign not yet executed')


def test_replay_performs_no_execution(monkeypatch):
    completed()
    def forbidden(*args, **kwargs):
        raise AssertionError('execution during replay')
    monkeypatch.setattr(cp.isolation, 'docker', forbidden)
    monkeypatch.setattr(cp.isolation, 'execute', forbidden)
    assert cp.replay()['sessions'] == 16


@pytest.mark.parametrize('change', ['observation', 'score', 'budget', 'trace', 'freeze'])
def test_replay_detects_tampering_even_with_updated_result_receipt(tmp_path, monkeypatch, change):
    completed()
    for name in ('freeze.json', 'results.json', 'trace.json', 'receipt.json', 'cases.json', 'campaign.json'):
        shutil.copyfile(cp.PACK / name, tmp_path / name)
    monkeypatch.setattr(cp, 'PACK', tmp_path)
    result = read(tmp_path / 'results.json')
    if change == 'observation':
        result['records'][0]['evidence']['stdout'] = '{}'
    elif change == 'score':
        result['records'][0]['score']['full_pass'] = False
    elif change == 'budget':
        result['budget']['usage']['attempts'] = 0
    elif change == 'trace':
        trace = read(tmp_path / 'trace.json')
        trace[0]['payload']['tampered'] = True
        save(tmp_path / 'trace.json', trace)
    else:
        freeze = read(tmp_path / 'freeze.json')
        freeze['policy']['max_sessions'] = 999
        save(tmp_path / 'freeze.json', freeze)
    save(tmp_path / 'results.json', result)
    receipt = read(tmp_path / 'receipt.json')
    receipt.update({name+'_sha256': cp.sha(tmp_path / (name+'.json')) for name in ('results', 'trace', 'freeze')})
    save(tmp_path / 'receipt.json', receipt)
    with pytest.raises(ValueError):
        cp.replay()
