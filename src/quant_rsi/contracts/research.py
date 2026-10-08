"""Immutable research contracts; references do not grant execution or promotion.

IDs are 3..128 ASCII characters; artifact hashes are lowercase SHA-256.
Textual falsifiability and artifact authenticity require independent review.
"""

from dataclasses import dataclass, fields
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from collections.abc import Mapping


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be nonblank, trimmed text")


def _id(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:/-]{2,127}", value):
        raise ValueError(f"{name} must be a meaningful 3..128 character ID")


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("artifact hash must be lowercase SHA-256")


def _ids(value, name, *, required=False):
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple")
    result = tuple(value)
    for item in result:
        _id(item, name)
    if len(set(result)) != len(result) or (required and not result):
        raise ValueError(f"{name} must be unique and satisfy required cardinality")
    return result


def _timestamp(value):
    _text(value, "timestamp")
    try:
        if "T" not in value:
            raise ValueError("timestamp requires time")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamp requires timezone")
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid timezone-aware ISO timestamp") from exc


class _Contract:
    def to_dict(self):
        def plain(value):
            if isinstance(value, Mapping):
                return {key: plain(item) for key, item in value.items()}
            if isinstance(value, tuple):
                return [plain(item) for item in value]
            return value
        return {field.name: plain(getattr(self, field.name)) for field in fields(self)}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, Mapping):
            raise ValueError("contract must be an object")
        if set(value) - {field.name for field in fields(cls)}:
            raise ValueError("unknown contract fields")
        try:
            return cls(**value)
        except TypeError as exc:
            raise ValueError("missing or invalid contract fields") from exc

    def content_digest(self):
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConceptMapping(_Contract):
    concept_mapping_id: str
    mechanism: str
    observable: str
    proxy: str
    feature_refs: tuple[str, ...]

    def __post_init__(self):
        _id(self.concept_mapping_id, "concept_mapping_id")
        for name in ("mechanism", "observable", "proxy"):
            _text(getattr(self, name), name)
        object.__setattr__(self, "feature_refs", _ids(self.feature_refs, "feature_refs", required=True))


@dataclass(frozen=True)
class Hypothesis(_Contract):
    hypothesis_id: str
    claim_id: str
    claim: str
    falsification_condition: str
    concept_mapping_id: str

    def __post_init__(self):
        for name in ("hypothesis_id", "claim_id", "concept_mapping_id"):
            _id(getattr(self, name), name)
        _text(self.claim, "claim")
        _text(self.falsification_condition, "falsification_condition")


@dataclass(frozen=True)
class ScientificSearchFamily(_Contract):
    """Service-assigned final-claim selection scope, never a capability budget.

    Parents retain their own claim/scope; descendants inherit their complete
    ancestry. Union ancestry IDs when consuming ledger attempts/variants to avoid
    diamond double counting. This contract neither stores nor scores attempts.
    """

    scientific_family_id: str
    claim_id: str
    selection_scope: str
    parent_family_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("scientific_family_id", "claim_id"):
            _id(getattr(self, name), name)
        _text(self.selection_scope, "selection_scope")
        parents = _ids(self.parent_family_ids, "parent_family_ids")
        if self.scientific_family_id in parents:
            raise ValueError("family cannot parent itself")
        object.__setattr__(self, "parent_family_ids", parents)


@dataclass(frozen=True)
class ExperimentSpec(_Contract):
    """Immutable preregistration. Legacy execution_started_at is not execution truth.

    Retained only to decode old artifacts; the ledger rejects it on registration.
    All admission checks use trace events, never this legacy field.
    """
    experiment_id: str
    hypothesis_id: str
    task_id: str
    data_spec_id: str
    cost_protocol_id: str
    statistical_protocol_id: str
    scientific_family_id: str
    benchmark_run_id: str
    preregistered_at: str
    execution_started_at: str | None = None

    def __post_init__(self):
        for field in fields(self):
            if field.name.endswith("_id"):
                _id(getattr(self, field.name), field.name)
        registered = _timestamp(self.preregistered_at)
        object.__setattr__(self, "preregistered_at", registered)
        if self.execution_started_at is not None:
            started = _timestamp(self.execution_started_at)
            if datetime.fromisoformat(started) <= datetime.fromisoformat(registered):
                raise ValueError("preregistration must precede execution")
            object.__setattr__(self, "execution_started_at", started)


