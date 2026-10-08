"""A1 synthetic cross-layer provenance; no market/provider execution."""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import pytest

from quant_rsi.contracts.condition import (
    AgentBenchmarkRun, BenchmarkCondition, TaskContract, BUDGET_DIMENSIONS,
    RESOURCE_DIMENSIONS, load_decisions, canonical_hash,
)
from quant_rsi.contracts.data import DataSpec, SnapshotFile, SnapshotManifest
from quant_rsi.contracts.research import (
    Candidate, Evidence, ConceptMapping, Hypothesis, ScientificSearchFamily,
    ExperimentSpec, validate_research_links,
)
from quant_rsi.contracts.manifest import RunManifest
from quant_rsi.ledger.budget import SearchBudget, BudgetDenied
from quant_rsi.ledger.store import TraceStore


def encoded(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def synthetic_flow(root, *, status='SUCCEEDED', extra_run=False):
    root.mkdir(parents=True)
    raw = b'SYNTHETIC raw input\n'
    raw_hash = sha256(raw).hexdigest()
    time = '2000-01-01T00:00:00Z'
    data = DataSpec('SYNTHETIC-source', 'revision-1', raw_hash, time, time, time, time, time, None,
        'UTC', {'value': 'synthetic'}, 'none', 'universe-v1', 'clean-v1', 'pit-v1',
        'available_at_lte_decision_at_and_membership_effective_at_decision',
        'choose_latest_revision_available_by_decision_not_latest_download')
    snapshot = SnapshotManifest('synthetic-snapshot', data, [SnapshotFile('raw.txt', raw_hash)])
    (root/'raw.txt').write_bytes(raw)
    snapshot.verify_files(root)
    decisions = load_decisions()
    task = TaskContract(task_id='TASK-A1', task_version='v1', target='synthetic contract check', horizon='1d',
        benchmark_ref='zero', universe_ref='universe-v1', asof_cutoff=time, execution_timing='next synthetic bar',
        data_spec_hash=data.content_hash(), snapshot_hash=snapshot.content_hash(), cleaning_spec_version='clean-v1',
        split_version='split-v1', env_version='env-synthetic', evaluator_version='eval-not-implemented',
        cost_model_version='COST-synthetic', market_rules_version='rules-synthetic', calendar_version='calendar-v1',
        statistical_protocol_version='STAT-deferred', budget_policy_version='0.2',
        decision_registry_hash=canonical_hash(decisions), decision_snapshot_ref='sha256:'+canonical_hash(decisions),
        decision_registry_version=decisions['version'], budget_limits={**dict.fromkeys(BUDGET_DIMENSIONS, 100), 'attempts': 2},
        memory_limit_mb=64, frozen_at='2000-01-02T00:00:00Z', frozen_by='synthetic-custodian')
    condition = BenchmarkCondition(task)
    service = SearchBudget(TraceStore(root/'trace.sqlite'))
    concept = ConceptMapping('MAP-A1', 'synthetic mechanism', 'observable', 'proxy', ('FEATURE-A1',))
    hypothesis = Hypothesis('HYP-A1', 'CLAIM-A1', 'synthetic outcome is positive', 'nonpositive falsifies', concept.concept_mapping_id)
    family = ScientificSearchFamily('FAM-AAA', hypothesis.claim_id, 'synthetic selection')
    service.register_concept(concept)
    service.register_hypothesis(hypothesis)
    service.register_family(family)
    project = Path(__file__).resolve().parents[2]
    code_tree = {p.relative_to(project).as_posix(): p.read_bytes().hex() for p in sorted((project/'src').rglob('*.py'))}
    artifacts = {'prompt.txt': b'Synthetic fixed operation, no provider call',
                 'code-tree.json': encoded(code_tree), 'dependencies.json': encoded({'python':sys.version}),
                 'raw.txt': raw, 'DATA-'+data.content_hash(): data.to_json().encode(),
                 'SNAPSHOT-'+snapshot.content_hash(): snapshot.to_json().encode()}
    run = AgentBenchmarkRun('RUN-AAA', family.scientific_family_id, condition.condition_hash,
        'synthetic-local-operation', 'fixture-v1', sha256(artifacts['prompt.txt']).hexdigest(),
        sha256(artifacts['code-tree.json']).hexdigest(), sha256(artifacts['dependencies.json']).hexdigest(),
        'RUN-AAA', '2000-01-03T00:00:00Z')
    service.register_run(run, condition, decision_snapshot=decisions)
    experiment = ExperimentSpec('EXP-AAA', hypothesis.hypothesis_id, task.task_id, 'DATA-'+data.content_hash(),
        task.cost_model_version, task.statistical_protocol_version, family.scientific_family_id,
        run.benchmark_run_id, '2000-01-04T00:00:00Z')
    service.register_experiment(experiment)
    envelope = dict(attempts=1, candidate_trials=1, model_trials=1, **dict.fromkeys(RESOURCE_DIMENSIONS, 10))
    service.reserve(run.benchmark_run_id, 'ATT-AAA', envelope, scientific_variant_id='VAR-AAA', experiment_id=experiment.experiment_id)
    artifacts['result.json'] = encoded({'synthetic_metric': -1, 'status':status})
    output_hash = sha256(artifacts['result.json']).hexdigest()
    kind = 'STRATEGY' if status == 'SUCCEEDED' else 'FAILURE_DIAGNOSTIC'
    service.record_output('ATT-AAA', 'CAN-AAA', 'result.json', output_hash, kind=kind)
    candidate = Candidate('CAN-AAA', experiment.experiment_id, family.scientific_family_id,
        run.benchmark_run_id, 'result.json', output_hash, run.code_hash, 'ATT-AAA', kind)
    evidence = Evidence('EVI-AAA', experiment.experiment_id, candidate.candidate_id,
        {'synthetic_metric': -1 if status == 'SUCCEEDED' else None}, 'result.json', output_hash,
        kind='SCIENTIFIC_FAILURE' if status == 'SUCCEEDED' else 'INFRASTRUCTURE_FAILURE')
    inputs = {ref:sha256(value).hexdigest() for ref,value in artifacts.items() if ref != 'result.json'}
    manifest = RunManifest('MAN-A1-draft', run.benchmark_run_id, run.content_digest(), candidate.attempt_id,
        task.task_id, task.content_digest(), 'condition:'+condition.condition_hash, condition.condition_hash,
        family.scientific_family_id, 'DATA-'+data.content_hash(), 'SNAPSHOT-'+snapshot.content_hash(),
        {candidate.candidate_id:candidate.content_digest()}, {evidence.evidence_id:evidence.content_digest()},
        inputs, {'result.json':output_hash}, 'prompt.txt', 'code-tree.json', 'dependencies.json', sys.version,
        {'synthetic_operation':'v1'}, 'fixed_seed_deterministic', 0,
        {e['event_id']:e['event_hash'] for e in service.store.read()}, datetime.now(timezone.utc).isoformat())
    service.settle('ATT-AAA', status, dict.fromkeys(RESOURCE_DIMENSIONS, 1), artifact_hashes={'result.json':output_hash},
        failure=None if status == 'SUCCEEDED' else 'synthetic infrastructure interruption')
    # The pre-terminal object is only a draft. Freeze a separate completed
    # manifest digest that binds the terminal event; never overwrite the draft.
    manifest = replace(manifest, manifest_id='MAN-A1', trace_refs={e['event_id']:e['event_hash'] for e in service.store.read()},
                       created_at=datetime.now(timezone.utc).isoformat())
    if extra_run:
        second_family = replace(family, scientific_family_id='FAM-BBB')
        service.register_family(second_family)
        second_run = replace(run, benchmark_run_id='RUN-BBB', budget_root_run_id='RUN-BBB', scientific_family_id='FAM-BBB', agent_model='synthetic-B')
        service.register_run(second_run, condition, decision_snapshot=decisions)
        second_exp = replace(experiment, experiment_id='EXP-BBB', benchmark_run_id='RUN-BBB', scientific_family_id='FAM-BBB')
        service.register_experiment(second_exp)
        service.reserve('RUN-BBB', 'ATT-BBB', envelope, scientific_variant_id='VAR-BBB', experiment_id='EXP-BBB')
        service.settle('ATT-BBB', 'FAILED', dict.fromkeys(RESOURCE_DIMENSIONS, 1), failure='preserved infrastructure failure')
        service.register_family(replace(family, scientific_family_id='FAM-pooled', parent_family_ids=('FAM-AAA','FAM-BBB')))
    kwargs = dict(trace_store=service.store, condition=condition, run=run, data_spec=data, snapshot=snapshot,
                  candidates=[candidate], evidence=[evidence], resolve_artifact=artifacts.__getitem__)
    manifest.verify_bindings(**kwargs)
    return dict(service=service, condition=condition, run=run, experiment=experiment, candidate=candidate,
        evidence=evidence, manifest=manifest, artifacts=artifacts, kwargs=kwargs, concept=concept,
        hypothesis=hypothesis, family=family, decisions=decisions, envelope=envelope)


@pytest.fixture
def flow(tmp_path):
    return synthetic_flow(tmp_path/'flow')


def research_args(flow):
    return dict(concept_mappings=[flow['concept']], hypotheses=[flow['hypothesis']], families=[flow['family']],
        experiments=[flow['experiment']], candidates=[flow['candidate']], evidence=[flow['evidence']],
        benchmark_run_ids=[flow['run'].benchmark_run_id], trace_store=flow['service'].store)


def test_A1_complete_synthetic_chain_and_manifest_roundtrip(flow, monkeypatch):
    m = flow['manifest']
    restored = RunManifest.from_dict(json.loads(json.dumps(m.to_dict())))
    assert restored == m and restored.manifest_digest == m.manifest_digest
    restored.verify_bindings(**flow['kwargs'])
    validate_research_links(**research_args(flow))
    assert flow['experiment'].execution_started_at is None
    assert flow['service'].capability_accounting('RUN-AAA')['usage']['attempts'] == 1
    # Historical verification needs no current registry or dispatch authorization.
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: (_ for _ in ()).throw(AssertionError('current registry read')))
    restored.verify_bindings(**flow['kwargs'])
    capture = os.environ.get('QUANT_RSI_A1_CAPTURE_DIR')
    if capture:
        destination = Path(capture); destination.mkdir(parents=True, exist_ok=False)
        for name, obj in [('manifest', m.to_dict()), ('trace', flow['service'].store.read()),
                          ('condition', flow['condition'].to_dict()), ('candidate', flow['candidate'].to_dict()),
                          ('evidence', flow['evidence'].to_dict()), ('experiment', flow['experiment'].to_dict()),
                          ('summary', {'status':'PASS','synthetic':True,'stage_B_started':False,
                                       'sealed_assurance':'NOT_IMPLEMENTED','manifest_digest':m.manifest_digest})]:
            (destination/(name+'.json')).write_text(json.dumps(obj,indent=2),encoding='utf-8')
        (destination/'artifact-bytes.json').write_text(json.dumps({k:v.hex() for k,v in flow['artifacts'].items()},indent=2))


