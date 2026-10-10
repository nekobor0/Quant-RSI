"""No sockets/real credentials: frozen wire capture and cross-segment safety."""
import copy
import io
import json
import socket
import urllib.error
from datetime import datetime, timezone
from http.client import IncompleteRead

import pytest

from quant_rsi.harness import segmented_comparison_023 as new, providers
from quant_rsi.harness import compatibility_pilot as pilot, capability_oracle as oracle
from quant_rsi.ledger.store import TraceStore

SAMPLES=pilot.load(oracle.V02_PATH.with_name('validation_samples_v02.json'))
KEY='synthetic-offline-transport-key'


@pytest.fixture(autouse=True)
def offline(monkeypatch,tmp_path):
    monkeypatch.setattr(socket.socket,'connect',lambda *a:pytest.fail('network forbidden'))
    monkeypatch.setenv('DEEPSEEK_API_KEY',KEY)
    monkeypatch.setenv('XIAOMI_API_KEY',KEY)
    monkeypatch.setattr(new.policy.base,'utc_now',lambda:datetime(2026,10,10,tzinfo=timezone.utc))
    monkeypatch.setattr(new,'OUTPUT',tmp_path/'batch')


def approval():
    return dict(pilot.load(new.PACK/'execution_authorization_request.json'),approved=True,
        authorization_source='Synthetic offline test approval only.',prices_reconfirmed=True,valid_on='2026-10-10')


class Response:
    status=200
    def __init__(self,raw,error=None): self.raw,self.error=raw,error
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self):
        if self.error: raise self.error
        return self.raw


def transport(monkeypatch,failure=None):
    calls=[]
    def dispatch(request,timeout):
        body=json.loads(request.data); calls.append(body)
        tid=body['messages'][1]['content'].splitlines()[0].split(': ')[1]
        if failure=='partial': return Response(None,IncompleteRead(b'{"partial":true}',10))
        if failure=='json': return Response(b'{bad envelope')
        if failure=='429': raise urllib.error.HTTPError('https://offline.invalid',429,'busy',{},io.BytesIO(b'{"error":"busy"}'))
        if failure=='timeout': raise TimeoutError('synthetic')
        if failure=='reset': raise ConnectionResetError('synthetic')
        if failure=='business': return Response(b'{"error":{"code":"rejected"}}')
        sample=copy.deepcopy(SAMPLES[tid]['correct'])
        if failure=='research': sample=SAMPLES[tid]['wrong_decision']
        text=json.dumps(sample)
        envelope=dict(model=body['model'],choices=[dict(finish_reason='stop',message=dict(content=text))],
            usage=dict(prompt_tokens=100,completion_tokens=50,total_tokens=150,
                       completion_tokens_details=dict(reasoning_tokens=20)))
        if failure=='unknown': envelope.pop('usage')
        if failure=='identity': envelope['model']='wrong-model'
        if failure=='overbudget': envelope['usage'].update(prompt_tokens=20000,total_tokens=20050)
        if failure=='length': envelope['choices'][0].update(finish_reason='length'); envelope['choices'][0]['message']['content']=''
        if failure=='leak': envelope['choices'][0]['message']['content']=KEY
        return Response(json.dumps(envelope).encode())
    monkeypatch.setattr(providers.urllib.request,'urlopen',dispatch)
    return calls


def check_capture(calls):
    plan=new.validate(); prompts=pilot.load(new.PACK/'prompts.json')
    for body in calls:
        tid=body['messages'][1]['content'].splitlines()[0].split(': ')[1]
        assert body['messages']==[dict(role='system',content=prompts['system']),dict(role='user',content=prompts['user'][tid])]
        pid='deepseek' if body['model']=='deepseek-flash' else 'xiaomi'
        assert body['thinking']=={'type':'enabled'} and 'tools' not in body
        if pid=='deepseek': assert body['max_tokens']==24000 and body['reasoning_effort']=='high'
        else: assert body['max_completion_tokens']==24000 and 'max_tokens' not in body and body['temperature']==1.0 and body['top_p']==0.95
        assert body['model']==plan['providers'][pid]['chat_provider']['model_id']


