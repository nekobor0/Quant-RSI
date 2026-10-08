"""Frozen comparison conditions and per-agent identities; no evaluator or scores."""
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
import hashlib
import json
import math

import yaml

from .research import _Contract, _hash, _id, _text, _timestamp, index_by_id


SEARCH_DIMENSIONS = (
    'attempts', 'candidate_trials', 'hypotheses_seen', 'factor_variants',
    'parameter_trials', 'model_trials', 'prompt_revisions', 'retries',
    'validation_queries', 'sealed_submissions', 'human_interventions',
)
RESOURCE_DIMENSIONS = ('input_tokens', 'output_tokens', 'wall_milliseconds', 'cpu_milliseconds')
BUDGET_DIMENSIONS = SEARCH_DIMENSIONS + RESOURCE_DIMENSIONS

# Implementation compatibility, not a second registry: unsupported accounting
# semantics require a kernel update, even if the registry version alone changes.
_ACCOUNTING_POLICY = {
    'accounting_policy_version': '0.2',
    'benchmark_budget_owner': 'AgentBenchmarkRun.budget_root_run_id',
    'scientific_claim_owner': 'ScientificSearchFamily.scientific_family_id',
    'capability_denominator': 'own_budget_root_run_attempts_only',
    'scientific_denominator': 'deduplicated_attempts_and_variants_in_selected_family_ancestry',
    'cross_model_penalty_on_capability': 'forbidden',
    'pooling': 'explicit_family_parent_links_for_joint_final_claim_selection_only',
    'retries': 'counted_attempts_same_budget_root_no_reset',
    'model_switch': 'independent_comparison_run_new_identity_same_frozen_condition',
    'continuation': 'same_condition_and_model_inherits_parent_budget_root',
    'family_inheritance': 'union_parent_ancestry_no_deletion_no_double_counting',
    'reserve': 'atomic_before_attempt_started',
    'settlement': 'search_counters_never_refunded_resource_actuals_recorded',
    'unknown_usage': 'reserve_upper_bound_and_block_new_dispatch_until_reconciled',
    'limits': 'task_specific_explicit_nonnegative_integers_no_default_unlimited',
    'budget_exhaustion': 'reject_and_preserve_denial_event',
    'peak_memory': 'per_attempt_resource_limit_not_cumulative_search_counter',
    'elapsed_time': 'persisted_as_integer_milliseconds',
}


def _json_value(value, *, freeze=False):
    """Copy JSON values; tuples are the immutable representation of arrays."""
    try:
        if isinstance(value, Mapping):
            if any(type(key) is not str for key in value):
                raise ValueError('JSON object keys must be strings')
            result = {key: _json_value(item, freeze=freeze) for key, item in value.items()}
            return MappingProxyType(result) if freeze else result
        if isinstance(value, (list, tuple)):
            result = [_json_value(item, freeze=freeze) for item in value]
            return tuple(result) if freeze else result
        if value is None or type(value) in (str, bool, int):
            return value
        if type(value) is float and math.isfinite(value):
            return value
        raise ValueError('finite JSON values required')
    except RecursionError as exc:
        raise ValueError('acyclic JSON values required') from exc