@pytest.mark.parametrize('changes', [
    {'attempt_id':'ATT-missing'}, {'experiment_id':'EXP-other'}, {'benchmark_run_id':'RUN-other'},
    {'scientific_family_id':'FAM-other'}, {'artifact_hash':'0'*64}, {'artifact_ref':'other.json'}, {'code_hash':'0'*64},
])
def test_A1_wrong_candidate_binding_blocked(flow, changes):
    args=research_args(flow); args['candidates']=[replace(flow['candidate'],**changes)]
    with pytest.raises(ValueError): validate_research_links(**args)


@pytest.mark.parametrize('changes', [{'candidate_id':'CAN-other'}, {'source_artifact_ref':'other.json'}, {'source_artifact_hash':'0'*64}])
def test_A1_wrong_evidence_binding_blocked(flow, changes):
    args=research_args(flow); args['evidence']=[replace(flow['evidence'],**changes)]
    with pytest.raises(ValueError): validate_research_links(**args)


@pytest.mark.parametrize('field,value',[('experiment_id','EXP-other'),('benchmark_run_id','RUN-other'),('scientific_family_id','FAM-other')])
def test_A1_existing_attempt_belongs_to_other_owner(flow,tmp_path,field,value):
    # Rebuild a structurally valid chain with an inconsistent attempt payload;
    # admission must reject ownership mismatch even with valid event hashes.
    trace=TraceStore(tmp_path/'other-owner.sqlite')
    for event in flow['service'].store.read():
        payload=dict(event['payload'])
        if event['kind']=='ATTEMPT_STARTED': payload[field]=value
        trace.append(event['event_id'],event['kind'],payload)
    with pytest.raises(ValueError,match='mismatch'):
        validate_research_links(**dict(research_args(flow),trace_store=trace))


