"""Unique B2 EvalResult contract. Engineering acceptance is not promotion."""
from dataclasses import dataclass
from collections.abc import Mapping

from .condition import _json_value
from .research import _Contract, _hash, _id, _text, _timestamp

GATES = tuple('G'+str(i) for i in range(8))
BLOCK_REASONS = {'G4': 'D04B_NOT_FROZEN', 'G6': 'BENCHMARK_GRADE_SEALED_INFRASTRUCTURE_ABSENT'}


@dataclass(frozen=True)
class EvalResult(_Contract):
    eval_result_id: str
    task_id: str
    condition_hash: str
    benchmark_run_id: str
    scientific_family_id: str
    attempt_id: str
    candidate_id: str
    evaluator_version: str
    evaluator_artifact_ref: str
    evaluator_artifact_hash: str
    gates: Mapping
    evidence_refs: Mapping
    strategy_metrics: Mapping
    research_behavior_metrics: Mapping
    critic_report_ref: str
    artifact_hashes: Mapping
    budget_usage_ref: str
    created_at: str
    formal_verdict: str = 'BLOCKED'
    attestation: str = 'UNSIGNED_SYNTHETIC'
    signature: str | None = None

    def __post_init__(self):
        for key in ('eval_result_id','task_id','benchmark_run_id','scientific_family_id','attempt_id','candidate_id'):
            _id(getattr(self,key),key)
        for key in ('condition_hash','evaluator_artifact_hash'):
            _hash(getattr(self,key))
        for key in ('evaluator_version','evaluator_artifact_ref','critic_report_ref','budget_usage_ref'):
            _text(getattr(self,key),key)
        if set(self.gates) != set(GATES):
            raise ValueError('G0-G7 are all required; no configurable exclusions')
        for name,result in self.gates.items():
            if set(result) != {'status','reason','scope'} or result['status'] not in ('PASS','FAIL','BLOCK'):
                raise ValueError('explicit gate status, reason and scope required; no N/A')
            _text(result['reason'],'gate reason'); _text(result['scope'],'gate scope')
        for gate,reason in BLOCK_REASONS.items():
            if self.gates[gate]['status'] != 'BLOCK' or self.gates[gate]['reason'] != reason:
                raise ValueError('B2 cannot override deferred protocol or sealed infrastructure')
        if self.formal_verdict != 'BLOCKED' or self.attestation != 'UNSIGNED_SYNTHETIC' or self.signature is not None:
            raise ValueError('B2 has no formal promotion or signing authority')
        for mapping in ('evidence_refs','artifact_hashes'):
            for ref,digest in getattr(self,mapping).items():
                _text(ref,'artifact ref'); _hash(digest)
        for key in ('gates','evidence_refs','strategy_metrics','research_behavior_metrics','artifact_hashes'):
            object.__setattr__(self,key,_json_value(getattr(self,key),freeze=True))
        object.__setattr__(self,'created_at',_timestamp(self.created_at))

    @property
    def engineering_conformance(self):
        return 'PASS' if all(self.gates[g]['status']=='PASS' for g in ('G0','G1','G2','G3','G5','G7')) else 'BLOCKED'
