"""Four segments of one frozen 24x2 batch; offline validation by default.

Reuses the frozen serial pilot transport, failure capture, scores and reservation
events. All segments write to one existing TraceStore, without a second ledger.
"""
import argparse
import copy
import json
import os
import sqlite3
import time
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from quant_rsi.harness import public_contract_023 as bundle
from quant_rsi.harness import compatibility_pilot as pilot, compatibility_pilot_023 as policy
from quant_rsi.harness.comparison import score_vector
from quant_rsi.ledger.store import TraceStore, Anchor, _read, verify_events

PACK = bundle.DIRECTORY
FREEZE = PACK/'execution_freeze.json'
ENTRY = Path(__file__)
BATCH = 'TRACK_A_V023_STATIC_24X2_001'
OUTPUT = bundle.ROOT/'benchmark/capability_public/runs/segmented_v023'/BATCH
LAUNCH = 'USER_OPERATED_TERMINAL_NO_PAID_CONTROLLER'


def make_plan():
    bundle.verify()
    inherited = pilot.load(policy.FREEZE)
    suite = bundle.oracle.suite_fixtures('0.2')
    groups = {d['id']: [] for d in suite['capability_dimensions']}
    for tid in suite['task_order']:
        groups[suite['tasks'][tid]['primary_dimension']].append(tid)
    segments = [dict(number=i+1, task_ids=[g[i] for g in groups.values()], calls=12)
                for i in range(4)]
    for segment in segments:
        segment['dispatch']=[dict(provider_id=pid,task_id=tid) for i,tid in enumerate(segment['task_ids'])
            for pid in (['deepseek','xiaomi'] if i%2==0 else ['xiaomi','deepseek'])]
    plan = copy.deepcopy(inherited)
    plan.update(run_id=BATCH, run_kind='TRACK_A_V023_STATIC_24X2_SEGMENTED', calls=48,
        task_ids=suite['task_order'], segments=segments, source_cluster_count=10,
        input_tokens_max=48*16384, completion_tokens_max=48*24000,
        money_caps_cny={'deepseek':'7.20','xiaomi':'4.80'},total_money_cap_cny='12.00',
        wall_seconds=3600, cumulative_dispatch_wall_seconds=14400,
        actual_entry='python -B -m quant_rsi.harness.segmented_comparison_023',
        batch_rule='One 48-call root. Four declared segments, not four new pilots. No rerun or rename.',
        derived_from=dict(prompt_freeze_sha256=bundle.verify(),prior_transport_freeze_sha256=bundle.digest(policy.FREEZE.read_bytes())),
        engineering_budget=dict(max_test_commands=12,max_complete_mock_48_batches=8,real_calls=0),
        pricing_sources=dict(verified_on='2026-10-10',currency='CNY',
            deepseek='https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
            xiaomi='https://mimo.mi.com/docs/en-US/price/pay-as-you-go',
            verification_note='Both official pricing pages retrieved, not model API requests. Peak/all-cache-miss bound; no settled invoice claim.'),
        continuation_rule='Only next declared segment after complete receipt and anomaly review. Never restart an interrupted/failed segment.',
        remaining_scope='STATIC_DIAGNOSTIC only; no Workflow, CP, Judge or Hidden execution.',
        price_reconfirmation_policy='Authorization must affirm published rates at or below frozen peak rates on its UTC valid_on date. All four segments must execute that date; later execution needs an explicit renewed authorization, same root/caps.',
        measurement_rule='Anomalies pause admission for offline human review; confirmed blocking defect permanently stops this frozen batch.')
    plan.pop('parent_run',None)
    plan['conditions_not_equivalent']=[s for s in inherited['conditions_not_equivalent'] if not s.startswith('Six public')]
    plan['conditions_not_equivalent'].append('24 public static tasks from 10 source clusters; no formal ranking, sealed or research-agent capability claim.')
    users=pilot.load(PACK/'prompts.json')['user']
    plan['prompt_hashes']={tid:bundle.digest(users[tid].encode()) for tid in plan['task_ids']}
    for pid,config in plan['providers'].items():
        config.update(requests=24,input_tokens_max=24*16384,completion_tokens_max=24*24000,
                      pricing_status='OFFICIAL_CNY_CHECKED_2026_10_10')
    plan['sha256'].update(pilot.load(PACK/'prompt_freeze.json')['sha256'])
    for path in [PACK/n for n in bundle.FILES]+[ENTRY,bundle.ROOT/'tests/test_segmented_comparison_023.py']:
        plan['sha256'][path.relative_to(bundle.ROOT).as_posix()]=bundle.digest(path.read_bytes())
    plan['stop_rules'] += ['Interruption or incomplete segment receipt blocks later dispatch; never refund unknown usage.',
        'Cross-segment request, token, money and active scheduling-window ceilings are cumulative.',
        'No automatic next-segment launch. Review flags cannot be cleared by model score alone.']
    return plan


