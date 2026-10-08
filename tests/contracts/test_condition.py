from dataclasses import replace
from copy import deepcopy
import json
import pytest

from quant_rsi.contracts.condition import (
    AgentBenchmarkRun, BenchmarkCondition, TaskContract, BUDGET_DIMENSIONS,
    decision_digest, require_activation, validate_run_lineage, canonical_hash, load_decisions,
)


def task(**changes):
    values = dict(task_id='TASK-synthetic', task_version='v1', target='synthetic target',
                  horizon='1d', benchmark_ref='synthetic-zero', universe_ref='synthetic-universe',
                  asof_cutoff='2000-01-01T00:00:00Z', execution_timing='next tradable bar',
                  data_spec_hash='a'*64, snapshot_hash='b'*64, cleaning_spec_version='v1',
                  split_version='v1', env_version='v1', evaluator_version='v1', cost_model_version='v1',
                  market_rules_version='v1', calendar_version='v1', statistical_protocol_version='deferred',
                  budget_policy_version='0.2', decision_registry_hash=decision_digest(),
                  decision_snapshot_ref='sha256:' + decision_digest(),
                  decision_registry_version=load_decisions()['version'],
                  budget_limits=dict.fromkeys(BUDGET_DIMENSIONS, 2), memory_limit_mb=64,
                  frozen_at='2000-01-02T00:00:00Z', frozen_by='synthetic custodian')
    values.update(changes)
    return TaskContract(**values)


def run(identifier='RUN-alpha', **changes):
    values = dict(benchmark_run_id=identifier, scientific_family_id='FAM-shared',
                  condition_hash=BenchmarkCondition(task()).condition_hash,
                  agent_model='synthetic-A', agent_model_version='v1', prompt_hash='c'*64,
                  code_hash='d'*64, dependency_hash='e'*64, budget_root_run_id=identifier,
                  registered_at='2000-01-03T00:00:00Z')
    values.update(changes)
    return AgentBenchmarkRun(**values)


def test_roundtrip_and_nested_immutability():
    for obj in (task(), BenchmarkCondition(task()), run()):
        restored = type(obj).from_dict(json.loads(json.dumps(obj.to_dict())))
        assert restored == obj
        assert restored.content_digest() == obj.content_digest()
        with pytest.raises(ValueError):
            type(obj).from_dict(dict(obj.to_dict(), extra='unfrozen'))
    limits = dict.fromkeys(BUDGET_DIMENSIONS, 2)
    frozen = task(budget_limits=limits)
    limits['attempts'] = 999
    assert frozen.budget_limits['attempts'] == 2
    with pytest.raises(TypeError):
        frozen.budget_limits['attempts'] = 1


@pytest.mark.parametrize('field', ['target', 'horizon', 'benchmark_ref', 'universe_ref', 'task_version',
    'execution_timing', 'cleaning_spec_version', 'split_version', 'env_version', 'evaluator_version',
    'cost_model_version', 'calendar_version', 'market_rules_version', 'statistical_protocol_version', 'budget_policy_version'])
def test_every_frozen_condition_change_changes_digest(field):
    assert BenchmarkCondition(task()).condition_hash != BenchmarkCondition(task(**{field: 'changed'})).condition_hash


def test_models_do_not_change_condition_or_share_identity():
    first, second = run(), run('RUN-beta', agent_model='synthetic-B')
    assert first.condition_hash == second.condition_hash
    assert first.budget_root_run_id != second.budget_root_run_id
    assert first.scientific_family_id == second.scientific_family_id
    assert first.content_digest() != second.content_digest()


def test_continuation_inherits_root_and_rejects_model_or_condition_change():
    first = run()
    child = run('RUN-resume', parent_run_id=first.benchmark_run_id, budget_root_run_id=first.budget_root_run_id)
    validate_run_lineage(child, [first])
    for changes in ({'agent_model': 'other'}, {'agent_model_version': 'v2'}, {'condition_hash': 'f'*64}, {'budget_root_run_id': 'RUN-resume'}):
        with pytest.raises(ValueError):
            validate_run_lineage(replace(child, **changes), [first])
    with pytest.raises(ValueError):
        validate_run_lineage(child, [])


@pytest.mark.parametrize('value', [-1, True, 1.5, float('nan'), None])
def test_invalid_budget_rejected(value):
    limits = dict.fromkeys(BUDGET_DIMENSIONS, 2)
    limits['attempts'] = value
    with pytest.raises(ValueError):
        task(budget_limits=limits)


