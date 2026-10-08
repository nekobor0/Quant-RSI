"""Coordinator idempotency and canonical-budget escape regressions."""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integration'))
from test_stage_b2 import build_case
from quant_rsi.agents.worker import FakeProvider
from quant_rsi.contracts.condition import BUDGET_DIMENSIONS, RESOURCE_DIMENSIONS, load_decisions
from quant_rsi.orchestration.runner import run_once


def next_args(b, **updates):
    return {**b['execution_args'], 'delivery_id': 'DEL-next', 'attempt_id': 'ATT-next',
            'scientific_variant_id': 'VAR-next', 'candidate_id': 'CAN-next',
            'evidence_id': 'EVI-next', 'manifest_id': 'MAN-next',
            'envelope': dict(attempts=1, candidate_trials=1, **dict.fromkeys(RESOURCE_DIMENSIONS, 1)),
            **updates}


def test_duplicate_delivery_returns_frozen_archive_without_new_attempt(tmp_path):
    b = build_case(tmp_path)
    before = b['store'].read()
    again = run_once(**b['execution_args'])
    assert again == b['outcome'] and b['store'].read() == before
    with pytest.raises(ValueError, match='fingerprint'):
        run_once(**{**b['execution_args'], 'candidate_id': 'CAN-changed'})
    with pytest.raises(ValueError, match='already claimed'):
        run_once(**{**b['execution_args'], 'delivery_id': 'DEL-other'})


def test_exhausted_budget_never_dispatches(tmp_path):
    b = build_case(tmp_path, task_updates={'budget_limits': dict.fromkeys(BUDGET_DIMENSIONS, 0)})
    assert b['status'] == 'BUDGET_EXHAUSTED'
    assert not any(e['kind'] in ('ATTEMPT_STARTED', 'WORKER_REQUEST') for e in b['store'].read())
    assert any(e['kind'] == 'ATTEMPT_DENIED' for e in b['store'].read())


def test_unknown_usage_retains_reservation_and_blocks_next_attempt(tmp_path):
    b = build_case(tmp_path, mode='unknown_usage')
    assert run_once(**next_args(b))['status'] == 'BUDGET_EXHAUSTED'
    assert sum(e['kind'] == 'WORKER_REQUEST' for e in b['store'].read()) == 1


def test_explicit_retry_uses_new_attempt_and_same_root(tmp_path):
    b = build_case(tmp_path, mode='failure')
    args = next_args(b, retry_of='ATT-B2', scientific_variant_id='VAR-B2',
        provider=FakeProvider(b['artifacts']['environment-input.json'], reported_usage=dict.fromkeys(RESOURCE_DIMENSIONS, 1)),
        envelope=dict(attempts=1, retries=1, **dict.fromkeys(RESOURCE_DIMENSIONS, 1)))
    assert run_once(**args)['status'] == 'EVALUATED'
    usage = b['budget'].capability_accounting('RUN-B2')['usage']
    assert usage['attempts'] == 2 and usage['candidate_trials'] == 1 and usage['retries'] == 1
    starts = [e['payload'] for e in b['store'].read() if e['kind'] == 'ATTEMPT_STARTED']
    assert {a['budget_root_run_id'] for a in starts} == {'RUN-B2'}
    assert starts[1]['retry_of'] == 'ATT-B2'


@pytest.mark.parametrize('change', ['model', 'prompt'])
def test_run_model_or_prompt_change_cannot_reset_budget_root(tmp_path, change):
    b = build_case(tmp_path)
    changes = {'agent_model': 'fake-other'} if change == 'model' else {'prompt_hash': 'a' * 64}
    other = replace(b['run'], benchmark_run_id='RUN-other', budget_root_run_id='RUN-other', **changes)
    b['budget'].register_run(other, b['condition'], decision_snapshot=load_decisions())
    exp = replace(b['experiment'], experiment_id='EXP-other', benchmark_run_id='RUN-other')
    b['budget'].register_experiment(exp)
    request = replace(b['execution_args']['request'], run_id='RUN-other', model_id=other.agent_model, prompt_hash=other.prompt_hash)
    args = next_args(b, run_id='RUN-other', experiment_id='EXP-other', request=request,
                     author=replace(b['author'], run_id='RUN-other'))
    before = b['store'].read()
    with pytest.raises(ValueError, match='multiple budget roots'):
        run_once(**args)
    assert b['store'].read() == before


