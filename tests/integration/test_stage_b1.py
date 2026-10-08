"""Fixed synthetic engineering operation; zero strategy/Agent search."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'env'))
from test_pit import record,dataset
from test_daily import fixture,order

from quant_rsi.contracts.condition import BenchmarkCondition,AgentBenchmarkRun,load_decisions,RESOURCE_DIMENSIONS
from quant_rsi.contracts.research import ConceptMapping,Hypothesis,ScientificSearchFamily,ExperimentSpec,Candidate,Evidence
from quant_rsi.contracts.manifest import RunManifest
from quant_rsi.data.pit import PITView,canonical_bytes
from quant_rsi.env.daily import simulate
from quant_rsi.eval.replay import replay,installed_code_bundle,dependency_lock,TOOL_VERSIONS
from quant_rsi.ledger.budget import SearchBudget
from quant_rsi.ledger.store import TraceStore


def build_bundle(root,randomness='fixed_seed_deterministic'):
    root.mkdir(parents=True)
    rows=[record()]+[record(kind=k,value=v) for k,v in [('ST',False),('board','MAIN'),('venue','X'),('suspended',False),('lagged_ADV','100000')]]
    rows.append(record(kind='ST',value=True,revision='r2',available='2000-02-01T00:00:00Z'))
    task,data,snapshot,artifacts=dataset(rows)
    view=PITView(task,data,snapshot,artifacts.__getitem__)
    _,_,environment=fixture()
    environment['orders']=[order(3,'buy',300),order(4,'sell',100)]
    environment['bars'][environment['sessions'][2]]['AAA'].pop('certified_open_volume')
    seed=7 if randomness=='fixed_seed_deterministic' else None
    operation={'operation':'synthetic-daily-v1','comparison':'exact','randomness':randomness,'seed':seed,'environment':environment}
    artifacts.update({'environment-input.json':canonical_bytes(operation),'prompt.txt':b'fixed synthetic signal fixture; no Agent',
        'code-tree.json':canonical_bytes(installed_code_bundle()),'dependencies.json':canonical_bytes(dependency_lock()),
        'DATA-'+data.content_hash():data.to_json().encode(),'SNAPSHOT-'+snapshot.content_hash():snapshot.to_json().encode()})
    condition=BenchmarkCondition(task);store=TraceStore(root/'trace.sqlite');budget=SearchBudget(store)
    mapping=ConceptMapping('MAP-B1','engineering conformance','fixed synthetic values','fixture',('FEAT-B1',))
    hypothesis=Hypothesis('HYP-B1','CLAIM-B1','fixed environment preserves conformance','any invariant fails','MAP-B1')
    family=ScientificSearchFamily('FAM-B1','CLAIM-B1','synthetic engineering fixture only')
    budget.register_concept(mapping);budget.register_hypothesis(hypothesis);budget.register_family(family)
    run=AgentBenchmarkRun('RUN-B1','FAM-B1',condition.condition_hash,'fixed-local-engineering-operation','B1-v1',
        sha256(artifacts['prompt.txt']).hexdigest(),sha256(artifacts['code-tree.json']).hexdigest(),
        sha256(artifacts['dependencies.json']).hexdigest(),'RUN-B1','2000-01-03T00:00:00Z',provider='synthetic-local')
    budget.register_run(run,condition,decision_snapshot=load_decisions())
    experiment=ExperimentSpec('EXP-B1','HYP-B1',task.task_id,'DATA-'+data.content_hash(),task.cost_model_version,
        task.statistical_protocol_version,'FAM-B1','RUN-B1','2000-01-04T00:00:00Z')
    budget.register_experiment(experiment)
    budget.reserve('RUN-B1','ATT-B1',dict(attempts=1,candidate_trials=1,model_trials=1,**dict.fromkeys(RESOURCE_DIMENSIONS,10)),scientific_variant_id='VAR-engineering',experiment_id='EXP-B1')
    result=simulate(task,view,environment)
    artifacts['result.json']=canonical_bytes(result);h=sha256(artifacts['result.json']).hexdigest()
    budget.record_output('ATT-B1','CAN-B1','result.json',h)
    candidate=Candidate('CAN-B1','EXP-B1','FAM-B1','RUN-B1','result.json',h,run.code_hash,'ATT-B1')
    evidence=Evidence('EVI-B1','EXP-B1','CAN-B1',{'synthetic_final_nav':float(result['ledger'][-1]['nav'])},'result.json',h)
    budget.settle('ATT-B1','SUCCEEDED',dict.fromkeys(RESOURCE_DIMENSIONS,1),artifact_hashes={'result.json':h})
    manifest=RunManifest('MAN-B1','RUN-B1',run.content_digest(),'ATT-B1',task.task_id,task.content_digest(),
        'condition:'+condition.condition_hash,condition.condition_hash,'FAM-B1','DATA-'+data.content_hash(),'SNAPSHOT-'+snapshot.content_hash(),
        {'CAN-B1':candidate.content_digest()},{'EVI-B1':evidence.content_digest()},
        {k:sha256(v).hexdigest() for k,v in artifacts.items() if k!='result.json'},{'result.json':h},
        'prompt.txt','code-tree.json','dependencies.json',sys.version,TOOL_VERSIONS,randomness,seed,
        {e['event_id']:e['event_hash'] for e in store.read()},datetime.now(timezone.utc).isoformat())
    artifacts.update({'CAN-B1':canonical_bytes(candidate.to_dict()),'EVI-B1':canonical_bytes(evidence.to_dict())})
    return dict(manifest=manifest,store=store,artifacts=artifacts,result=result,view=view,task=task,data=data,snapshot=snapshot,budget=budget,experiment=experiment)


def run_replay(bundle,manifest=None):
    m=bundle['manifest'] if manifest is None else manifest
    return replay(m,expected_manifest_digest=m.manifest_digest,replay_id='REPLAY-B1',trace_store=bundle['store'],resolve_artifact=bundle['artifacts'].__getitem__)


def test_B1_end_to_end_pit_execution_manifest_replay(tmp_path,monkeypatch):
    b=build_bundle(tmp_path/'bundle');before=b['store'].read()
    assert b['view'].state('2000-01-03T16:00:00Z','AAA','ST') is False
    assert b['view'].state('2000-02-01T00:00:00Z','AAA','ST') is True
    assert any(x['status']=='UNCERTAIN' for x in b['result']['decisions'])
    assert all(x['fill_at']>x['order_created_at'] for x in b['result']['decisions'] if x['fill_at'])
    replay_result=run_replay(b)
    assert replay_result['assurance']=='DETERMINISTIC_REPRODUCED'
    assert b['store'].read()==before
    def forbidden():raise AssertionError('historical replay must not load current registry')
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions',forbidden)
    assert run_replay(b)['assurance']=='DETERMINISTIC_REPRODUCED'
    assert b['experiment'].execution_started_at is None
    capture=os.environ.get('QUANT_RSI_B1_CAPTURE_DIR')
    if capture:
        target=Path(capture);target.mkdir(parents=True,exist_ok=False)
        for name,value in [('manifest',b['manifest'].to_dict()),('trace',before),('result',b['result']),('replay',replay_result),
                           ('summary',{'synthetic':True,'scientific_searches':0,'engineering_fixture_candidate_trials':1,
                            'sealed_assurance':'SYNTHETIC_MOCK','formal_G6':'BLOCKED','stage_next_started':False})]:
            (target/(name+'.json')).write_text(json.dumps(value,indent=2),encoding='utf-8')
        (target/'artifact-bytes.json').write_text(json.dumps({k:v.hex() for k,v in b['artifacts'].items()},indent=2),encoding='utf-8')