def test_incomplete_unlimited_budget_and_missing_fields_rejected():
    for limits in ({'attempts': 2}, dict(task().budget_limits, mystery=1)):
        with pytest.raises(ValueError):
            task(budget_limits=limits)
    for changes in ({'horizon': ''}, {'market': 'ETF'}, {'track': 'OPEN_WEB'}, {'data_spec_hash': 'bad'}, {'asof_cutoff': '2000-01-01'}):
        with pytest.raises(ValueError):
            task(**changes)


def test_synthetic_does_not_unfreeze_empirical_or_shadow():
    task().require_activation()
    for mode in ('EMPIRICAL', 'SHADOW'):
        with pytest.raises(ValueError):
            task(mode=mode).require_activation()
    # Compatibility alias checks current permission, not historical provenance.
    task(decision_registry_hash='0'*64).require_activation()
    with pytest.raises(ValueError):
        require_activation('LIVE')


def test_bindings_verify_actual_contract_hashes():
    from quant_rsi.contracts.data import DataSpec, SnapshotFile, SnapshotManifest
    spec = DataSpec('SYNTHETIC', 'r1', 'a'*64, '2000-01-01T00:00:00Z',
                    '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z',
                    '2000-01-01T00:00:00Z', None, 'UTC', {'price': 'synthetic'}, 'none', 'v1', 'v1', 'v1',
                    'available_at_lte_decision_at_and_membership_effective_at_decision',
                    'choose_latest_revision_available_by_decision_not_latest_download')
    snapshot = SnapshotManifest('synthetic', spec, [SnapshotFile('raw.txt', 'a'*64)])
    bound = task(data_spec_hash=spec.content_hash(), snapshot_hash=snapshot.content_hash())
    bound.verify_data_bindings(spec, snapshot)
    with pytest.raises(ValueError):
        bound.verify_data_bindings(replace(spec, source_revision='r2'), snapshot)


def frozen_task(snapshot, **changes):
    return task(decision_registry_hash=canonical_hash(snapshot),
                decision_snapshot_ref='sha256:' + canonical_hash(snapshot),
                decision_registry_version=snapshot['version'], **changes)


def test_a1_02_01_freeze_under_registry_vn():
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    frozen.verify_frozen_condition(snapshot)
    assert frozen.decision_snapshot_ref == 'sha256:' + canonical_hash(snapshot)
    assert TaskContract.from_dict(frozen.to_dict()) == frozen
    with pytest.raises(AttributeError):
        frozen.decision_registry_version = 'next'


def test_a1_02_02_registry_upgrade_does_not_mutate_task(monkeypatch):
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    before = frozen.content_digest()
    current = deepcopy(snapshot)
    current['version'] = 'next'
    current['activation']['stage_B']['authorized'] = True
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: current)
    assert canonical_hash(current) != frozen.decision_registry_hash
    frozen.authorize_dispatch()
    assert frozen.content_digest() == before


def test_a1_02_03_historical_verify_never_reads_current(monkeypatch):
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    def forbidden_read():
        pytest.fail('historical verification read current registry')
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', forbidden_read)
    frozen.verify_frozen_condition(snapshot)


def test_a1_02_04_current_revocation_blocks_old_task(monkeypatch):
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    current = deepcopy(snapshot)
    current['version'] = 'next'
    current['activation']['stage_A']['mode'] = 'DISABLED'
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: current)
    frozen.verify_frozen_condition(snapshot)
    with pytest.raises(ValueError):
        frozen.authorize_dispatch()


def test_a1_02_05_current_permission_allows_explicit_new_run(monkeypatch):
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    condition = BenchmarkCondition(frozen)
    current = deepcopy(snapshot)
    current['version'] = 'next'
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: current)
    frozen.verify_frozen_condition(snapshot)
    frozen.authorize_dispatch()
    first = run(condition_hash=condition.condition_hash)
    second = run('RUN-new', condition_hash=condition.condition_hash)
    validate_run_lineage(second, [first])
    assert first.budget_root_run_id != second.budget_root_run_id


def test_a1_02_06_tampered_snapshot_blocked():
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    snapshot['decisions']['D01']['value'] = 'ETF'
    with pytest.raises(ValueError):
        frozen.verify_frozen_condition(snapshot)


