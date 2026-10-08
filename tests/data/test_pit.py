from dataclasses import replace
from hashlib import sha256
import pytest

from quant_rsi.contracts.data import DataSpec, SnapshotFile, SnapshotManifest
from quant_rsi.contracts.condition import TaskContract, BUDGET_DIMENSIONS, load_decisions, canonical_hash
from quant_rsi.data.pit import PITView, CleaningSpec, fit_cleaner, purged_training_ids, canonical_bytes


def record(entity='AAA', kind='listing', value=True, *, source=None, revision='r1',
           event='2000-01-01T00:00:00Z', available='2000-01-01T00:00:00Z',
           effective='2000-01-01T00:00:00Z', end=None):
    payload=dict(entity=entity,kind=kind,value=value)
    spec=DataSpec(source or entity+'-'+kind,revision,sha256(canonical_bytes(payload)).hexdigest(),
        event,available,available,available,effective,end,'UTC',{'value':'synthetic'},'none','universe-v1',
        'clean-v1','pit-v1','available_at_lte_decision_at_and_membership_effective_at_decision',
        'choose_latest_revision_available_by_decision_not_latest_download')
    return dict(data_spec=spec.to_dict(),**payload)


def dataset(records):
    raw=canonical_bytes(records); digest=sha256(raw).hexdigest()
    data=replace(DataSpec.from_dict(record()['data_spec']),source_id='dataset',raw_artifact_hash=digest)
    snapshot=SnapshotManifest('snapshot',data,[SnapshotFile('rows.json',digest)])
    registry=load_decisions(); h=canonical_hash(registry)
    task=TaskContract(task_id='TASK-pit',task_version='v1',target='synthetic conformance',horizon='1d',
        benchmark_ref='zero',universe_ref='universe-v1',asof_cutoff='2000-01-01T00:00:00Z',
        execution_timing='next synthetic open',data_spec_hash=data.content_hash(),snapshot_hash=snapshot.content_hash(),
        cleaning_spec_version='clean-v1',split_version='split-v1',env_version='env-v1',evaluator_version='eval-synthetic',
        cost_model_version='cost-v1',market_rules_version='rules-v1',calendar_version='calendar-v1',
        statistical_protocol_version='deferred',budget_policy_version='0.2',decision_registry_hash=h,
        budget_limits=dict.fromkeys(BUDGET_DIMENSIONS,10),memory_limit_mb=64,frozen_at='2000-01-02T00:00:00Z',
        frozen_by='fixture',decision_snapshot_ref='sha256:'+h,decision_registry_version=registry['version'])
    artifacts={'rows.json':raw}
    return task,data,snapshot,artifacts


def view(records):
    task,data,snapshot,artifacts=dataset(records)
    return PITView(task,data,snapshot,artifacts.__getitem__),task


def test_revision_availability_effective_and_determinism():
    records=[record(kind='ST',value=False),record(kind='ST',value=True,revision='r2',available='2000-02-01T00:00:00Z')]
    p,_=view(records)
    assert p.state('2000-01-15T00:00:00Z','AAA','ST') is False
    assert p.state('2000-02-01T00:00:00Z','AAA','ST') is True
    assert p.at('2000-01-15T00:00:00Z')==p.at('2000-01-15T00:00:00Z')
    p,_=view([record(),record(revision='r2',available='2000-02-01T00:00:00Z',end='2000-02-01T00:00:00Z')])
    assert p.universe('2000-01-15T00:00:00Z')==('AAA',)
    assert p.universe('2000-02-01T00:00:00Z')==() # do not resurrect the original open interval


def test_historical_universe_delisting_st_industry_index_listing():
    rows=[record('DELISTED',end='2000-03-01T00:00:00Z'),record('NEW',effective='2000-04-01T00:00:00Z')]
    for kind,old,new in [('ST',True,False),('industry','old','new'),('index',True,False)]:
        rows += [record('DELISTED',kind,old),record('DELISTED',kind,new,revision='r2',available='2000-02-01T00:00:00Z')]
    p,_=view(rows)
    assert p.universe('2000-01-15T00:00:00Z')==('DELISTED',)
    assert p.universe('2000-04-01T00:00:00Z')==('NEW',)
    assert p.state('2000-01-15T00:00:00Z','DELISTED','industry')=='old'
    assert p.state('2000-01-15T00:00:00Z','DELISTED','ST') is True
    assert p.state('2000-01-15T00:00:00Z','DELISTED','index') is True