def test_A1_no_start_and_no_preregistration_mutation_shortcut(flow, tmp_path):
    args=research_args(flow)
    empty=TraceStore(tmp_path/'empty.sqlite')
    for e in flow['service'].store.read():
        if e['kind'] != 'ATTEMPT_STARTED': empty.append(e['event_id'],e['kind'],e['payload'])
    with pytest.raises(ValueError, match='STARTED'): validate_research_links(**dict(args,trace_store=empty))
    args['experiments']=[replace(flow['experiment'],execution_started_at=datetime.now(timezone.utc).isoformat())]
    with pytest.raises(ValueError, match='preregistration'): validate_research_links(**args)


@pytest.mark.parametrize('status',['FAILED','ABORTED','TIMEOUT','CANCELLED','UNKNOWN_TERMINATION'])
def test_A1_failures_preserve_diagnostic_evidence_not_strategy(tmp_path,status):
    f=synthetic_flow(tmp_path/status,status=status)
    validate_research_links(**research_args(f))
    args=research_args(f); args['candidates']=[replace(f['candidate'],kind='STRATEGY')]
    with pytest.raises(ValueError): validate_research_links(**args)
    with pytest.raises(ValueError): replace(f['evidence'],metrics={'fake_return':1})
    assert f['service'].scientific_accounting('FAM-AAA')['attempt_count']==1


