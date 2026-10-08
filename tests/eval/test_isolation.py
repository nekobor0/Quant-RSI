from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import os

import pytest
from quant_rsi.eval.isolation import MockIsolation
from quant_rsi.ledger.store import TraceStore


def service(tmp_path, *, limit=3, mode='normal'):
    root=tmp_path/'public';root.mkdir()
    (root/'feature.txt').write_bytes(b'PUBLIC_SYNTHETIC')
    evaluator=tmp_path/'evaluator.txt';evaluator.write_bytes(b'FROZEN_SYNTHETIC_EVALUATOR')
    review=json.loads((Path(__file__).resolve().parents[2]/'artifacts/stage_b1/w09_tm01_custodian_review.json').read_text(encoding='utf-8'))
    return MockIsolation(TraceStore(tmp_path/'trace.sqlite'),condition_id='COND-mock',holdout_id='HOLDOUT-synthetic',root=root,
        public_files={'feature.txt':sha256(b'PUBLIC_SYNTHETIC').hexdigest()},evaluator_path=evaluator,
        evaluator_hash=sha256(evaluator.read_bytes()).hexdigest(),submission_limit=limit,tm_review=review,diagnostic_mode=mode)


def submit(s,identity='REQ-one',**extra):
    return s.request(identity,'CAN-one','submit',dict(artifact_ref='result',artifact_hash='a'*64,**extra))


@pytest.mark.parametrize('operation,payload',[
    ('read_public',{'ref':'../hidden'}),('read_public',{'ref':'C:/hidden'}),('read_public',{'ref':'private.txt'}),
    ('network',{'url':'https://example.invalid'}),('DNS',{'host':'metadata'}),('metadata',{'url':'http://169.254.169.254'}),
    ('tool',{'name':'inherited-shell'}),('hidden_seed',{}),('shared_cache',{}),('path_size',{'ref':'hidden'}),
])
def test_attack_channels_are_denied_in_mock_only(tmp_path,operation,payload):
    s=service(tmp_path)
    result=s.request('REQ-attack','CAN-one',operation,payload)
    assert result=={'assurance':'SYNTHETIC_MOCK','status':'BLOCKED','feedback':None,'error_id':'MOCK_DENIED'}
    assert submit(s,'REQ-after')['status']=='BLOCKED'
    report=s.assurance_report()
    assert report['formal_G6']=='BLOCKED' and report['results']=='UNDER_REVIEW'
    assert set(report['deployment'].values())=={'UNVERIFIED / REQUIRES_DEPLOYMENT'}


@pytest.mark.parametrize('mode',['stdout','stderr','exception'])
def test_stdout_stderr_exception_sanitized_without_metadata(tmp_path,capsys,mode):
    s=service(tmp_path,mode=mode); result=submit(s)
    captured=capsys.readouterr()
    assert captured.out==captured.err==''
    assert 'PRIVATE' not in json.dumps(result) and str(tmp_path) not in json.dumps(result)
    assert result['status']==('BLOCKED' if mode=='exception' else 'ACCEPTED')


def test_atomic_counts_retries_repeated_submission_and_counter_bypass(tmp_path):
    s=service(tmp_path,limit=1)
    first=submit(s);assert submit(s)==first
    assert submit(s,'REQ-two')['status']=='BLOCKED'
    assert submit(s,'REQ-three',submission_count=0)['status']=='BLOCKED'
    assert len([e for e in s.store.read() if e['kind']=='MOCK_REQUEST'])==3
    # Reopening cannot replace the pinned condition config or erase exposure.
    with pytest.raises(ValueError):
        MockIsolation(s.store,condition_id='COND-mock',holdout_id='HOLDOUT-synthetic',root=s.root,public_files=s.public_files,
            evaluator_path=s.evaluator_path,evaluator_hash=s.evaluator_hash,submission_limit=100,
            tm_review={'decision':'PASS_FOR_SYNTHETIC_MOCK','unresolved_P0_P1':[]})


def test_concurrent_submission_one_slot(tmp_path):
    s=service(tmp_path,limit=1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda n:submit(s,'REQ-'+str(n)),range(4)))
    assert sum(r['status']=='ACCEPTED' for r in results)==1


def test_condition_version_change_cannot_reset_same_holdout_exposure(tmp_path):
    s=service(tmp_path,limit=1);assert submit(s)['status']=='ACCEPTED'
    other=MockIsolation(s.store,condition_id='COND-version2',holdout_id='HOLDOUT-synthetic',root=s.root,
        public_files=s.public_files,evaluator_path=s.evaluator_path,evaluator_hash=s.evaluator_hash,
        submission_limit=1,tm_review={'decision':'PASS_FOR_SYNTHETIC_MOCK','unresolved_P0_P1':[]})
    assert submit(other,'REQ-new')['status']=='BLOCKED'


def test_evaluator_modification_and_client_identity_tool_injection(tmp_path):
    s=service(tmp_path);s.evaluator_path.write_bytes(b'CHANGED')
    assert submit(s)['status']=='BLOCKED'
    assert submit(s,'REQ-new',evaluator_hash='b'*64,principal='custodian',tools=['shell'])['status']=='BLOCKED'


def test_symlink_or_junction_escape_denied(tmp_path):
    s=service(tmp_path);outside=tmp_path/'outside';outside.mkdir();(outside/'secret.txt').write_text('private')
    link=s.root/'linked'
    try:link.symlink_to(outside,target_is_directory=True)
    except OSError:
        if os.name!='nt':raise
        result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
        assert result.returncode==0,result.stderr
    s.public_files['linked/secret.txt']=sha256(b'private').hexdigest()
    assert s.request('REQ-link','CAN-one','read_public',{'ref':'linked/secret.txt'})['status']=='BLOCKED'


def test_missing_tm01_review_is_blocked(tmp_path):
    with pytest.raises(ValueError,match='prerequisite'):
        MockIsolation(None,condition_id='COND-test',holdout_id='HOLDOUT-synthetic',root=tmp_path,public_files={},evaluator_path=tmp_path/'x',
            evaluator_hash='a'*64,submission_limit=1,tm_review={})


def test_critic_07_request_identity_bound_to_condition(tmp_path):
    s=service(tmp_path,limit=1);assert submit(s)['status']=='ACCEPTED'
    other=MockIsolation(s.store,condition_id='COND-version2',holdout_id='HOLDOUT-synthetic',root=s.root,
        public_files=s.public_files,evaluator_path=s.evaluator_path,evaluator_hash=s.evaluator_hash,
        submission_limit=1,tm_review={'decision':'PASS_FOR_SYNTHETIC_MOCK','unresolved_P0_P1':[]})
    assert submit(other)['status']=='BLOCKED'
    assert other.assurance_report()['results']=='UNDER_REVIEW'


def test_critic_08_invalid_json_is_sanitized_and_recorded(tmp_path):
    s=service(tmp_path)
    result=submit(s,junk=float('nan'))
    assert result['status']=='BLOCKED'
    assert len([e for e in s.store.read() if e['kind']=='MOCK_REQUEST'])==1