def canonical_hash(value):
    return hashlib.sha256(json.dumps(_json_value(value), sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def counters(value, *, complete=False):
    if not isinstance(value, Mapping) or set(value) - set(BUDGET_DIMENSIONS):
        raise ValueError('unknown budget dimensions')
    if complete and set(value) != set(BUDGET_DIMENSIONS):
        raise ValueError('every budget dimension needs an explicit limit')
    if any(type(v) is not int or v < 0 for v in value.values()):
        raise ValueError('budget counters must be nonnegative integers, not bool')
    return dict(value)


def load_decisions():
    path = Path(__file__).resolve().parents[3] / 'contracts' / 'decisions.yaml'
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def decision_digest():
    return canonical_hash(load_decisions())


def require_activation(mode, registry=None):
    """Policy check only; supplied registries never grant dispatch authority.

    Dispatch callers must use TaskContract.authorize_dispatch().
    """
    registry = load_decisions() if registry is None else registry
    try:
        decisions = registry['decisions']
        for key in ('D01', 'D02', 'D03', 'D04A', 'D05', 'D06', 'D07', 'D08', 'D10', 'D13'):
            if decisions[key]['status'] != 'FROZEN':
                raise ValueError(f'unfrozen required decision: {key}')
        if mode == 'SYNTHETIC':
            stage_a = registry['activation']['stage_A']
            if (stage_a['mode'] != 'SYNTHETIC_GOVERNANCE_ONLY'
                    or not isinstance(stage_a['authorized_work_items'], (list, tuple))
                    or 'W06' not in stage_a['authorized_work_items']):
                raise ValueError('synthetic governance activation not authorized')
            return
        stage = {'EMPIRICAL': 'empirical', 'SHADOW': 'shadow'}.get(mode)
        if (stage is None or registry['activation']['stage_B']['authorized'] is not True
                or registry['activation'][stage]['authorized'] is not True):
            raise ValueError('empirical/shadow activation is not authorized')
        declared = registry['activation'][stage]['requires_frozen']
        if not isinstance(declared, (list, tuple)) or any(type(key) is not str for key in declared):
            raise ValueError('requires_frozen must be a list of decision IDs')
        mandatory = ('D04B', 'D11', 'D12') if mode == 'EMPIRICAL' else ('D09',)
        for key in (*mandatory, *declared):
            if decisions[key]['status'] != 'FROZEN':
                raise ValueError(f'unfrozen required decision: {key}')
    except (KeyError, TypeError) as exc:
        raise ValueError('missing or malformed activation policy') from exc


@dataclass(frozen=True)
class TaskContract(_Contract):
    task_id: str
    task_version: str
    target: str
    horizon: str
    benchmark_ref: str
    universe_ref: str
    asof_cutoff: str
    execution_timing: str
    data_spec_hash: str
    snapshot_hash: str
    cleaning_spec_version: str
    split_version: str
    env_version: str
    evaluator_version: str
    cost_model_version: str
    market_rules_version: str
    calendar_version: str
    statistical_protocol_version: str
    budget_policy_version: str
    decision_registry_hash: str
    budget_limits: Mapping[str, int]
    memory_limit_mb: int
    frozen_at: str
    frozen_by: str
    mode: str = 'SYNTHETIC'
    market: str = 'A_SHARE_ORDINARY_STOCK_DAILY'
    research_type: str = 'RESEARCH_AGENT_ONLY'
    track: str = 'CLOSED_DATA'
    decision_snapshot_ref: str | None = None
    decision_registry_version: str | None = None

    def __post_init__(self):
        _id(self.task_id, 'task_id')
        for name in ('data_spec_hash', 'snapshot_hash', 'decision_registry_hash'):
            _hash(getattr(self, name))
        for name in ('decision_snapshot_ref', 'decision_registry_version'):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)
        for name in ('task_version', 'target', 'horizon', 'benchmark_ref', 'universe_ref',
                     'execution_timing', 'cleaning_spec_version', 'split_version', 'env_version',
                     'evaluator_version', 'cost_model_version', 'market_rules_version',
                     'calendar_version', 'statistical_protocol_version', 'budget_policy_version', 'frozen_by'):
            _text(getattr(self, name), name)
        if self.mode not in ('SYNTHETIC', 'EMPIRICAL', 'SHADOW'):
            raise ValueError('unknown execution mode')
        if (self.market, self.research_type, self.track) != (
                'A_SHARE_ORDINARY_STOCK_DAILY', 'RESEARCH_AGENT_ONLY', 'CLOSED_DATA'):
            raise ValueError('Task exceeds frozen v0.1 scope')
        if type(self.memory_limit_mb) is not int or self.memory_limit_mb <= 0:
            raise ValueError('positive integer memory limit required')
        object.__setattr__(self, 'asof_cutoff', _timestamp(self.asof_cutoff))
        object.__setattr__(self, 'frozen_at', _timestamp(self.frozen_at))
        object.__setattr__(self, 'budget_limits', MappingProxyType(counters(self.budget_limits, complete=True)))

    def _verify_policy(self, registry):
        try:
            _text(registry['version'], 'decision registry version')
            if (registry['canonical'] is not True
                    or registry['scope'] != 'independent_Quant_RSI_Governance_Kernel'):
                raise ValueError('decision registry scope mismatch')
            decisions = registry['decisions']
            for key, expected in (('D01', self.market), ('D02', self.research_type),
                                  ('D03', self.track),
                                  ('D13', 'INDEPENDENT_QUANT_RSI_NO_EXTERNAL_PROJECT_REUSE')):
                if decisions[key]['value'] != expected:
                    raise ValueError(f'decision scope mismatch: {key}')
            policy = decisions['D04A']['value']
            if (self.budget_policy_version != _ACCOUNTING_POLICY['accounting_policy_version']
                    or any(policy[key] != expected for key, expected in _ACCOUNTING_POLICY.items())):
                raise ValueError('unsupported accounting policy')
            require_activation(self.mode, registry)
        except (KeyError, TypeError) as exc:
            raise ValueError('missing or malformed decision policy') from exc

    def verify_frozen_condition(self, snapshot):
        """Verify historical provenance only, without reading current decisions.

        The caller resolves sha256:<digest> from immutable trace/artifact content;
        this contract requires no filesystem snapshot store. Legacy metadata is
        decodable but cannot establish historical validity.
        """
        if self.decision_snapshot_ref is None or self.decision_registry_version is None:
            raise ValueError('historical decision snapshot metadata required')
        if (not isinstance(snapshot, Mapping)
                or self.decision_snapshot_ref != 'sha256:' + self.decision_registry_hash
                or snapshot.get('version') != self.decision_registry_version
                or canonical_hash(snapshot) != self.decision_registry_hash):
            raise ValueError('historical decision snapshot ref/hash/version mismatch')
        self._verify_policy(snapshot)

    def authorize_dispatch(self):
        """Check current canonical permission only; never accept caller authority.

        Registry upgrades need not match the historical hash/version. A new run
        and attempt still require the ledger's lineage and budget validation.
        """
        self._verify_policy(load_decisions())

    def require_activation(self):
        """Compatibility alias for current authorization, NOT historical verification."""
        self.authorize_dispatch()

    def verify_data_bindings(self, data_spec, snapshot):
        if data_spec.content_hash() != self.data_spec_hash or snapshot.content_hash() != self.snapshot_hash:
            raise ValueError('Task data content binding mismatch')
        if snapshot.data_spec.content_hash() != self.data_spec_hash:
            raise ValueError('snapshot points at another DataSpec')
        if data_spec.cleaning_spec_version != self.cleaning_spec_version:
            raise ValueError('cleaning version mismatch')


@dataclass(frozen=True)
class BenchmarkCondition(_Contract):
    task: TaskContract

    def __post_init__(self):
        if isinstance(self.task, Mapping):
            object.__setattr__(self, 'task', TaskContract.from_dict(self.task))
        if type(self.task) is not TaskContract:
            raise ValueError('condition requires a TaskContract')

    def to_dict(self):
        return {'task': self.task.to_dict()}

    @property
    def condition_hash(self):
        return self.content_digest()


@dataclass(frozen=True)
class AgentBenchmarkRun(_Contract):
    """Canonical model provenance: agent_model is the family/exposed identifier.

    agent_model_version records the exact exposed version, or None when unknown;
    provider and returned metadata must not be guessed from the model name.
    """
    benchmark_run_id: str
    scientific_family_id: str
    condition_hash: str
    agent_model: str
    agent_model_version: str | None
    prompt_hash: str
    code_hash: str
    dependency_hash: str
    budget_root_run_id: str
    registered_at: str
    parent_run_id: str | None = None
    provider: str | None = None
    requested_settings: Mapping = field(default_factory=dict)
    returned_metadata: Mapping = field(default_factory=dict)

    def __post_init__(self):
        for name in ('benchmark_run_id', 'scientific_family_id', 'budget_root_run_id'):
            _id(getattr(self, name), name)
        for name in ('condition_hash', 'prompt_hash', 'code_hash', 'dependency_hash'):
            _hash(getattr(self, name))
        _text(self.agent_model, 'agent_model')
        for name in ('agent_model_version', 'provider'):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)
        for name in ('requested_settings', 'returned_metadata'):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ValueError(f'{name} must be a JSON object')
            object.__setattr__(self, name, _json_value(value, freeze=True))
        object.__setattr__(self, 'registered_at', _timestamp(self.registered_at))
        if self.parent_run_id is None:
            if self.budget_root_run_id != self.benchmark_run_id:
                raise ValueError('independent run owns its own budget root')
        else:
            _id(self.parent_run_id, 'parent_run_id')
            if self.parent_run_id == self.benchmark_run_id:
                raise ValueError('run cannot parent itself')


