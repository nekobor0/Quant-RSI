from dataclasses import replace
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from test_stage_b1 import build_bundle,run_replay
from quant_rsi.eval.replay import replay
from quant_rsi.ledger.store import TraceStore


@pytest.fixture
def bundle(tmp_path):return build_bundle(tmp_path/'bundle')


def test_deterministic_replay_is_readonly(bundle):
    before=bundle['store'].path.read_bytes()
    assert run_replay(bundle)['assurance']=='DETERMINISTIC_REPRODUCED'
    assert bundle['store'].path.read_bytes()==before


@pytest.mark.parametrize('ref',['rows.json','code-tree.json','dependencies.json','environment-input.json','result.json'])
@pytest.mark.parametrize('action',['missing','changed'])
def test_missing_changed_artifact_blocks(bundle,ref,action):
    if action=='missing':del bundle['artifacts'][ref]
    else:bundle['artifacts'][ref]=b'changed'
    assert run_replay(bundle)['assurance']=='REPLAY_BLOCKED'


@pytest.mark.parametrize('field,value',[('seed',8),('runtime_identity','wrong-runtime'),('tool_versions',{'daily':'wrong'})])
def test_seed_runtime_tool_mismatch(bundle,field,value):
    m=replace(bundle['manifest'],**{field:value})
    assert run_replay(bundle,m)['assurance']=='REPLAY_BLOCKED'


@pytest.mark.parametrize('kind',['DECISION_SNAPSHOT','ATTEMPT_SETTLED'])
def test_historical_registry_or_terminal_tampering_blocks(bundle,tmp_path,kind):
    copy=TraceStore(tmp_path/'tampered.sqlite')
    for event in bundle['store'].read():
        p=event['payload']
        if event['kind']==kind:p=dict(p,version='changed')
        copy.append(event['event_id'],event['kind'],p)
    bundle['store']=copy
    assert run_replay(bundle)['assurance']=='REPLAY_BLOCKED'


@pytest.mark.parametrize('mode',['externally_nondeterministic','provider_randomness_unknown'])
def test_nondeterministic_provenance_never_reproducibility(tmp_path,mode):
    b=build_bundle(tmp_path/'non',mode)
    r=run_replay(b)
    assert r['assurance']=='PROVENANCE_VERIFIED_NONDETERMINISTIC'
    assert r['formal_G2']=='NOT_EVALUATED'
    with pytest.raises(ValueError):replace(b['manifest'],randomness='fixed_seed_deterministic')
    fake=replace(b['manifest'],randomness='fixed_seed_deterministic',seed=7)
    assert run_replay(b,fake)['assurance']=='REPLAY_BLOCKED'


def test_frozen_expected_manifest_digest_cannot_be_replaced(bundle):
    m=replace(bundle['manifest'],seed=8)
    result=replay(m,expected_manifest_digest=bundle['manifest'].manifest_digest,replay_id='REPLAY-test',
        trace_store=bundle['store'],resolve_artifact=bundle['artifacts'].__getitem__)
    assert result['assurance']=='REPLAY_BLOCKED'


def test_output_mismatch_is_failure_not_pass(bundle,monkeypatch):
    monkeypatch.setattr('quant_rsi.eval.replay.simulate',lambda *args: {'different':'output'})
    assert run_replay(bundle)['assurance']=='REPLAY_FAILED'


def test_changed_installed_code_or_dependency_blocks(bundle,monkeypatch):
    monkeypatch.setattr('quant_rsi.eval.replay.installed_code_bundle',lambda:{})
    assert run_replay(bundle)['assurance']=='REPLAY_BLOCKED'