@dataclass(frozen=True)
class Evidence(_Contract):
    """Unknown metrics remain None; notes cannot carry a measured fact/verdict.

    One source artifact binds all measured metrics in this evidence object.
    Hash presence is provenance structure, not proof of artifact authenticity.
    """

    evidence_id: str
    experiment_id: str
    candidate_id: str
    metrics: Mapping[str, float | int | None]
    source_artifact_ref: str | None = None
    source_artifact_hash: str | None = None
    notes: str | None = None
    kind: str = 'MEASURED_STRATEGY'

    def __post_init__(self):
        if self.kind not in ('MEASURED_STRATEGY', 'SCIENTIFIC_FAILURE', 'INFRASTRUCTURE_FAILURE', 'UNKNOWN', 'PUBLIC_FIXTURE'):
            raise ValueError('unknown evidence kind')
        for name in ("evidence_id", "experiment_id", "candidate_id"):
            _id(getattr(self, name), name)
        if not isinstance(self.metrics, Mapping) or not self.metrics:
            raise ValueError("metrics must be a nonempty mapping")
        metrics = dict(self.metrics)
        for key, value in metrics.items():
            _id(key, "metric name")
            if value is not None:
                if type(value) not in (int, float):
                    raise ValueError("metrics must be numbers or None, never bool/narrative")
                try:
                    finite = math.isfinite(value)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError("metrics must be finite")
        has_ref = self.source_artifact_ref is not None
        has_hash = self.source_artifact_hash is not None
        if has_ref != has_hash or (any(v is not None for v in metrics.values()) and not has_ref):
            raise ValueError("measured metrics require source artifact ref and hash")
        if has_ref:
            _text(self.source_artifact_ref, "source_artifact_ref")
            _hash(self.source_artifact_hash)
        if self.notes is not None:
            _text(self.notes, "notes")
        object.__setattr__(self, "metrics", MappingProxyType(metrics))
        if self.kind in ('INFRASTRUCTURE_FAILURE', 'UNKNOWN', 'PUBLIC_FIXTURE') and any(v is not None for v in metrics.values()):
            raise ValueError('infrastructure failure/unknown cannot carry strategy measurements')


@dataclass(frozen=True)
class Candidate(_Contract):
    candidate_id: str
    experiment_id: str
    scientific_family_id: str
    benchmark_run_id: str
    artifact_ref: str
    artifact_hash: str
    code_hash: str
    attempt_id: str
    kind: str = 'STRATEGY'

    def __post_init__(self):
        for name in ("candidate_id", "experiment_id", "scientific_family_id", "benchmark_run_id", "attempt_id"):
            _id(getattr(self, name), name)
        _text(self.artifact_ref, "artifact_ref")
        _hash(self.artifact_hash)
        _hash(self.code_hash)
        if self.kind not in ('STRATEGY', 'FAILURE_DIAGNOSTIC', 'PUBLIC_FIXTURE'):
            raise ValueError('unknown candidate kind')


def index_by_id(objects, id_field):
    """Build an index without silently overwriting duplicate IDs."""
    result = {}
    for obj in objects:
        identifier = getattr(obj, id_field)
        _id(identifier, id_field)
        if identifier in result:
            raise ValueError(f"duplicate {id_field}: {identifier}")
        result[identifier] = obj
    return result