def validate_run_lineage(run, registered_runs):
    registry = index_by_id(registered_runs, 'benchmark_run_id')
    if run.benchmark_run_id in registry and registry[run.benchmark_run_id] != run:
        raise ValueError('run identity cannot be overwritten')
    if run.parent_run_id is None:
        return
    seen = {run.benchmark_run_id}
    child = run
    while child.parent_run_id is not None:
        parent = registry.get(child.parent_run_id)
        if parent is None or parent.benchmark_run_id in seen:
            raise ValueError('missing or cyclic parent run')
        seen.add(parent.benchmark_run_id)
        if (child.condition_hash, child.agent_model, child.agent_model_version, child.provider, child.budget_root_run_id) != (
                parent.condition_hash, parent.agent_model, parent.agent_model_version, parent.provider, parent.budget_root_run_id):
            raise ValueError('continuation cannot change condition/model or reset budget root')
        child = parent
    if child.benchmark_run_id != run.budget_root_run_id:
        raise ValueError('root run mismatch')


def validate_experiment_binding(experiment, task, run):
    """DataSpec ID is its content-addressed DATA-<sha256> reference, not a source ID."""
    if (experiment.task_id != task.task_id or experiment.benchmark_run_id != run.benchmark_run_id
            or experiment.scientific_family_id != run.scientific_family_id
            or experiment.data_spec_id != 'DATA-' + task.data_spec_hash
            or experiment.cost_protocol_id != task.cost_model_version
            or experiment.statistical_protocol_id != task.statistical_protocol_version):
        raise ValueError('experiment does not bind frozen task/data/run/protocol')
    if datetime.fromisoformat(experiment.preregistered_at) < datetime.fromisoformat(task.frozen_at):
        raise ValueError('experiment must follow task freeze')