@pytest.mark.parametrize('changes', [
    {'decision_registry_hash': '0'*64},
    {'decision_snapshot_ref': 'sha256:' + '0'*64},
    {'decision_registry_version': 'wrong'},
])
def test_a1_02_07_snapshot_hash_ref_version_mismatch_blocked(changes):
    snapshot = load_decisions()
    with pytest.raises(ValueError):
        replace(frozen_task(snapshot), **changes).verify_frozen_condition(snapshot)


def test_a1_02_08_current_cannot_replace_historical_snapshot(monkeypatch):
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    current = deepcopy(snapshot)
    current['version'] = 'next'
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: current)
    with pytest.raises(ValueError):
        frozen.verify_frozen_condition(current)
    with pytest.raises(ValueError):
        frozen.verify_frozen_condition(None)


def test_a1_02_09_historical_cannot_authorize_current_dispatch(monkeypatch):
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    current = deepcopy(snapshot)
    current['decisions']['D04A']['status'] = 'DEFERRED'
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: current)
    frozen.verify_frozen_condition(snapshot)
    with pytest.raises(TypeError):
        frozen.authorize_dispatch(snapshot)
    with pytest.raises(TypeError):
        frozen.authorize_dispatch(registry=snapshot)
    with pytest.raises(ValueError):
        frozen.authorize_dispatch()


def test_legacy_snapshot_metadata_decodes_but_cannot_verify():
    encoded = task().to_dict()
    del encoded['decision_snapshot_ref']
    del encoded['decision_registry_version']
    legacy = TaskContract.from_dict(encoded)
    assert legacy.decision_snapshot_ref is legacy.decision_registry_version is None
    with pytest.raises(ValueError):
        legacy.verify_frozen_condition(load_decisions())


@pytest.mark.parametrize('field', ['decision_snapshot_ref', 'decision_registry_version'])
def test_each_missing_snapshot_metadata_field_blocks_verification(field):
    snapshot = load_decisions()
    frozen = replace(frozen_task(snapshot), **{field: None})
    with pytest.raises(ValueError):
        frozen.verify_frozen_condition(snapshot)


def test_content_addressed_snapshot_can_be_an_in_memory_immutable_mapping():
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    immutable = run(requested_settings=snapshot).requested_settings
    assert canonical_hash(immutable) == frozen.decision_registry_hash
    frozen.verify_frozen_condition(immutable)
    encoded = frozen.to_dict()
    encoded['decision_snapshot_ref'] = 'file:///mutable/decisions.yaml'
    with pytest.raises(ValueError):
        TaskContract.from_dict(encoded).verify_frozen_condition(snapshot)


@pytest.mark.parametrize('path,value', [
    (('scope',), 'another_project'),
    (('canonical',), False),
    (('decisions', 'D01', 'value'), 'ETF'),
    (('decisions', 'D02', 'value'), 'LIVE_AGENT'),
    (('decisions', 'D03', 'value'), 'OPEN_WEB'),
    (('decisions', 'D13', 'value'), 'EXTERNAL_REUSE'),
    (('decisions', 'D08', 'status'), 'DEFERRED'),
    (('decisions', 'D04A', 'value', 'accounting_policy_version'), 'next'),
    (('decisions', 'D04A', 'value', 'retries'), 'free'),
    (('decisions', 'D04A', 'value', 'settlement'), 'refund'),
    (('decisions', 'D04A', 'value', 'capability_denominator'), 'all_models'),
    (('activation', 'stage_A', 'mode'), 'DISABLED'),
])
def test_historical_and_current_policy_fail_closed(monkeypatch, path, value):
    snapshot = load_decisions()
    frozen = frozen_task(snapshot)
    invalid = deepcopy(snapshot)
    node = invalid
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    invalid_task = frozen_task(invalid)
    with pytest.raises(ValueError):
        invalid_task.verify_frozen_condition(invalid)
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: invalid)
    with pytest.raises(ValueError):
        frozen.authorize_dispatch()


@pytest.mark.parametrize('invalid', [None, {}, {'version': 'next'}])
def test_malformed_current_registry_fails_closed(monkeypatch, invalid):
    frozen = task()
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: invalid)
    with pytest.raises(ValueError):
        frozen.authorize_dispatch()


@pytest.mark.parametrize('mode,required', [('EMPIRICAL', ['D04B', 'D11', 'D12']),
                                          ('SHADOW', ['D09'])])
