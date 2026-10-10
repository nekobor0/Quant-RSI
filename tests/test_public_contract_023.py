"""Full-suite public prompt binding, without model or credential access."""
import copy
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from quant_rsi.harness import public_contract_023 as bundle, evaluator_023 as evaluator
from quant_rsi.harness import capability_oracle as oracle, providers

SUITE = oracle.suite_fixtures('0.2')
SAMPLES = json.loads(oracle.V02_PATH.with_name('validation_samples_v02.json').read_bytes())


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('network or credential resolution forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(providers.urllib.request, 'urlopen', forbidden)
    monkeypatch.setattr(providers.ChatProvider, '_resolve_key', forbidden)


def test_full_freeze_binding_and_execution_not_authorized():
    assert len(bundle.verify()) == 64
    plan = json.loads((bundle.DIRECTORY / 'prompt_freeze.json').read_bytes())
    assert plan['task_ids'] == SUITE['task_order']
    assert plan['source_cluster_count'] == 10
    assert set(plan['primary_dimension_counts'].values()) == {4}
    assert not plan['real_execution_authorized'] and not plan['budget_authorized']
    assert plan['execution_entry'] is None and plan['segment_schedule'] is None


@pytest.mark.parametrize('tid', SUITE['task_order'])
def test_published_input_contract_and_frozen_score_examples(tid):
    prompts = json.loads((bundle.DIRECTORY / 'prompts.json').read_bytes())
    contracts = json.loads((bundle.DIRECTORY / 'contracts.json').read_bytes())['tasks']
    user = prompts['user'][tid]
    assert user == providers.build_prompt(tid, SUITE['tasks'][tid]['public_input'],
                                          contract=contracts[tid])
    assert 'ground_truth' not in user and 'accept_verdicts' not in user
    assert contracts[tid]['version'] == bundle.policy.CONTRACT_VERSION
    assert evaluator.adjudicate(tid, bundle.encode(SAMPLES[tid]['correct'])).full_pass
    assert not evaluator.adjudicate(tid, bundle.encode(SAMPLES[tid]['wrong_decision'])).full_pass


def test_ground_truth_does_not_enter_any_public_message(monkeypatch):
    before = bundle.artifacts()
    modified = copy.deepcopy(SUITE)
    for task in modified['tasks'].values():
        task['ground_truth'] = {'SECRET_SENTINEL': 'never release'}
    monkeypatch.setattr(oracle, 'suite_fixtures', lambda *args: modified)
    assert bundle.artifacts() == before


def test_six_existing_prompt_bytes_preserved():
    previous = json.loads(evaluator.FREEZE.with_name('prompts.json').read_bytes())
    current = json.loads(bundle.artifacts()['prompts.json'])
    assert current['system'] == previous['system']
    assert all(current['user'][tid] == text for tid, text in previous['user'].items())


def test_changed_public_input_changes_prompt_and_binding(monkeypatch):
    before = bundle.artifacts()
    modified = copy.deepcopy(SUITE)
    tid = SUITE['task_order'][0]
    modified['tasks'][tid]['public_input']['controlled_test_marker'] = 'observation changed'
    monkeypatch.setattr(oracle, 'suite_fixtures', lambda *args: modified)
    after = bundle.artifacts()
    assert before['contracts.json'] == after['contracts.json']
    assert before['prompts.json'] != after['prompts.json']
    assert before['prompt_freeze.json'] != after['prompt_freeze.json']


@pytest.mark.parametrize('name', bundle.FILES)
def test_tampering_rejected_and_existing_artifacts_preserved(tmp_path, name):
    bundle.write(tmp_path)
    target = tmp_path / name
    target.write_bytes(target.read_bytes() + b' ')
    damaged = target.read_bytes()
    with pytest.raises(ValueError, match='binding changed'):
        bundle.verify(tmp_path)
    with pytest.raises(ValueError, match='preserve existing binding'):
        bundle.write(tmp_path)
    assert target.read_bytes() == damaged