def prepare():
    raw=bundle.encode(make_plan())
    if FREEZE.exists() and FREEZE.read_bytes()!=raw:
        raise ValueError('PRESERVE_EXISTING_EXECUTION_FREEZE')
    if not FREEZE.exists(): FREEZE.write_bytes(raw)
    auth=dict(approved=False,authorization_source=None,run_id=BATCH,call_cap=48,
        freeze_sha256=bundle.digest(raw),entry_sha256=bundle.digest(ENTRY.read_bytes()),
        money_caps_cny=make_plan()['money_caps_cny'],total_money_cap_cny='12.00',
        launch_channel=LAUNCH,keys_rotated=True,
        key_rotation_source=pilot.load(policy.FREEZE.with_name('authorization_request.json'))['key_rotation_source'],
        prices_reconfirmed=False,valid_on=None,
        instruction='Preparation only. Requires explicit human 48-call approval and date-bound price confirmation. No paid controller.')
    target=PACK/'execution_authorization_request.json'
    if target.exists() and pilot.load(target)!=auth: raise ValueError('PRESERVE_EXISTING_AUTHORIZATION')
    if not target.exists(): target.write_bytes(bundle.encode(auth))
    return validate()


def validate():
    expected=make_plan()
    if FREEZE.read_bytes()!=bundle.encode(expected): raise ValueError('EXECUTION_FREEZE_CHANGED')
    for relative,pin in expected['sha256'].items():
        if bundle.digest((bundle.ROOT/relative).read_bytes())!=pin:
            raise ValueError('EXECUTION_BINDING_CHANGED:'+relative)
    for pid,c in expected['providers'].items():
        rates=c['prices_cny_per_million']
        worst=(Decimal(expected['input_per_call'])*Decimal(rates['input_miss'])+
               Decimal(expected['completion_per_call'])*Decimal(rates['output']))/1000000
        if worst>Decimal(c['worst_cost_cny_per_call']) or 24*Decimal(c['worst_cost_cny_per_call'])>Decimal(expected['money_caps_cny'][pid]):
            raise ValueError('COST_CEILING_INVALID')
    messages=pilot.load(PACK/'prompts.json')
    if any(len((messages['system']+u).encode())+1024>expected['input_per_call'] for u in messages['user'].values()):
        raise ValueError('PROMPT_INPUT_BOUND_EXCEEDED')
    return expected