def family_ancestry(scientific_family_id, families):
    """Return immutable, deduplicated inclusive ancestry; reject missing/cyclic links."""
    _id(scientific_family_id, "scientific_family_id")
    registry = index_by_id(families, "scientific_family_id")
    visited, active = set(), set()

    def visit(identifier):
        if identifier in active:
            raise ValueError("cyclic family ancestry")
        if identifier in visited:
            return
        if identifier not in registry:
            raise ValueError(f"unregistered family: {identifier}")
        active.add(identifier)
        for parent in registry[identifier].parent_family_ids:
            visit(parent)
        active.remove(identifier)
        visited.add(identifier)

    visit(scientific_family_id)
    return frozenset(visited)


def validate_research_links(*, concept_mappings, hypotheses, families, experiments,
                            candidates, evidence, benchmark_run_ids, trace_store=None):
    """Validate a supplied research registry; external contracts remain ID-only.

    Call before admission/persistence. Standalone deserialization validates shape,
    not registry membership. W04 owns benchmark identity/condition/budget checks.
    """
    mappings = index_by_id(concept_mappings, "concept_mapping_id")
    claims = index_by_id(hypotheses, "hypothesis_id")
    index_by_id(claims.values(), "claim_id")
    family = index_by_id(families, "scientific_family_id")
    specs = index_by_id(experiments, "experiment_id")
    artifacts = index_by_id(candidates, "candidate_id")
    results = index_by_id(evidence, "evidence_id")
    runs = _ids(benchmark_run_ids, "benchmark_run_ids")
    events = [] if trace_store is None else trace_store.read()
    if artifacts and trace_store is None:
        raise ValueError('candidate lineage requires execution trace')
    if artifacts:
        for objects, kind, field in ((mappings, 'CONCEPT_REGISTERED', 'concept_mapping_id'),
                                     (claims, 'HYPOTHESIS_REGISTERED', 'hypothesis_id'),
                                     (family, 'FAMILY_REGISTERED', 'scientific_family_id')):
            persisted = {e['payload'][field]: e['payload'] for e in events if e['kind'] == kind}
            if any(persisted.get(key) != obj.to_dict() for key, obj in objects.items()):
                raise ValueError('research objects differ from canonical trace registration')

    def require(registry, identifier):
        if identifier not in registry:
            raise ValueError(f"unregistered reference: {identifier}")
        return registry[identifier]

    for hypothesis in claims.values():
        require(mappings, hypothesis.concept_mapping_id)
    claim_ids = {hypothesis.claim_id for hypothesis in claims.values()}
    for item in family.values():
        if item.claim_id not in claim_ids:
            raise ValueError("family references unregistered claim")
        family_ancestry(item.scientific_family_id, family.values())
    for spec in specs.values():
        hypothesis = require(claims, spec.hypothesis_id)
        scope = require(family, spec.scientific_family_id)
        if scope.claim_id != hypothesis.claim_id or spec.benchmark_run_id not in runs:
            raise ValueError("experiment claim or benchmark run mismatch")
    for candidate in artifacts.values():
        spec = require(specs, candidate.experiment_id)
        if (candidate.scientific_family_id != spec.scientific_family_id
                or candidate.benchmark_run_id != spec.benchmark_run_id):
            raise ValueError("candidate family/run differs from registered experiment")
        validate_candidate_trace(candidate, spec, events)
    for item in results.values():
        spec = require(specs, item.experiment_id)
        candidate = require(artifacts, item.candidate_id)
        if candidate.experiment_id != spec.experiment_id:
            raise ValueError("evidence candidate/experiment mismatch")
        validate_evidence_trace(item, candidate, events)


def attempt_from_trace(attempt_id, events):
    """Read-only projection; no Attempt object or writable status table exists."""
    starts = [e for e in events if e['kind'] == 'ATTEMPT_STARTED' and e['payload']['attempt_id'] == attempt_id]
    if len(starts) != 1:
        raise ValueError('requires execution: exactly one ATTEMPT_STARTED')
    start = starts[0]
    terminals = [e for e in events if e['kind'] == 'ATTEMPT_SETTLED' and e['payload']['attempt_id'] == attempt_id]
    if len(terminals) != 1 or terminals[0]['sequence'] <= start['sequence']:
        raise ValueError('attempt requires one terminal event after start')
    return start, terminals[0]


