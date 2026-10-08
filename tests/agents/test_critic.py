from dataclasses import FrozenInstanceError, replace
import json

import pytest

from quant_rsi.agents.critic import CriticReport, Issue, ReviewIdentity, admit, review
from quant_rsi.contracts.research import Candidate, Evidence


@pytest.fixture
def inputs():
    candidate = Candidate('CAN-one', 'EXP-one', 'FAM-one', 'RUN-author',
                          'synthetic/output', 'a'*64, 'b'*64, 'ATT-one')
    evidence = Evidence('EVD-one', 'EXP-one', 'CAN-one', {'synthetic_metric': 1},
                        'synthetic/output', 'a'*64)
    author = ReviewIdentity('ACT-author', 'CTX-author', 'RUN-author', 'candidate_author')
    critic = ReviewIdentity('ACT-critic', 'CTX-critic', 'RUN-critic', 'critic')
    return candidate, [evidence], dict(author=author, critic=critic)


def test_canonical_report_admission_and_read_only(inputs):
    candidate, evidence, identities = inputs
    before = (candidate.to_dict(), evidence[0].to_dict())
    report = review(candidate, evidence, **identities)
    restored = CriticReport.from_dict(json.loads(json.dumps(report.to_dict())))
    assert admit(restored, candidate, evidence, **identities)
    assert restored == report and restored.content_digest() == report.content_digest()
    assert (candidate.to_dict(), evidence[0].to_dict()) == before
    with pytest.raises(FrozenInstanceError):
        report.review_status = 'BLOCK'
    with pytest.raises(TypeError):
        report.evidence_digests['EVD-one'] = 'f'*64
    with pytest.raises(ValueError):
        CriticReport.from_dict({**report.to_dict(), 'verdict': 'PASS'})


@pytest.mark.parametrize('field', ['actor_id', 'context_id', 'run_id', 'role'])
def test_self_review_denied(inputs, field):
    candidate, evidence, identities = inputs
    identities['critic'] = replace(identities['critic'], **{field: getattr(identities['author'], field)})
    with pytest.raises(ValueError, match='independent'):
        review(candidate, evidence, **identities)


@pytest.mark.parametrize('severity,allowed', [('P0', False), ('P1', False), ('P2', True), ('P3', True)])
def test_evidence_backed_issues_and_serious_block(inputs, severity, allowed):
    candidate, evidence, identities = inputs
    issue = Issue('ISS-one', severity, ('EVD-one',), 'Synthetic evidence discrepancy', 'Supply corrected evidence')
    report = review(candidate, evidence, issues=(issue,), **identities)
    assert admit(report, candidate, evidence, **identities) is allowed
    assert CriticReport.from_dict(report.to_dict()) == report
    if not allowed:
        with pytest.raises(ValueError, match='serious'):
            replace(report, review_status='ADMIT')


def test_missing_and_oral_only_evidence_block(inputs):
    candidate, evidence, identities = inputs
    for supplied in ([], [replace(evidence[0], metrics={'synthetic_metric': None},
                                 source_artifact_ref=None, source_artifact_hash=None, notes='looks good')]):
        report = review(candidate, supplied, **identities)
        assert report.review_status == 'BLOCK'
        assert not admit(report, candidate, supplied, **identities)
    assert not admit('looks good', candidate, evidence, **identities)


def test_report_binds_candidate_all_evidence_and_reviewer(inputs):
    candidate, evidence, identities = inputs
    report = review(candidate, evidence, **identities)
    assert not admit(report, replace(candidate, code_hash='f'*64), evidence, **identities)
    assert not admit(report, candidate, [], **identities)
    assert not admit(report, candidate, [replace(evidence[0], metrics={'synthetic_metric': 2})], **identities)
    assert not admit(report, candidate, evidence+[replace(evidence[0], evidence_id='EVD-two')], **identities)
    for who in ('author', 'critic'):
        changed = {**identities, who: replace(identities[who], actor_id='ACT-third')}
        assert not admit(report, candidate, evidence, **changed)


@pytest.mark.parametrize('changes', [dict(candidate_id='CAN-other'), dict(experiment_id='EXP-other'),
                                     dict(source_artifact_hash='f'*64), dict(source_artifact_ref='other')])
def test_evidence_misbindings_rejected(inputs, changes):
    candidate, evidence, identities = inputs
    with pytest.raises(ValueError, match='mismatch'):
        review(candidate, [replace(evidence[0], **changes)], **identities)


def test_issue_references_and_duplicates_fail_closed(inputs):
    candidate, evidence, identities = inputs
    issue = Issue('ISS-one', 'P1', ('EVD-missing',), 'Concern', 'Repair')
    with pytest.raises(ValueError, match='unreviewed'):
        review(candidate, evidence, issues=(issue,), **identities)
    with pytest.raises(ValueError, match='duplicate evidence'):
        review(candidate, evidence*2, **identities)
    issue = replace(issue, evidence_refs=('EVD-one',))
    with pytest.raises(ValueError, match='duplicate issue'):
        review(candidate, evidence, issues=(issue, issue), **identities)
    with pytest.raises(ValueError):
        replace(issue, evidence_refs=())


def test_author_run_and_role_bound_to_candidate(inputs):
    candidate, evidence, identities = inputs
    for change in (dict(run_id='RUN-other'), dict(role='observer')):
        with pytest.raises(ValueError):
            review(candidate, evidence, **{**identities, 'author': replace(identities['author'], **change)})


def test_evidence_order_is_canonical_and_resolution_requires_new_report(inputs):
    candidate, evidence, identities = inputs
    evidence.append(replace(evidence[0], evidence_id='EVD-two'))
    clean = review(candidate, evidence, **identities)
    assert review(candidate, list(reversed(evidence)), **identities).content_digest() == clean.content_digest()
    issue = Issue('ISS-one', 'P1', ('EVD-one',), 'Concern', 'Provide repaired evidence')
    blocked = review(candidate, evidence, issues=(issue,), **identities)
    assert blocked.content_digest() != clean.content_digest()
    assert not admit(blocked, candidate, evidence, **identities)