def test_mode_authorization_requires_explicit_grants_and_frozen_decisions(monkeypatch, mode, required):
    current = load_decisions()
    frozen = task(mode=mode)
    section = current['activation'][mode.lower()]
    current['activation']['stage_B']['authorized'] = True
    section['authorized'] = True
    section['requires_frozen'] = []  # Cannot omit mandatory mode-specific decisions.
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: current)
    with pytest.raises(ValueError):
        frozen.authorize_dispatch()
    for key in required:
        current['decisions'][key]['status'] = 'FROZEN'
    frozen.authorize_dispatch()
    current['activation']['stage_B']['authorized'] = False
    with pytest.raises(ValueError):
        frozen.authorize_dispatch()
    current['activation']['stage_B']['authorized'] = True
    section['authorized'] = 'false'
    with pytest.raises(ValueError):
        frozen.authorize_dispatch()


def test_task_accounting_version_must_be_supported_and_match_policy(monkeypatch):
    snapshot = load_decisions()
    frozen = frozen_task(snapshot, budget_policy_version='unknown')
    monkeypatch.setattr('quant_rsi.contracts.condition.load_decisions', lambda: snapshot)
    with pytest.raises(ValueError):
        frozen.verify_frozen_condition(snapshot)
    with pytest.raises(ValueError):
        frozen.authorize_dispatch()


def test_model_provenance_is_deeply_immutable_json_and_roundtrips():
    settings = {'temperature': 0.2, 'tools': [{'names': ['synthetic'], 'enabled': True}]}
    metadata = {'version': None, 'counts': [1, 2], 'response': {'id': 'fake'}}
    frozen = run(provider='synthetic', agent_model_version=None,
                 requested_settings=settings, returned_metadata=metadata)
    before = frozen.content_digest()
    settings['tools'][0]['names'].append('mutated')
    metadata['response']['id'] = 'mutated'
    assert frozen.requested_settings['tools'][0]['names'] == ('synthetic',)
    assert frozen.returned_metadata['response']['id'] == 'fake'
    with pytest.raises(TypeError):
        frozen.requested_settings['tools'][0]['enabled'] = False
    with pytest.raises(TypeError):
        frozen.returned_metadata['counts'][0] = 5
    restored = AgentBenchmarkRun.from_dict(json.loads(json.dumps(frozen.to_dict())))
    assert restored == frozen
    assert restored.content_digest() == before
    assert restored.agent_model_version is None
    assert run().provider is None
    assert dict(run().requested_settings) == dict(run().returned_metadata) == {}
    for changes in ({'provider': 'other'}, {'requested_settings': {'temperature': 1}},
                    {'returned_metadata': {'version': 'v2'}}):
        assert replace(frozen, **changes).content_digest() != before


@pytest.mark.parametrize('field', ['requested_settings', 'returned_metadata'])
@pytest.mark.parametrize('value', [None, [], {'x': float('nan')}, {'x': float('inf')},
                                  {'x': -float('inf')}, {1: 'bad'}, {'x': {1, 2}},
                                  {'x': object()}, {'x': b'bytes'}])
def test_model_provenance_rejects_non_json_and_nonfinite(field, value):
    with pytest.raises(ValueError):
        run(**{field: value})


def test_provider_identity_cannot_change_in_continuation():
    first = run(provider='synthetic')
    child = run('RUN-child', provider='other', parent_run_id=first.benchmark_run_id,
                budget_root_run_id=first.budget_root_run_id)
    with pytest.raises(ValueError):
        validate_run_lineage(child, [first])


@pytest.mark.parametrize('field', ['requested_settings', 'returned_metadata'])
def test_cyclic_model_provenance_is_not_json(field):
    cycle = {}
    cycle['self'] = cycle
    with pytest.raises(ValueError, match='acyclic JSON'):
        run(**{field: cycle})


def test_legacy_run_decodes_with_explicit_unknown_provider_and_empty_metadata():
    encoded = run().to_dict()
    for field in ('provider', 'requested_settings', 'returned_metadata'):
        del encoded[field]
    encoded['agent_model_version'] = None
    restored = AgentBenchmarkRun.from_dict(encoded)
    assert restored.provider is restored.agent_model_version is None
    assert restored.to_dict()['requested_settings'] == {}
    assert restored.to_dict()['returned_metadata'] == {}