def test_current_membership_replacement_and_data_binding_fail_closed():
    task,data,snapshot,artifacts=dataset([record('DELISTED'),record('NEW',effective='2000-04-01T00:00:00Z')])
    artifacts['rows.json']=canonical_bytes([record('NEW')])
    with pytest.raises(ValueError,match='artifact'):PITView(task,data,snapshot,artifacts.__getitem__)
    with pytest.raises(ValueError):PITView(task,replace(data,source_revision='other'),snapshot,artifacts.__getitem__)


@pytest.mark.parametrize('field,value',[('available_at',None),('available_at','2000-01-01'),('pit_rule','latest'),('revision_rule','final')])
def test_missing_or_ambiguous_availability_rejected(field,value):
    row=record();row['data_spec'][field]=value
    with pytest.raises(ValueError):view([row])


def test_release_timezone_and_ambiguous_revision_tie():
    p,_=view([record(available='2000-01-02T08:00:00+08:00')])
    assert p.at('2000-01-01T23:59:59Z')==()
    assert len(p.at('2000-01-02T00:00:00Z'))==1
    with pytest.raises(ValueError):p.at('2000-01-02')
    p,_=view([record(),record(revision='r2')])
    with pytest.raises(ValueError,match='ambiguous'):p.at('2000-01-02T00:00:00Z')


@pytest.mark.parametrize('transform',['identity','signed_log1p'])
def test_training_only_imputation_scaling_winsorization_future_invariance(transform):
    train=[record(kind='feature',value=v,source='feature-'+str(i),event=f'2000-01-0{i+1}T00:00:00Z') for i,v in enumerate([1,None,3,100])]
    def fitted(future):
        p,t=view(train+[record(kind='feature',value=future,source='future',event='2000-02-01T00:00:00Z',available='2000-02-01T00:00:00Z')])
        return fit_cleaner(p,decision_at='2000-01-05T00:00:00Z',task=t,spec=CleaningSpec('clean-v1',transform,0.1,0.9),training_from='2000-01-01T00:00:00Z',training_to='2000-01-05T00:00:00Z',feature_kind='feature')
    a,b=fitted(1),fitted(10**20)
    assert a==b and a.apply([1,None,3,100])==b.apply([1,None,3,100])
    assert len(a.training_ids)==4
    assert abs(sum(a.apply([1,None,3,100])))<1e-12


def test_purge_embargo_and_information_lag_are_frozen_parameters():
    _,task=view([record()]); labels={str(i):f'2000-01-0{i}T00:00:00Z' for i in range(1,8)}
    result=purged_training_ids(labels,{'4'},task=task,split_version='split-v1',label_horizon_seconds=172800,information_lag_seconds=0,embargo_seconds=86400)
    assert result==('1','2','7')
    with pytest.raises(ValueError):purged_training_ids(labels,{'4'},task=task,split_version='other',label_horizon_seconds=1,information_lag_seconds=0,embargo_seconds=0)
    with pytest.raises(ValueError):purged_training_ids(labels,{'4'},task=task,split_version='split-v1',label_horizon_seconds=None,information_lag_seconds=0,embargo_seconds=0)


def test_critic_01_late_revision_cannot_change_frozen_training_fit():
    base=[record(kind='feature',value=1,source='f1'),record(kind='feature',value=3,source='f2',event='2000-01-02T00:00:00Z')]
    late=record(kind='feature',value=100,source='f1',revision='r2',available='2000-02-01T00:00:00Z')
    def fit(rows):
        p,t=view(rows)
        return fit_cleaner(p,decision_at='2000-02-02T00:00:00Z',task=t,spec=CleaningSpec('clean-v1','identity',0,1),
            training_from='2000-01-01T00:00:00Z',training_to='2000-01-03T00:00:00Z',feature_kind='feature')
    assert fit(base)==fit(base+[late])