def review(n):
    if pilot.load(new.OUTPUT/'summary.json')['status']=='ANOMALY_REVIEW_REQUIRED':
        new.review_segment(n,'continue','Offline fixture answers compared to task truth and raw captured envelopes; no blocker in this synthetic fixture.',approval())


def test_freeze_exact_24_tasks_four_balanced_segments():
    plan=new.validate()
    assert plan['calls']==48 and len(plan['task_ids'])==24
    assert plan['source_cluster_count']==10
    suite=oracle.suite_fixtures('0.2')
    selected=[t for s in plan['segments'] for t in s['task_ids']]
    assert len(set(selected))==24 and set(selected)==set(plan['task_ids'])
    for s in plan['segments']:
        assert len({suite['tasks'][t]['primary_dimension'] for t in s['task_ids']})==6
        assert len(s['dispatch'])==12
    assert plan['input_tokens_max']==786432 and plan['completion_tokens_max']==1152000
    assert not pilot.load(new.PACK/'execution_authorization_request.json')['approved']


@pytest.mark.parametrize('field,value',[('approved',False),('keys_rotated',False),('call_cap',12),
    ('run_id','rename'),('freeze_sha256','old'),('entry_sha256','old'),('prices_reconfirmed',False),
    ('valid_on','2026-10-09'),('launch_channel','PAID_DSH_CONTROLLER'),('authorization_source',None)])
def test_gate_before_credentials_output_or_requests(monkeypatch,field,value):
    auth=approval(); auth[field]=value
    monkeypatch.setattr(providers.ChatProvider,'_resolve_key',lambda *a:pytest.fail('credential read'))
    monkeypatch.setattr(providers.urllib.request,'urlopen',lambda *a,**kw:pytest.fail('dispatch'))
    with pytest.raises(ValueError): new.run_segment(1,auth)
    assert not new.OUTPUT.exists()


def test_complete_four_segments_one_root_capture_and_readonly_replay(monkeypatch):
    calls=transport(monkeypatch)
    for n in range(1,5):
        result=new.run_segment(n,approval())
        assert len(calls)==n*12 and result['calls']==n*12
        assert all(v['tasks_assigned']==24 for v in result['score_vector'].values())
        assert all(r['score']['full_pass'] and r['provider_attempts']==1 for r in result['records'])
        with pytest.raises(ValueError,match='NEXT_SEGMENT'): new.run_segment(n,approval())
        review(n)
    assert pilot.load(new.OUTPUT/'summary.json')['status']=='EXECUTED_48'
    assert len({(b['model'],b['messages'][1]['content']) for b in calls})==48
    check_capture(calls)
    events=new.read_events()
    assert sum(e['kind']=='BATCH_STARTED' for e in events)==1
    reserved=new.reservations(events)
    assert [r['batch_index'] for r in reserved]==list(range(1,49))
    projected=new.ledger_projection(events,new.validate())
    assert projected['deepseek']['cost_cny_reserved']=='7.20'
    assert projected['xiaomi']['cost_cny_reserved']=='4.80'
    before={p:p.read_bytes() for p in new.OUTPUT.rglob('*') if p.is_file()}
    monkeypatch.setattr(providers.ChatProvider,'_resolve_key',lambda *a:pytest.fail('credential read'))
    monkeypatch.setattr(providers.urllib.request,'urlopen',lambda *a,**k:pytest.fail('dispatch'))
    assert new.replay()['attempts']==48
    assert before=={p:p.read_bytes() for p in new.OUTPUT.rglob('*') if p.is_file()}