def validate_candidate_trace(candidate, experiment, events):
    start, terminal = attempt_from_trace(candidate.attempt_id, events)
    a = start['payload']
    if (a['experiment_id'], a['benchmark_run_id'], a['scientific_family_id']) != (
            candidate.experiment_id, candidate.benchmark_run_id, candidate.scientific_family_id):
        raise ValueError('candidate/attempt experiment/run/family mismatch')
    registered = [e for e in events if e['kind'] == 'EXPERIMENT_REGISTERED'
                  and e['payload']['experiment_id'] == experiment.experiment_id]
    if len(registered) != 1 or registered[0]['payload'] != experiment.to_dict() or registered[0]['sequence'] >= start['sequence']:
        raise ValueError('experiment differs from immutable preregistration')
    if experiment.execution_started_at is not None or datetime.fromisoformat(experiment.preregistered_at) >= datetime.fromisoformat(start['created_at']):
        raise ValueError('trace start must follow unmodified preregistration')
    run = next((e['payload'] for e in events if e['kind'] == 'RUN_REGISTERED'
                and e['payload']['benchmark_run_id'] == candidate.benchmark_run_id), None)
    if run is None or run['code_hash'] != candidate.code_hash or run['condition_hash'] != a['condition_hash']:
        raise ValueError('candidate code/run mismatch')
    success = terminal['payload']['status'] == 'SUCCEEDED'
    if candidate.kind == 'PUBLIC_FIXTURE':
        if a['scientific_variant_id'] is not None or a['envelope']['candidate_trials'] != 0:
            raise ValueError('public fixture cannot consume a scientific candidate trial')
    elif success != (candidate.kind == 'STRATEGY'):
        raise ValueError('failed attempt cannot be a successful strategy candidate')
    outputs = [e for e in events if e['kind'] == 'ATTEMPT_OUTPUT'
               and e['payload']['attempt_id'] == candidate.attempt_id]
    if len(outputs) != 1:
        raise ValueError('one candidate output per counted attempt required')
    output = outputs[0]
    expected = dict(attempt_id=candidate.attempt_id, candidate_id=candidate.candidate_id,
                    artifact_ref=candidate.artifact_ref, artifact_hash=candidate.artifact_hash, kind=candidate.kind)
    if output is None or output['payload'] != expected or not start['sequence'] < output['sequence'] < terminal['sequence']:
        raise ValueError('candidate artifact/attempt binding mismatch')
    if terminal['payload']['artifact_hashes'].get(candidate.artifact_ref) != candidate.artifact_hash:
        raise ValueError('terminal artifact hash mismatch')


def validate_evidence_trace(evidence, candidate, events):
    if (evidence.candidate_id, evidence.experiment_id) != (candidate.candidate_id, candidate.experiment_id):
        raise ValueError('evidence candidate/experiment mismatch')
    if evidence.source_artifact_ref is not None and (evidence.source_artifact_ref, evidence.source_artifact_hash) != (
            candidate.artifact_ref, candidate.artifact_hash):
        raise ValueError('evidence source artifact differs from candidate output')
    _, terminal = attempt_from_trace(candidate.attempt_id, events)
    if evidence.kind in ('MEASURED_STRATEGY', 'SCIENTIFIC_FAILURE'):
        if terminal['payload']['status'] != 'SUCCEEDED' or candidate.kind != 'STRATEGY':
            raise ValueError('strategy measurements require successful execution')
    elif evidence.kind == 'PUBLIC_FIXTURE' and candidate.kind != 'PUBLIC_FIXTURE':
        raise ValueError('public fixture evidence requires public fixture output')
    elif evidence.kind == 'INFRASTRUCTURE_FAILURE' and candidate.kind != 'FAILURE_DIAGNOSTIC':
        raise ValueError('infrastructure evidence requires diagnostic output')
