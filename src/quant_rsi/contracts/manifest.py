"""Immutable replay binding, not a runner or a second execution-state store."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from types import MappingProxyType

from .research import (
    _Contract, _hash, _id, _text, _timestamp, index_by_id,
    validate_research_links, ConceptMapping, Hypothesis, ScientificSearchFamily, ExperimentSpec,
)


def _hashes(value):
    if not isinstance(value, Mapping) or not value:
        raise ValueError('nonempty reference/hash mapping required')
    for ref, digest in value.items():
        _text(ref, 'reference')
        _hash(digest)
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class RunManifest(_Contract):
    manifest_id: str
    benchmark_run_id: str
    run_hash: str
    attempt_id: str
    task_ref: str
    task_hash: str
    condition_ref: str
    condition_hash: str
    scientific_family_id: str
    data_spec_ref: str
    snapshot_ref: str
    candidate_hashes: Mapping[str, str]
    evidence_hashes: Mapping[str, str]
    input_artifacts: Mapping[str, str]
    output_artifacts: Mapping[str, str]
    prompt_ref: str
    code_ref: str
    dependency_ref: str
    runtime_identity: str
    tool_versions: Mapping[str, str]
    randomness: str
    seed: int | None
    trace_refs: Mapping[str, str]
    created_at: str

    def __post_init__(self):
        for name in ('manifest_id', 'benchmark_run_id', 'attempt_id', 'scientific_family_id'):
            _id(getattr(self, name), name)
        for name in ('run_hash', 'task_hash', 'condition_hash'):
            _hash(getattr(self, name))
        for name in ('task_ref', 'condition_ref', 'data_spec_ref', 'snapshot_ref',
                     'prompt_ref', 'code_ref', 'dependency_ref', 'runtime_identity'):
            _text(getattr(self, name), name)
        for name in ('candidate_hashes', 'evidence_hashes', 'input_artifacts', 'output_artifacts', 'trace_refs'):
            object.__setattr__(self, name, _hashes(getattr(self, name)))
        if not isinstance(self.tool_versions, Mapping) or not self.tool_versions:
            raise ValueError('explicit tool versions required')
        for name, version in self.tool_versions.items():
            _text(name, 'tool')
            _text(version, 'tool version; use explicit unknown when unavailable')
        object.__setattr__(self, 'tool_versions', MappingProxyType(dict(self.tool_versions)))
        if self.randomness not in ('fixed_seed_deterministic', 'externally_nondeterministic', 'provider_randomness_unknown'):
            raise ValueError('explicit randomness declaration required')
        if self.randomness == 'fixed_seed_deterministic':
            if type(self.seed) is not int or self.seed < 0:
                raise ValueError('deterministic declaration requires explicit nonnegative seed')
        elif self.seed is not None:
            raise ValueError('unknown/external randomness must not masquerade as fixed seed')
        object.__setattr__(self, 'created_at', _timestamp(self.created_at))

    @property
    def manifest_digest(self):
        return self.content_digest()

    def verify_bindings(self, *, trace_store, condition, run, data_spec, snapshot,
                        candidates, evidence, resolve_artifact):
        """Verify historical inputs and completed output provenance; never dispatch.

        resolve_artifact(ref) must return actual immutable bytes. This verifies
        digests, not trust in the custodian or truth of measured metric values.
        A draft can be assembled before settlement, but a completed manifest
        must bind its terminal event. State is read from the full trace.
        """
        task = condition.task
        if (self.benchmark_run_id != run.benchmark_run_id or self.run_hash != run.content_digest()
                or self.condition_hash != condition.condition_hash or run.condition_hash != self.condition_hash
                or self.task_ref != task.task_id or self.task_hash != task.content_digest()
                or self.condition_ref != 'condition:' + self.condition_hash
                or self.scientific_family_id != run.scientific_family_id
                or self.data_spec_ref != 'DATA-' + task.data_spec_hash
                or self.snapshot_ref != 'SNAPSHOT-' + task.snapshot_hash):
            raise ValueError('manifest task/condition/run/family/data binding mismatch')
        task.verify_data_bindings(data_spec, snapshot)
        events = trace_store.read()
        by_id = {e['event_id']: e for e in events}
        for ref, digest in self.trace_refs.items():
            if ref not in by_id or by_id[ref]['event_hash'] != digest:
                raise ValueError('trace event binding mismatch')
        governance = by_id.get(task.decision_snapshot_ref)
        if governance is None or governance['kind'] != 'DECISION_SNAPSHOT':
            raise ValueError('historical governance snapshot missing')
        task.verify_frozen_condition(governance['payload'])
        if by_id.get('run:' + run.benchmark_run_id, {}).get('payload') != run.to_dict():
            raise ValueError('run differs from canonical trace')
        if by_id.get(self.condition_ref, {}).get('payload') != condition.to_dict():
            raise ValueError('condition differs from canonical trace')
        started = by_id.get('attempt:' + self.attempt_id)
        if started is None or started['kind'] != 'ATTEMPT_STARTED':
            raise ValueError('manifest requires started attempt')
        a = started['payload']
        if (a['benchmark_run_id'], a['scientific_family_id'], a['condition_hash']) != (
                self.benchmark_run_id, self.scientific_family_id, self.condition_hash):
            raise ValueError('manifest attempt/run/family mismatch')
        required_events = {started['event_id'], self.condition_ref, 'run:' + run.benchmark_run_id,
                           task.decision_snapshot_ref, 'experiment:' + a['experiment_id'],
                           'settle:' + self.attempt_id}
        candidate_index = index_by_id(candidates, 'candidate_id')
        evidence_index = index_by_id(evidence, 'evidence_id')
        if (dict(self.candidate_hashes) != {k: c.content_digest() for k, c in candidate_index.items()}
                or dict(self.evidence_hashes) != {k: e.content_digest() for k, e in evidence_index.items()}):
            raise ValueError('candidate/evidence digest binding mismatch')
        if any(c.attempt_id != self.attempt_id for c in candidates):
            raise ValueError('manifest candidate belongs to another attempt')
        required_events.update('output:' + c.candidate_id for c in candidates)
        if not required_events <= self.trace_refs.keys():
            raise ValueError('required trace references missing')
        if any(datetime.fromisoformat(by_id[ref]['created_at']) > datetime.fromisoformat(self.created_at)
               for ref in self.trace_refs):
            raise ValueError('manifest cannot predate referenced events')
        def objects(kind, cls):
            return [cls.from_dict(e['payload']) for e in events if e['kind'] == kind]
        validate_research_links(
            concept_mappings=objects('CONCEPT_REGISTERED', ConceptMapping),
            hypotheses=objects('HYPOTHESIS_REGISTERED', Hypothesis),
            families=objects('FAMILY_REGISTERED', ScientificSearchFamily),
            experiments=objects('EXPERIMENT_REGISTERED', ExperimentSpec),
            candidates=candidates, evidence=evidence,
            benchmark_run_ids=[e['payload']['benchmark_run_id'] for e in events if e['kind'] == 'RUN_REGISTERED'],
            trace_store=trace_store)
        outputs = {e['payload']['artifact_ref']: e['payload']['artifact_hash'] for e in events
                   if e['kind'] == 'ATTEMPT_OUTPUT' and e['payload']['attempt_id'] == self.attempt_id}
        terminal = next(e['payload'] for e in events if e['kind'] == 'ATTEMPT_SETTLED' and e['payload']['attempt_id'] == self.attempt_id)
        if dict(self.output_artifacts) != outputs or outputs != terminal['artifact_hashes']:
            raise ValueError('output artifact set mismatch')
        required_inputs = {self.prompt_ref: run.prompt_hash, self.code_ref: run.code_hash,
                           self.dependency_ref: run.dependency_hash, self.data_spec_ref: task.data_spec_hash,
                           self.snapshot_ref: task.snapshot_hash}
        if len(required_inputs) != 5 or any(self.input_artifacts.get(k) != v for k, v in required_inputs.items()):
            raise ValueError('code/dependency/prompt/data input binding mismatch')
        if any(self.input_artifacts.get(entry.path) != entry.sha256 for entry in snapshot.files):
            raise ValueError('snapshot file input binding missing or mismatched')
        for ref, digest in list(self.input_artifacts.items()) + list(self.output_artifacts.items()):
            value = resolve_artifact(ref)
            if type(value) is not bytes or sha256(value).hexdigest() != digest:
                raise ValueError('artifact bytes/hash mismatch')