def test_A1_retry_has_distinct_candidate_attempt_and_no_denominator_reset(tmp_path):
    f=synthetic_flow(tmp_path/'retry',status='FAILED')
    b=f['service']; e={**f['envelope'],'candidate_trials':0,'model_trials':0,'retries':1}
    b.reserve('RUN-AAA','ATT-retry',e,scientific_variant_id='VAR-AAA',experiment_id='EXP-AAA',retry_of='ATT-AAA')
    b.record_output('ATT-retry','CAN-retry','retry.json','f'*64)
    b.settle('ATT-retry','SUCCEEDED',dict.fromkeys(RESOURCE_DIMENSIONS,1),artifact_hashes={'retry.json':'f'*64})
    candidate=replace(f['candidate'],candidate_id='CAN-retry',attempt_id='ATT-retry',artifact_ref='retry.json',artifact_hash='f'*64,kind='STRATEGY')
    evidence=Evidence('EVI-retry','EXP-AAA','CAN-retry',{'synthetic_metric':0},'retry.json','f'*64)
    args=research_args(f); args['candidates'].append(candidate); args['evidence'].append(evidence)
    validate_research_links(**args)
    wrong=replace(f['evidence'],candidate_id='CAN-retry')
    with pytest.raises(ValueError,match='source artifact'):
        validate_research_links(**dict(args,evidence=[wrong]))
    assert b.scientific_accounting('FAM-AAA')['attempt_count']==2
    assert b.scientific_accounting('FAM-AAA')['candidate_variant_count']==1
    assert b.capability_accounting('RUN-AAA')['usage']['retries']==1
    with pytest.raises(BudgetDenied): b.reserve('RUN-AAA','ATT-third',e,scientific_variant_id='VAR-AAA',experiment_id='EXP-AAA',retry_of='ATT-AAA')


@pytest.mark.parametrize('field',['code_hash','dependency_hash','prompt_hash','condition_hash'])
def test_A1_manifest_canonical_run_tampering(flow,field):
    kwargs=dict(flow['kwargs'],run=replace(flow['run'],**{field:'0'*64}))
    with pytest.raises(ValueError): flow['manifest'].verify_bindings(**kwargs)


@pytest.mark.parametrize('ref',['prompt.txt','code-tree.json','dependencies.json','raw.txt','result.json'])
def test_A1_manifest_artifact_bytes_tampering(flow,ref):
    flow['artifacts'][ref]=b'tampered'
    with pytest.raises(ValueError,match='bytes/hash'): flow['manifest'].verify_bindings(**flow['kwargs'])


@pytest.mark.parametrize('field,value',[('condition_hash','0'*64),('attempt_id','ATT-other'),
    ('benchmark_run_id','RUN-other'),('scientific_family_id','FAM-other'),('task_hash','0'*64)])
def test_A1_manifest_identity_mismatch(flow,field,value):
    with pytest.raises(ValueError): replace(flow['manifest'],**{field:value}).verify_bindings(**flow['kwargs'])


