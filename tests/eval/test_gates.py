"""Adversarial gate tests; no statistical calibration or hidden outcomes."""
from dataclasses import replace
from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from quant_rsi.contracts.evaluation import EvalResult, GATES, BLOCK_REASONS
from quant_rsi.contracts.research import Candidate, Evidence
from quant_rsi.data.pit import canonical_bytes
from quant_rsi.eval.gates import evaluate


def result_contract():
    gates={g:dict(status='PASS',reason='SYNTHETIC_EVIDENCE',scope='SYNTHETIC_ONLY') for g in GATES}
    for g,reason in BLOCK_REASONS.items():gates[g]=dict(status='BLOCK',reason=reason,scope='FORMAL_RESEARCH')
    return EvalResult('EVAL-test','TASK-test','a'*64,'RUN-test','FAM-test','ATT-test','CAN-test',
        'B2-gates-v1','gates.py','b'*64,gates,{'EVI-test':'c'*64},{'synthetic_final_nav':'100'},
        {'capability_score':None},'critic:test',{'result.json':'d'*64},'settle:ATT-test','2000-01-01T00:00:00Z')


@pytest.mark.parametrize('gate',['G4','G6'])
@pytest.mark.parametrize('change',['PASS','N/A','omit','primitive_implemented','mock_passed'])
def test_required_formal_blocks_cannot_be_bypassed(gate,change):
    data=result_contract().to_dict()
    if change=='omit':del data['gates'][gate]
    else:data['gates'][gate]['status']='PASS' if change in ('primitive_implemented','mock_passed') else change
    with pytest.raises(ValueError):EvalResult.from_dict(data)


def test_formal_verdict_and_serialization_cannot_merge_scores_or_promote():
    original=result_contract();assert original.engineering_conformance=='PASS'
    assert EvalResult.from_dict(original.to_dict())==original
    assert original.formal_verdict=='BLOCKED' and original.signature is None
    for edit in ({'formal_verdict':'PASS'},{'signature':'fake-production-signature'},{'required_gates':['G0']},{'total_score':100}):
        with pytest.raises(ValueError):EvalResult.from_dict({**original.to_dict(),**edit})
    with pytest.raises(TypeError):original.gates['G4']['status']='PASS'


def case(tmp_path,**kwargs):
    from test_stage_b2 import build_case
    return build_case(tmp_path/'case',**kwargs)


def rerun(b, manifest=None, critic_report=None):
    m=b['manifest'] if manifest is None else manifest
    return evaluate(m,expected_manifest_digest=m.manifest_digest,trace_store=b['store'],resolve_artifact=b['artifacts'].__getitem__,
        critic_report=b['critic_report'] if critic_report is None else critic_report,author=b['author'],critic=b['critic'],created_at=m.created_at)


def test_clean_gates_read_only_and_explicit_block_reasons(tmp_path):
    b=case(tmp_path);before=b['store'].read();out=rerun(b)
    assert all(out.gates[g]['status']=='PASS' for g in ('G0','G1','G2','G3','G5','G7'))
    assert out.engineering_conformance=='PASS' and out.formal_verdict=='BLOCKED'
    assert out.gates['G4']['reason']=='D04B_NOT_FROZEN'
    assert out.gates['G6']['reason']=='BENCHMARK_GRADE_SEALED_INFRASTRUCTURE_ABSENT'
    assert 'SYNTHETIC' in out.gates['G5']['reason']
    assert b['store'].read()==before


@pytest.mark.parametrize('ref',['rows.json','environment-input.json','pit-observations.json','code-tree.json','dependencies.json'])
def test_missing_artifact_blocks_lineage_and_dependent_gates(tmp_path,ref):
    b=case(tmp_path);del b['artifacts'][ref]
    out=rerun(b);assert out.gates['G7']['status']=='BLOCK'
    assert out.formal_verdict=='BLOCKED'


def test_future_observation_claim_fails_independent_pit_recomputation(tmp_path):
    from hashlib import sha256
    b=case(tmp_path)
    data=json.loads(b['artifacts']['pit-observations.json']);data[0]['visible']=[]
    raw=canonical_bytes(data);b['artifacts']['pit-observations.json']=raw
    m=replace(b['manifest'],input_artifacts={**b['manifest'].input_artifacts,'pit-observations.json':sha256(raw).hexdigest()})
    out=rerun(b,m);assert out.gates['G1']['status']=='BLOCK'


def test_fabricated_measured_metric_cannot_pass_g7(tmp_path):
    from quant_rsi.agents.critic import review
    b=case(tmp_path);m=b['manifest']
    candidate=Candidate.from_dict(json.loads(b['artifacts'][next(iter(m.candidate_hashes))]))
    ref=next(iter(m.evidence_hashes));e=Evidence.from_dict(json.loads(b['artifacts'][ref]))
    forged=replace(e,metrics={'synthetic_final_nav':123456789})
    b['artifacts'][ref]=canonical_bytes(forged.to_dict())
    m=replace(m,evidence_hashes={ref:forged.content_digest()})
    report=review(candidate,[forged],author=b['author'],critic=b['critic'])
    out=rerun(b,m,report);assert out.gates['G7']['status']=='BLOCK'
    assert out.strategy_metrics=={}


def test_dangling_evidence_fails_lineage(tmp_path):
    b=case(tmp_path);ref=next(iter(b['manifest'].evidence_hashes));del b['artifacts'][ref]
    assert rerun(b).gates['G7']['status']=='BLOCK'


@pytest.mark.parametrize('randomness',['externally_nondeterministic','provider_randomness_unknown'])
def test_nondeterministic_run_never_gets_deterministic_g2(tmp_path,randomness):
    b=case(tmp_path,randomness=randomness);out=rerun(b)
    assert out.gates['G2']['status']=='BLOCK' and out.formal_verdict=='BLOCKED'


def test_unsupported_evaluator_version_blocks_contract(tmp_path):
    b=case(tmp_path,task_updates={'evaluator_version':'unsupported-version'})
    assert rerun(b).gates['G0']['status']=='FAIL'


def test_unaccounted_worker_call_cannot_pass_g3(tmp_path):
    b=case(tmp_path)
    b['store'].append('unaccounted-call','WORKER_REQUEST',{'attempt_id':'ATT-unregistered'})
    assert rerun(b).gates['G3']['status']=='BLOCK'


def test_canonical_critic_rejection_cannot_be_erased_by_clean_report(tmp_path):
    from quant_rsi.agents.critic import Issue, review
    issue=Issue('ISS-unresolved','P1',('EVI-B2',),'Evidence requires correction','New evidence required')
    b=case(tmp_path,issues=(issue,))
    clean=review(b['candidate'],[b['evidence']],author=b['author'],critic=b['critic'])
    out=rerun(b,critic_report=clean)
    assert out.gates['G7']['status']=='BLOCK' and out.engineering_conformance=='BLOCKED'
    assert out.critic_report_ref=='critic:'+b['critic_report'].content_digest()


@pytest.mark.parametrize('attack',['missing','tampered'])
def test_admitted_critic_report_bytes_are_required(tmp_path,attack):
    b=case(tmp_path);ref='critic:'+b['critic_report'].content_digest()
    if attack=='missing':del b['artifacts'][ref]
    else:b['artifacts'][ref]=b'{}'
    assert rerun(b).gates['G7']['status']=='BLOCK'
