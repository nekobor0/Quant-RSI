"""Read-only synthetic review. Identity trust is protocol trust, not OS auth."""
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from quant_rsi.contracts.research import Candidate, Evidence, _Contract, _hash, _id, _ids, _text


@dataclass(frozen=True)
class ReviewIdentity(_Contract):
    actor_id: str
    context_id: str
    run_id: str
    role: str

    def __post_init__(self):
        for name in ('actor_id', 'context_id', 'run_id'):
            _id(getattr(self, name), name)
        _text(self.role, 'role')


@dataclass(frozen=True)
class Issue(_Contract):
    id: str
    severity: str
    evidence_refs: tuple[str, ...]
    rationale: str
    resolution_requirement: str

    def __post_init__(self):
        _id(self.id, 'issue id')
        if self.severity not in ('P0', 'P1', 'P2', 'P3'):
            raise ValueError('severity must be P0/P1/P2/P3')
        object.__setattr__(self, 'evidence_refs', _ids(self.evidence_refs, 'evidence_refs', required=True))
        _text(self.rationale, 'rationale')
        _text(self.resolution_requirement, 'resolution_requirement')


@dataclass(frozen=True)
class CriticReport(_Contract):
    candidate_id: str
    candidate_digest: str
    evidence_digests: Mapping[str, str]
    author: ReviewIdentity
    critic: ReviewIdentity
    issues: tuple[Issue, ...]
    review_status: str

    def __post_init__(self):
        _id(self.candidate_id, 'candidate_id')
        _hash(self.candidate_digest)
        if not isinstance(self.evidence_digests, Mapping):
            raise ValueError('evidence digests must be an object')
        for ref, digest in self.evidence_digests.items():
            _id(ref, 'evidence ref')
            _hash(digest)
        object.__setattr__(self, 'evidence_digests', MappingProxyType(dict(self.evidence_digests)))
        _independent(self.author, self.critic)
        if not isinstance(self.issues, (tuple, list)) or any(type(i) is not Issue for i in self.issues):
            raise ValueError('Issue sequence required')
        object.__setattr__(self, 'issues', tuple(self.issues))
        if len({i.id for i in self.issues}) != len(self.issues):
            raise ValueError('duplicate issue ID')
        if any(not set(i.evidence_refs) <= set(self.evidence_digests) for i in self.issues):
            raise ValueError('issue references unreviewed evidence')
        if self.review_status not in ('ADMIT', 'BLOCK'):
            raise ValueError('invalid review status')
        if self.review_status == 'ADMIT' and (not self.evidence_digests
                or any(i.severity in ('P0', 'P1') for i in self.issues)):
            raise ValueError('evidence required and serious issues BLOCK')

    def to_dict(self):
        return dict(candidate_id=self.candidate_id, candidate_digest=self.candidate_digest,
                    evidence_digests=dict(self.evidence_digests), author=self.author.to_dict(),
                    critic=self.critic.to_dict(), issues=[i.to_dict() for i in self.issues],
                    review_status=self.review_status)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, Mapping):
            raise ValueError('report object required')
        data = dict(value)
        try:
            data['author'] = ReviewIdentity.from_dict(data['author'])
            data['critic'] = ReviewIdentity.from_dict(data['critic'])
            if not isinstance(data['issues'], (list, tuple)):
                raise ValueError('issues sequence required')
            data['issues'] = tuple(Issue.from_dict(i) for i in data['issues'])
            return cls(**data)
        except (KeyError, TypeError) as exc:
            raise ValueError('invalid report fields') from exc


def _independent(author, critic):
    if type(author) is not ReviewIdentity or type(critic) is not ReviewIdentity:
        raise ValueError('review identities required')
    if (author.role != 'candidate_author' or critic.role != 'critic'
            or any(getattr(author, name) == getattr(critic, name)
                   for name in ('actor_id', 'context_id', 'run_id'))):
        raise ValueError('independent actor/context/run and critic role required')


def review(candidate, evidence, *, author, critic, issues=()):
    """Bind every supplied evidence object; never read hidden labels or write gates."""
    _independent(author, critic)
    if type(candidate) is not Candidate or author.run_id != candidate.benchmark_run_id:
        raise ValueError('candidate author run mismatch')
    if not isinstance(evidence, (tuple, list)) or any(type(e) is not Evidence for e in evidence):
        raise ValueError('Evidence sequence required')
    digests = {}
    supported = bool(evidence) and candidate.kind in ('STRATEGY', 'PUBLIC_FIXTURE')
    for item in evidence:
        if item.evidence_id in digests:
            raise ValueError('duplicate evidence ID')
        if (item.candidate_id, item.experiment_id) != (candidate.candidate_id, candidate.experiment_id):
            raise ValueError('evidence candidate/experiment mismatch')
        if item.source_artifact_ref is not None and (
                item.source_artifact_ref, item.source_artifact_hash) != (
                candidate.artifact_ref, candidate.artifact_hash):
            raise ValueError('evidence artifact mismatch')
        supported = supported and (item.source_artifact_ref is not None and (
            (candidate.kind == 'STRATEGY' and item.kind == 'MEASURED_STRATEGY'
             and any(v is not None for v in item.metrics.values()))
            or (candidate.kind == 'PUBLIC_FIXTURE' and item.kind == 'PUBLIC_FIXTURE'
                and all(v is None for v in item.metrics.values()))))
        digests[item.evidence_id] = item.content_digest()
    if not isinstance(issues, (tuple, list)) or any(type(i) is not Issue for i in issues):
        raise ValueError('Issue sequence required')
    status = 'ADMIT' if supported and not any(i.severity in ('P0', 'P1') for i in issues) else 'BLOCK'
    return CriticReport(candidate.candidate_id, candidate.content_digest(), digests,
                        author, critic, tuple(issues), status)


def admit(report, candidate, evidence, *, author, critic):
    """Admission is only review binding, not evidence authenticity or evaluator PASS."""
    if type(report) is not CriticReport:
        return False
    try:
        expected = review(candidate, evidence, author=author, critic=critic, issues=report.issues)
    except ValueError:
        return False
    return report.review_status == 'ADMIT' and report.to_dict() == expected.to_dict()