def test_current_b2_authority_is_checked_before_new_dispatch(tmp_path, monkeypatch):
    b = build_case(tmp_path)
    registry = load_decisions()
    registry['activation']['stage_B2']['authorized'] = False
    monkeypatch.setattr('quant_rsi.orchestration.runner.load_decisions', lambda: registry)
    before = b['store'].read()
    with pytest.raises(ValueError, match='not authorized'):
        run_once(**next_args(b))
    assert b['store'].read() == before


def test_post_settlement_collision_preserves_failed_delivery_and_compute(tmp_path):
    b=build_case(tmp_path);args=next_args(b)
    b['artifacts']['CAN-next']=b'preexisting immutable artifact'
    out=run_once(**args)
    assert out['status']=='FAILED'
    events=b['store'].read();by_id={e['event_id']:e for e in events}
    assert by_id['settle:ATT-next']['payload']['status']=='SUCCEEDED'
    failure=by_id['delivery-failure:DEL-next']['payload']
    assert 'immutable artifact reference collision' in failure['failure']
    assert failure['partial_refs']=={'result':'result-ATT-next.json'}
    assert by_id['archive:DEL-next']['payload']['status']=='FAILED'
    assert run_once(**args)==out and b['store'].read()==events


def test_reconciled_unknown_usage_retry_uses_effective_canonical_accounting(tmp_path):
    from quant_rsi.eval.gates import evaluate
    b=build_case(tmp_path,mode='unknown_usage')
    b['budget'].reconcile('ATT-B2',dict.fromkeys(RESOURCE_DIMENSIONS,1))
    args=next_args(b,retry_of='ATT-B2',scientific_variant_id='VAR-B2',
        provider=FakeProvider(b['artifacts']['environment-input.json'],reported_usage=dict.fromkeys(RESOURCE_DIMENSIONS,1)),
        envelope=dict(attempts=1,retries=1,**dict.fromkeys(RESOURCE_DIMENSIONS,1)))
    out=run_once(**args)
    assert out['eval_result'].gates['G3']['status']=='PASS'
    assert b['budget'].capability_accounting('RUN-B2')['usage']['attempts']==2
    original=next(e['payload'] for e in b['store'].read() if e['event_id']=='settle:ATT-B2')
    assert original['status']=='FAILED' and original['actual_resources'] is None
    manifest=replace(out['manifest'],trace_refs={k:v for k,v in out['manifest'].trace_refs.items() if k!='reconcile:ATT-B2'})
    result=evaluate(manifest,expected_manifest_digest=manifest.manifest_digest,trace_store=b['store'],
        resolve_artifact=b['artifacts'].__getitem__,critic_report=out['critic_report'],
        author=b['author'],critic=b['critic'],created_at=manifest.created_at)
    assert result.gates['G3']['status']=='BLOCK'


def test_revoked_authority_after_reserve_prevents_worker_handoff(tmp_path,monkeypatch):
    b=build_case(tmp_path);registry=load_decisions()
    monkeypatch.setattr('quant_rsi.orchestration.runner.load_decisions',lambda:registry)
    original_reserve=b['budget'].reserve
    def revoke(*args,**kwargs):
        result=original_reserve(*args,**kwargs)
        registry['activation']['stage_B2']['authorized']=False
        return result
    monkeypatch.setattr(b['budget'],'reserve',revoke)
    assert run_once(**next_args(b))['status']=='FAILED'
    events=b['store'].read()
    assert not any(e['event_id']=='worker-request:ATT-next' for e in events)
    terminal=next(e['payload'] for e in events if e['event_id']=='settle:ATT-next')
    assert 'not authorized' in terminal['failure'] and terminal['actual_resources'] is None