@pytest.mark.parametrize('failure',['partial','json','429','timeout','reset','business','unknown','identity','overbudget','leak'])
def test_failure_keeps_reservation_raw_and_permanent_stop(monkeypatch,failure):
    calls=transport(monkeypatch,failure)
    result=new.run_segment(1,approval())
    assert len(calls)==1 and result['status']=='HARD_STOP' and result['calls']==1
    assert result['budget']['deepseek']['requests_reserved']==1
    assert result['budget']['deepseek']['cost_cny_reserved']=='0.30'
    if failure in ('partial','json','429','business'): assert result['records'][0]['raw_ref']
    if failure=='unknown':
        assert result['budget']['deepseek']['usage_unknown_or_pending']==1
        assert result['score_vector']['deepseek']['input_tokens_reported'] is None
        assert result['score_vector']['deepseek']['cost_reported'] is None
    assert new.replay()['attempts']==1
    monkeypatch.setattr(providers.ChatProvider,'_resolve_key',lambda *a:pytest.fail('credential read'))
    with pytest.raises(ValueError,match='PERMANENTLY_STOPPED'): new.run_segment(2,approval())
    assert len(calls)==1


@pytest.mark.parametrize('failure',['length','research'])
def test_complete_usage_failure_not_retried_or_confused_with_provider_success(monkeypatch,failure):
    calls=transport(monkeypatch,failure)
    result=new.run_segment(1,approval())
    assert len(calls)==12 and result['calls']==12
    if failure=='length':
        assert all(r['provider_failure'] and not r['complete'] for r in result['records'])
        assert all(r['budget_stage']=='COMBINED_TOKEN_EXHAUSTION_STAGE_UNKNOWN' for r in result['records'])
    else: assert all(r['complete'] and not r['score']['full_pass'] for r in result['records'])
    assert new.replay()['attempts']==12


def test_anomaly_review_and_confirmed_blocker_stop(monkeypatch):
    calls=transport(monkeypatch)
    result=new.run_segment(1,approval())
    assert result['status']=='ANOMALY_REVIEW_REQUIRED'
    with pytest.raises(ValueError,match='ANOMALY_REVIEW_REQUIRED'): new.run_segment(2,approval())
    result=new.review_segment(1,'stop','Synthetic confirmed blocking example; do not dispatch remaining tasks.',approval())
    assert result['status']=='HARD_STOP'
    with pytest.raises(ValueError,match='PERMANENTLY_STOPPED'): new.run_segment(2,approval())
    assert len(calls)==12


def test_interruption_after_reservation_never_restarts(monkeypatch):
    calls=[]
    def interrupted(request,timeout): calls.append(request); raise KeyboardInterrupt()
    monkeypatch.setattr(providers.urllib.request,'urlopen',interrupted)
    with pytest.raises(KeyboardInterrupt): new.run_segment(1,approval())
    result=pilot.load(new.OUTPUT/'summary.json')
    assert result['calls']==1 and result['budget']['deepseek']['usage_unknown_or_pending']==1
    assert new.replay()['attempts']==1
    with pytest.raises(ValueError): new.run_segment(1,approval())
    with pytest.raises(ValueError): new.run_segment(2,approval())
    assert len(calls)==1


def test_no_skip_order_or_repeat_claim(monkeypatch):
    calls=transport(monkeypatch)
    with pytest.raises(ValueError,match='FIRST_SEGMENT'): new.run_segment(2,approval())
    new.run_segment(1,approval()); review(1)
    with pytest.raises(ValueError,match='NEXT_SEGMENT'): new.run_segment(3,approval())
    assert len(calls)==12


@pytest.mark.parametrize('name',['summary.json','trace.json','raw_01.json','result.json','attempt_01.json'])
def test_tamper_stops_before_next_credentials(monkeypatch,name):
    calls=transport(monkeypatch)
    new.run_segment(1,approval()); review(1)
    path=new.OUTPUT/name if name in ('summary.json','trace.json') else new.OUTPUT/(new.BATCH+'_S1')/name
    if name=='summary.json':
        value=pilot.load(path); value['budget']['deepseek']['cost_cny_reserved']='0'; pilot.save(path,value)
    else: path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(providers.ChatProvider,'_resolve_key',lambda *a:pytest.fail('credential read'))
    with pytest.raises(ValueError): new.run_segment(2,approval())
    assert len(calls)==12