def check_authorization(plan,auth):
    exact=dict(approved=True,keys_rotated=True,prices_reconfirmed=True,run_id=BATCH,call_cap=48,
        freeze_sha256=bundle.digest(FREEZE.read_bytes()),entry_sha256=bundle.digest(ENTRY.read_bytes()),
        money_caps_cny=plan['money_caps_cny'],total_money_cap_cny=plan['total_money_cap_cny'],launch_channel=LAUNCH)
    if any(auth.get(k)!=v for k,v in exact.items()) or not isinstance(auth.get('authorization_source'),str) or not auth['authorization_source'].strip():
        raise ValueError('NEW_EXPLICIT_48_CALL_AUTHORIZATION_REQUIRED')
    allowed=set(exact)|{'authorization_source','valid_on','key_rotation_source','instruction'}
    if set(auth)-allowed or not pilot.output_safe(bundle.encode(auth)):
        raise ValueError('NON_SENSITIVE_AUTHORIZATION_FIELDS_ONLY')
    if auth.get('valid_on')!=policy.base.utc_now().date().isoformat():
        raise ValueError('DATE_BOUND_PRICE_AUTHORIZATION_REQUIRED')


def read_events():
    with sqlite3.connect((OUTPUT/'trace.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as conn:
        events=_read(conn)
    verify_events(events)
    return events


def reservations(events):
    return [e['payload'] for e in events if e['kind']=='PILOT_RESERVED']


def ledger_projection(events,plan):
    reserved=reservations(events)
    records=[e['payload'] for e in events if e['kind']=='PILOT_ATTEMPT']
    result={}
    for pid in plan['providers']:
        requests=[r for r in reserved if r['provider_id']==pid]
        answers=[r for r in records if r['provider_id']==pid]
        known=[r for r in answers if r['cost_cny_decimal'] is not None]
        result[pid]=dict(requests_reserved=len(requests),input_tokens_reserved=sum(r['input_tokens'] for r in requests),
            completion_tokens_reserved=sum(r['output_tokens'] for r in requests),
            cost_cny_reserved=str(sum((Decimal(r['cost_cny']) for r in requests),Decimal(0))),
            usage_unknown_or_pending=len(requests)-len(known),
            input_tokens_known=sum(r['input_tokens'] for r in answers if r['input_tokens'] is not None),
            completion_tokens_known=sum(r['output_tokens'] for r in answers if r['output_tokens'] is not None),
            cost_cny_known=str(sum((Decimal(r['cost_cny_decimal']) for r in known),Decimal(0))),
            invoice_cost='UNKNOWN')
    return result


@contextmanager
def segment_bindings(plan,segment,auth):
    started=time.monotonic()
    with policy.bindings():
        observed_class=pilot.TraceStore
        class SharedTrace(observed_class):
            def __init__(self,path): super().__init__(OUTPUT/'trace.sqlite')
            def append(self,event_id,kind,payload):
                prefix='S'+str(segment['number'])+':'
                payload.update(batch_id=BATCH,segment=segment['number'])
                if kind=='PILOT_RESERVED':
                    if auth['valid_on']!=policy.base.utc_now().date().isoformat():
                        super().append(prefix+'authorization:expired','BATCH_BUDGET_DENIED',
                            dict(reason='DATE_BOUND_AUTHORIZATION_EXPIRED',batch_id=BATCH))
                        raise ValueError('DATE_BOUND_AUTHORIZATION_EXPIRED')
                    denied=False
                    with self.transaction() as tx:
                        old=reservations(tx.events())
                        mine=[r for r in old if r['provider_id']==payload['provider_id']]
                        config=plan['providers'][payload['provider_id']]
                        expected=segment['dispatch'][payload['index']-1]
                        spent=sum(e['payload']['dispatch_wall_milliseconds'] for e in tx.events() if e['kind']=='SEGMENT_FINISHED')
                        denied=(len(old)>=48 or len(mine)>=24 or any(
                            (r['provider_id'],r['task_id'])==(payload['provider_id'],payload['task_id']) for r in old)
                            or sum(r['input_tokens'] for r in mine)+payload['input_tokens']>config['input_tokens_max']
                            or sum(r['output_tokens'] for r in mine)+payload['output_tokens']>config['completion_tokens_max']
                            or sum((Decimal(r['cost_cny']) for r in mine),Decimal(0))+Decimal(payload['cost_cny'])>Decimal(plan['money_caps_cny'][payload['provider_id']])
                            or expected!={k:payload[k] for k in ('provider_id','task_id')}
                            or spent+int((time.monotonic()-started)*1000)+plan['timeout_s']*1000>plan['cumulative_dispatch_wall_seconds']*1000)
                        if denied:
                            tx.append(prefix+'deny:'+event_id,'BATCH_BUDGET_DENIED',dict(batch_id=BATCH,reason='CUMULATIVE_OR_DUPLICATE_REQUEST'))
                        else:
                            payload['batch_index']=len(old)+1
                            return tx.append(prefix+event_id,kind,payload)
                    if denied: raise ValueError('CUMULATIVE_BUDGET_DENIED')
                return super().append(prefix+event_id,kind,payload)
        sub=copy.deepcopy(plan)
        sub.update(task_ids=segment['task_ids'],calls=12,
            prompt_hashes={t:plan['prompt_hashes'][t] for t in segment['task_ids']})
        users=pilot.load(PACK/'prompts.json')['user']
        with ExitStack() as stack:
            for module,name,value in [(pilot,'FREEZE',FREEZE),(policy.base,'FREEZE',FREEZE),
                (pilot,'__file__',str(ENTRY)),(pilot,'TraceStore',SharedTrace),
                (pilot,'validate_freeze',lambda:sub),
                (pilot,'prompts',lambda p:{t:users[t] for t in p['task_ids']}),
                (pilot,'check_authorization',lambda p,a:check_authorization(plan,a))]:
                stack.enter_context(patch.object(module,name,value))
            yield


def snapshot(plan,store,persist=True):
    events=store.read()
    records=[e['payload'] for e in events if e['kind']=='PILOT_ATTEMPT']
    pair=[SimpleNamespace(provider_id=pid,model_id=c['chat_provider']['model_id']) for pid,c in plan['providers'].items()]
    vector=score_vector(records,pair,plan['task_ids'],suite='0.2')
    for pid,entry in vector.items():
        mine=[r for r in records if r['provider_id']==pid]
        entry.update(completion_rate_assigned=sum(r['complete'] for r in mine)/24,
            provider_failure_count=sum(bool(r['provider_failure']) for r in mine),
            provider_failure_rate=sum(bool(r['provider_failure']) for r in mine)/24,
            reason_contract_failures=sum(r['score']['parsed'] and not r['diagnostics']['reason_ok'] for r in mine),
            tokens_complete=all(r['input_tokens'] is not None and r['output_tokens'] is not None for r in mine),
            estimated_cost_complete=all(r['cost_cny_decimal'] is not None for r in mine))
        if not entry['tokens_complete']:
            entry['input_tokens_reported']=entry['output_tokens_reported']=None
        if not entry['estimated_cost_complete']: entry['cost_reported']=None
    ended=[e for e in events if e['kind']=='SEGMENT_FINISHED']
    hard=any(e['kind'] in ('BATCH_HARD_STOP','BATCH_BUDGET_DENIED') for e in events)
    reviewed={e['payload']['segment'] for e in events if e['kind']=='SEGMENT_REVIEWED'}
    pending=bool(ended and ended[-1]['payload']['review_required'] and ended[-1]['payload']['segment'] not in reviewed)
    state='HARD_STOP' if hard else ('ANOMALY_REVIEW_REQUIRED' if pending else ('EXECUTED_48' if len(records)==48 else 'SEGMENT_PAUSED'))
    result=dict(status=state,batch_id=BATCH,labels=['PUBLIC','UNSEALED','PROVISIONAL'],calls=len(reservations(events)),
        records=records,score_vector=vector,budget=ledger_projection(events,plan),segments_finished=len(ended),
        source_cluster_count=10,source_clusters_observed=len({r['source_incident_id'] for r in records}),
        is_formal_model_ranking=False,conditions_not_equivalent=plan['conditions_not_equivalent'],
        confirmed_legal_answer_misjudgments=None,freeze_sha256=bundle.digest(FREEZE.read_bytes()),
        entry_sha256=bundle.digest(ENTRY.read_bytes()),trace_anchor=asdict(store.checkpoint()))
    if persist:
        pilot.save(OUTPUT/'summary.json',result)
        pilot.save(OUTPUT/'trace.json',events)
    return result


def run_segment(number,auth):
    plan=validate()
    check_authorization(plan,auth)
    if type(number) is not int or not 1<=number<=4: raise ValueError('SEGMENT_1_TO_4_REQUIRED')
    if OUTPUT.exists():
        replay()
        events=read_events()
        if any(e['kind'] in ('BATCH_HARD_STOP','BATCH_BUDGET_DENIED') for e in events): raise ValueError('BATCH_PERMANENTLY_STOPPED')
        finished=[e['payload'] for e in events if e['kind']=='SEGMENT_FINISHED']
        if number!=len(finished)+1: raise ValueError('NEXT_SEGMENT_ONLY_NO_RERUN')
        if len([e for e in events if e['kind']=='SEGMENT_CLAIMED'])!=len(finished): raise ValueError('INTERRUPTED_SEGMENT_NO_RESTART')
        if finished and finished[-1]['review_required'] and not any(e['kind']=='SEGMENT_REVIEWED' and e['payload']['segment']==number-1 for e in events):
            raise ValueError('ANOMALY_REVIEW_REQUIRED')
    elif number!=1: raise ValueError('FIRST_SEGMENT_REQUIRED')
    policy.base.require_offpeak_room(plan)
    # Non-sensitive availability only, after all authorization/continuation gates.
    if not all(os.environ.get(c['chat_provider']['api_key_env']) for c in plan['providers'].values()):
        raise ValueError('CREDENTIAL_UNAVAILABLE_NO_DISPATCH')
    if not OUTPUT.exists():
        OUTPUT.mkdir(parents=True,exist_ok=False)
        TraceStore(OUTPUT/'trace.sqlite').append('batch:start','BATCH_STARTED',dict(batch_id=BATCH,
            freeze_sha256=bundle.digest(FREEZE.read_bytes()),entry_sha256=bundle.digest(ENTRY.read_bytes()),authorization=auth))
    store=TraceStore(OUTPUT/'trace.sqlite')
    with store.transaction() as tx:
        if any(e['event_id']=='segment:claim:'+str(number) for e in tx.events()): raise ValueError('SEGMENT_ALREADY_CLAIMED')
        tx.append('segment:claim:'+str(number),'SEGMENT_CLAIMED',dict(segment=number,batch_id=BATCH,
            valid_on=auth['valid_on'],authorization_source=auth['authorization_source'],prices_reconfirmed=True))
    segment=plan['segments'][number-1]
    started=time.monotonic()
    try:
        with segment_bindings(plan,segment,auth):
            result=pilot.run(BATCH+'_S'+str(number),auth,OUTPUT)
        segment_root=OUTPUT/(BATCH+'_S'+str(number))
        result.update(batch_id=BATCH,segment=number,status='SEGMENT_EXECUTED',
            source_cluster_count=len({bundle.oracle.suite_fixtures('0.2')['tasks'][t]['source_incident_id'] for t in segment['task_ids']}))
        for r in result['unattempted']: r['failure_type']='NOT_DISPATCHED'
        pilot.save(segment_root/'result.json',result)
        if result['stop']: store.append('segment:stop:'+str(number),'BATCH_HARD_STOP',dict(segment=number,reason=result['stop']))
        store.append('segment:finished:'+str(number),'SEGMENT_FINISHED',dict(segment=number,calls=result['calls'],
            result_sha256=bundle.digest((segment_root/'result.json').read_bytes()),stop=result['stop'],
            dispatch_wall_milliseconds=int((time.monotonic()-started)*1000),
            review_required=bool(result['anomaly_review']['reasons']),review_flags=result['anomaly_review']['reasons']))
    except BaseException as exc:
        store.append('segment:exception:'+str(number),'BATCH_HARD_STOP',dict(segment=number,reason='EXECUTION_INTERRUPTED',exception_type=type(exc).__name__))
        snapshot(plan,store)
        raise
    return snapshot(plan,store)


def review_segment(number,decision,note,auth):
    plan=validate()
    check_authorization(plan,auth)
    replay()
    events=read_events()
    if any(e['kind'] in ('BATCH_HARD_STOP','BATCH_BUDGET_DENIED') for e in events):
        raise ValueError('BATCH_PERMANENTLY_STOPPED')
    ended=[e['payload'] for e in events if e['kind']=='SEGMENT_FINISHED']
    if not ended or number!=ended[-1]['segment'] or not ended[-1]['review_required'] or decision not in ('continue','stop'):
        raise ValueError('LATEST_FLAGGED_SEGMENT_REVIEW_REQUIRED')
    if not isinstance(note,str) or not note.strip() or not pilot.output_safe(note.encode()): raise ValueError('SAFE_HUMAN_REVIEW_NOTE_REQUIRED')
    if any(e['kind']=='SEGMENT_REVIEWED' and e['payload']['segment']==number for e in events): raise ValueError('REVIEW_ALREADY_RECORDED')
    store=TraceStore(OUTPUT/'trace.sqlite')
    if decision=='stop': store.append('review:stop:'+str(number),'BATCH_HARD_STOP',dict(segment=number,reason='CONFIRMED_MEASUREMENT_BLOCKER',note=note))
    store.append('review:'+str(number),'SEGMENT_REVIEWED',dict(segment=number,decision=decision,note=note,
        qualification='HUMAN_DECLARED_REVIEW_NOT_D08',authorization_source=auth['authorization_source']))
    return snapshot(plan,store)


def replay():
    plan=validate()
    result=pilot.load(OUTPUT/'summary.json')
    events=read_events()
    if asdict(verify_events(events,Anchor(**result['trace_anchor'])))!=result['trace_anchor']:
        raise ValueError('TRACE_ANCHOR_CHANGED')
    def saved_bytes(value):
        return json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True,allow_nan=False).encode()
    if (OUTPUT/'trace.json').read_bytes()!=saved_bytes(events) or result['freeze_sha256']!=bundle.digest(FREEZE.read_bytes()) or result['entry_sha256']!=bundle.digest(ENTRY.read_bytes()):
        raise ValueError('SAVED_TRACE_OR_BINDING_CHANGED')
    started=events[0]['payload']
    if started['batch_id']!=BATCH or started['freeze_sha256']!=result['freeze_sha256']: raise ValueError('BATCH_IDENTITY_CHANGED')
    records=[e['payload'] for e in events if e['kind']=='PILOT_ATTEMPT']
    if records!=result['records'] or result['budget']!=ledger_projection(events,plan): raise ValueError('RECORD_OR_BUDGET_CHANGED')
    if result!=snapshot(plan,SimpleNamespace(read=lambda:events,checkpoint=lambda:verify_events(events)),persist=False):
        raise ValueError('SUMMARY_PROJECTION_CHANGED')
    if (OUTPUT/'summary.json').read_bytes()!=saved_bytes(result): raise ValueError('SUMMARY_BYTES_CHANGED')
    pending=reservations(events)
    schedule=[r for s in plan['segments'] for r in s['dispatch']]
    for index,reserved in enumerate(pending,1):
        if ({k:reserved[k] for k in ('provider_id','task_id')}!=schedule[index-1]
            or reserved['batch_index']!=index or reserved['candidate_trials']!=0
            or reserved['input_tokens']!=plan['input_per_call'] or reserved['output_tokens']!=plan['completion_per_call']
            or Decimal(reserved['cost_cny'])!=Decimal(plan['providers'][reserved['provider_id']]['worst_cost_cny_per_call'])):
            raise ValueError('RESERVATION_SCHEDULE_OR_LIMIT_CHANGED')
    if len({(r['provider_id'],r['task_id']) for r in pending})!=len(pending): raise ValueError('DUPLICATE_REQUEST')
    users=pilot.load(PACK/'prompts.json')
    for event in events:
        if event['kind']=='SEGMENT_FINISHED':
            n=event['payload']['segment']; root=OUTPUT/(BATCH+'_S'+str(n))
            if bundle.digest((root/'result.json').read_bytes())!=event['payload']['result_sha256']: raise ValueError('SEGMENT_RECEIPT_CHANGED')
            if (root/'prompts.json').read_bytes()!=saved_bytes({'system':users['system'],'user':{t:users['user'][t] for t in plan['segments'][n-1]['task_ids']}}):
                raise ValueError('SEGMENT_PROMPT_CHANGED')
    with policy.bindings():
        for event in events:
            if event['kind']!='PILOT_ATTEMPT': continue
            record=event['payload']; number=record['segment']; root=OUTPUT/(BATCH+'_S'+str(number))
            index=int(event['event_id'].split(':')[-1])
            if (root/f'attempt_{index:02d}.json').read_bytes()!=saved_bytes(record): raise ValueError('ATTEMPT_FILE_CHANGED')
            if record['raw_ref']:
                if record['raw_ref']!=f'raw_{index:02d}.json': raise ValueError('RAW_REFERENCE_CHANGED')
                raw=(root/record['raw_ref']).read_bytes()
                if not pilot.output_safe(raw) or bundle.digest(raw)!=record['raw_sha256']: raise ValueError('RAW_BYTES_CHANGED')
                if record['transport_error']:
                    if record['transport_ok'] or record['response_text'] is not None: raise ValueError('FAILED_BYTES_ADMITTED')
                else:
                    envelope=json.loads(raw)
                    content=((envelope.get('choices') or [{}])[0].get('message') or {}).get('content')
                    content=content if isinstance(content,str) and content.strip() else None
                    if content!=record['response_text']: raise ValueError('ENVELOPE_CONTENT_CHANGED')
            score,diagnostics=pilot.score_record(record['task_id'],record['response_text'],record['provider_failure'])
            if (score,diagnostics)!=(record['score'],record['diagnostics']): raise ValueError('SCORE_DRIFT')
    return dict(status='OFFLINE_48_BATCH_REPLAY_VERIFIED',attempts=len(pending),real_calls=0)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--segment',type=int)
    parser.add_argument('--authorization',type=Path)
    parser.add_argument('--replay',action='store_true')
    parser.add_argument('--review-segment',type=int)
    parser.add_argument('--decision',choices=['continue','stop'])
    parser.add_argument('--note')
    args=parser.parse_args(argv)
    if sum([args.prepare,args.segment is not None,args.replay,args.review_segment is not None])>1: parser.error('one operation only')
    if args.segment is not None or args.review_segment is not None:
        if not args.authorization: parser.error('explicit authorization file required')
        auth=pilot.load(args.authorization)
        result=run_segment(args.segment,auth) if args.segment is not None else review_segment(args.review_segment,args.decision,args.note,auth)
    elif args.replay: result=replay()
    else:
        plan=prepare() if args.prepare else validate()
        result=dict(status='OFFLINE_48_BATCH_PREPARED_NOT_AUTHORIZED',real_calls=0,run_id=BATCH,
            freeze_sha256=bundle.digest(FREEZE.read_bytes()),entry_sha256=bundle.digest(ENTRY.read_bytes()),calls=plan['calls'])
    print(json.dumps({k:result[k] for k in ('status','real_calls','calls','attempts','freeze_sha256','entry_sha256') if k in result},indent=2))


if __name__=='__main__': main()