def test_A1_manifest_required_provenance_and_randomness_fail_closed(flow):
    for field in flow['manifest'].to_dict():
        value=flow['manifest'].to_dict(); value.pop(field)
        with pytest.raises(ValueError): RunManifest.from_dict(value)
    m=replace(flow['manifest'],randomness='provider_randomness_unknown',seed=None)
    assert RunManifest.from_dict(m.to_dict()).randomness=='provider_randomness_unknown'
    with pytest.raises(ValueError): replace(m,randomness='fixed_seed_deterministic')
    with pytest.raises(ValueError): replace(m,seed=0)
    for change in ({'output_artifacts':{'wrong.json':'f'*64}}, {'trace_refs':{'missing':'f'*64}},
                   {'input_artifacts':{'other':'f'*64}}, {'candidate_hashes':{'CAN-AAA':'f'*64}}):
        with pytest.raises(ValueError): replace(m,**change).verify_bindings(**flow['kwargs'])
    inputs=dict(m.input_artifacts); del inputs['raw.txt']
    with pytest.raises(ValueError,match='snapshot file'):
        replace(m,input_artifacts=inputs).verify_bindings(**flow['kwargs'])


@pytest.mark.parametrize('revocation',['mode','authorized_work_items'])
def test_A1_registry_upgrade_controls_new_dispatch_without_invalidating_history(flow, monkeypatch, revocation):
    from copy import deepcopy
    current=deepcopy(flow['decisions']); current['version']='next-version'
    original=current['activation']['stage_A'][revocation]
    current['activation']['stage_A'][revocation]='DISABLED' if revocation=='mode' else []
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions',lambda:current)
    flow['manifest'].verify_bindings(**flow['kwargs'])
    b=flow['service']
    with pytest.raises(ValueError,match='not authorized'):
        b.reserve('RUN-AAA','ATT-next',dict(attempts=1,**dict.fromkeys(RESOURCE_DIMENSIONS,0)))
    assert b.capability_accounting('RUN-AAA')['usage']['attempts']==1
    current['activation']['stage_A'][revocation]=original
    b.reserve('RUN-AAA','ATT-next',dict(attempts=1,**dict.fromkeys(RESOURCE_DIMENSIONS,0)))
    assert b.capability_accounting('RUN-AAA')['usage']['attempts']==2
    assert flow['condition'].task.decision_registry_version != current['version']


def test_A1_crash_after_output_never_loses_failure_or_releases_budget(flow):
    b=flow['service']
    b.reserve('RUN-AAA','ATT-crash',flow['envelope'],scientific_variant_id='VAR-crash',experiment_id='EXP-AAA')
    b.record_output('ATT-crash','CAN-crash','partial.json','f'*64)
    assert b.recover_incomplete()==['ATT-crash']
    terminal=next(e['payload'] for e in b.store.read() if e['event_id']=='settle:ATT-crash')
    assert terminal['artifact_hashes']=={'partial.json':'f'*64}
    assert terminal['status']=='UNKNOWN_TERMINATION'
    assert b.capability_accounting('RUN-AAA')['blocked'] is True
    args=research_args(flow)
    args['candidates']=[replace(flow['candidate'],candidate_id='CAN-crash',attempt_id='ATT-crash',artifact_ref='partial.json',artifact_hash='f'*64)]
    args['evidence']=[]
    with pytest.raises(ValueError,match='failed attempt'): validate_research_links(**args)


def test_A1_critic_01_second_candidate_cannot_escape_denominator(flow):
    b=flow['service']
    b.reserve('RUN-AAA','ATT-multi',flow['envelope'],scientific_variant_id='VAR-multi',experiment_id='EXP-AAA')
    first=b.record_output('ATT-multi','CAN-one','one.json','f'*64)
    assert b.record_output('ATT-multi','CAN-one','one.json','f'*64)==first
    with pytest.raises(ValueError,match='one candidate'):
        b.record_output('ATT-multi','CAN-two','two.json','e'*64)
    outputs=[e for e in b.store.read() if e['kind']=='ATTEMPT_OUTPUT' and e['payload']['attempt_id']=='ATT-multi']
    assert len(outputs)==1 and outputs[0]==first


def test_A1_critic_02_completed_manifest_must_bind_terminal_hash(flow):
    m=flow['manifest']; refs=dict(m.trace_refs); refs.pop('settle:ATT-AAA',None)
    with pytest.raises(ValueError,match='trace references'):
        replace(m,trace_refs=refs).verify_bindings(**flow['kwargs'])
    refs['settle:ATT-AAA']='f'*64
    with pytest.raises(ValueError,match='trace event'):
        replace(m,trace_refs=refs).verify_bindings(**flow['kwargs'])