def test_default_operation_is_offline(monkeypatch):
    monkeypatch.setattr(providers.ChatProvider,'_resolve_key',lambda *a:pytest.fail('credential read'))
    monkeypatch.setattr(providers.urllib.request,'urlopen',lambda *a,**kw:pytest.fail('dispatch'))
    new.main([])
    assert not new.OUTPUT.exists()


@pytest.mark.parametrize('dimension',['requests','input','output','cost','duplicate','wall'])
def test_cumulative_denial_is_atomic_and_retained(dimension):
    plan=new.validate(); segment=plan['segments'][0]
    store=TraceStore(new.OUTPUT/'trace.sqlite')
    prior=dict(index=1,provider_id='deepseek',task_id='synthetic-other-task',candidate_trials=0,
        input_tokens=0,output_tokens=0,cost_cny='0.00')
    if dimension=='requests':
        for i in range(24): store.append('prior:'+str(i),'PILOT_RESERVED',dict(prior,task_id='synthetic-'+str(i)))
    elif dimension=='wall':
        store.append('prior:wall','SEGMENT_FINISHED',dict(dispatch_wall_milliseconds=14400000))
    else:
        if dimension=='input': prior['input_tokens']=plan['providers']['deepseek']['input_tokens_max']
        if dimension=='output': prior['output_tokens']=plan['providers']['deepseek']['completion_tokens_max']
        if dimension=='cost': prior['cost_cny']='7.20'
        if dimension=='duplicate': prior['task_id']=segment['dispatch'][0]['task_id']
        store.append('prior','PILOT_RESERVED',prior)
    before=len(new.reservations(store.read()))
    with new.segment_bindings(plan,segment,approval()):
        shared=pilot.TraceStore(new.OUTPUT/'unused.sqlite')
        payload=dict(index=1,**segment['dispatch'][0],candidate_trials=0,input_tokens=16384,output_tokens=24000,cost_cny='0.30')
        with pytest.raises(ValueError,match='CUMULATIVE_BUDGET_DENIED'):
            shared.append('reserve:1','PILOT_RESERVED',payload)
    assert len(new.reservations(store.read()))==before
    assert store.read()[-1]['kind']=='BATCH_BUDGET_DENIED'


def test_second_segment_failure_keeps_first_segment_budget(monkeypatch):
    calls=transport(monkeypatch)
    new.run_segment(1,approval()); review(1)
    failed=transport(monkeypatch,'unknown')
    result=new.run_segment(2,approval())
    assert len(calls)==12 and len(failed)==1 and result['calls']==13
    assert result['budget']['deepseek']['requests_reserved']==7
    assert result['budget']['xiaomi']['requests_reserved']==6
    assert result['budget']['deepseek']['cost_cny_reserved']=='2.10'
    assert new.replay()['attempts']==13
    with pytest.raises(ValueError,match='PERMANENTLY_STOPPED'): new.run_segment(3,approval())


def test_date_expiry_mid_segment_denies_next_request(monkeypatch):
    calls=transport(monkeypatch)
    original=providers.urllib.request.urlopen
    def expire(request,timeout):
        response=original(request,timeout)
        monkeypatch.setattr(new.policy.base,'utc_now',lambda:datetime(2026,10,11,tzinfo=timezone.utc))
        return response
    monkeypatch.setattr(providers.urllib.request,'urlopen',expire)
    with pytest.raises(ValueError,match='DATE_BOUND_AUTHORIZATION_EXPIRED'): new.run_segment(1,approval())
    assert len(calls)==1
    assert new.replay()['attempts']==1
    assert any(e['kind']=='BATCH_BUDGET_DENIED' and e['payload']['reason']=='DATE_BOUND_AUTHORIZATION_EXPIRED' for e in new.read_events())
