"""Synthetic governance fixtures only; no market measurements."""

from dataclasses import FrozenInstanceError, replace
import json

import pytest

from quant_rsi.contracts.research import (
    Candidate, ConceptMapping, Evidence, ExperimentSpec, Hypothesis,
    ScientificSearchFamily, family_ancestry, index_by_id, validate_research_links,
)


HASH = "a" * 64


@pytest.fixture
def registry(tmp_path):
    mapping = ConceptMapping("map-1", "Synthetic mechanism", "Synthetic observable",
                             "Synthetic proxy", ["feature-1"])
    hypothesis = Hypothesis("hyp-1", "claim-1", "Synthetic feature predicts positive test output",
                            "Nonpositive test output falsifies the claim", "map-1")
    family = ScientificSearchFamily("family-1", "claim-1", "Final synthetic claim selection")
    spec = ExperimentSpec("exp-1", "hyp-1", "task-1", "data-1", "cost-1", "stats-1",
                          "family-1", "run-1", "2026-09-01T00:00:00Z")
    candidate = Candidate("candidate-1", "exp-1", "family-1", "run-1",
                          "synthetic/result", HASH, HASH, "attempt-1")
    evidence = Evidence("evidence-1", "exp-1", "candidate-1", {"test_metric": None},
                        notes="Synthetic fixture; outcome unknown")
    from quant_rsi.ledger.store import TraceStore
    trace = TraceStore(tmp_path/'research.sqlite')
    for kind, obj, key in [('CONCEPT_REGISTERED', mapping, 'concept_mapping_id'),
                           ('HYPOTHESIS_REGISTERED', hypothesis, 'hypothesis_id'),
                           ('FAMILY_REGISTERED', family, 'scientific_family_id'),
                           ('EXPERIMENT_REGISTERED', spec, 'experiment_id')]:
        trace.append(getattr(obj, key), kind, obj.to_dict())
    trace.append('run:run-1', 'RUN_REGISTERED', dict(benchmark_run_id='run-1', code_hash=HASH, condition_hash=HASH))
    trace.append('attempt:attempt-1', 'ATTEMPT_STARTED', dict(attempt_id='attempt-1', experiment_id='exp-1',
        benchmark_run_id='run-1', scientific_family_id='family-1', condition_hash=HASH))
    trace.append('output:candidate-1', 'ATTEMPT_OUTPUT', dict(attempt_id='attempt-1', candidate_id='candidate-1',
        artifact_ref='synthetic/result', artifact_hash=HASH, kind='STRATEGY'))
    trace.append('settle:attempt-1', 'ATTEMPT_SETTLED', dict(attempt_id='attempt-1', status='SUCCEEDED',
        artifact_hashes={'synthetic/result': HASH}))
    return dict(trace_store=trace, concept_mappings=[mapping], hypotheses=[hypothesis], families=[family],
                experiments=[spec], candidates=[candidate], evidence=[evidence],
                benchmark_run_ids=["run-1"])


def test_valid_registry_and_json_roundtrips(registry):
    validate_research_links(**registry)
    for name, values in registry.items():
        if name in ("benchmark_run_ids", "trace_store"):
            continue
        obj = values[0]
        serialized = json.loads(json.dumps(obj.to_dict(), allow_nan=False))
        restored = type(obj).from_dict(serialized)
        assert restored == obj
        assert restored.content_digest() == obj.content_digest()
        assert len(obj.content_digest()) == 64
        with pytest.raises(FrozenInstanceError):
            setattr(obj, next(iter(obj.to_dict())), "changed")
        with pytest.raises(ValueError, match="unknown"):
            type(obj).from_dict({**serialized, "verdict": "PASS"})
        serialized.pop(next(iter(serialized)))
        with pytest.raises(ValueError):
            type(obj).from_dict(serialized)


def test_nested_freeze_and_digest(registry):
    features = ["feature-1"]
    mapping = replace(registry["concept_mappings"][0], feature_refs=features)
    features.append("feature-2")
    assert mapping.feature_refs == ("feature-1",)
    metrics = {"test_metric": None}
    evidence = replace(registry["evidence"][0], metrics=metrics)
    before = evidence.content_digest()
    metrics["test_metric"] = 10
    evidence.to_dict()["metrics"]["test_metric"] = 20
    assert evidence.metrics["test_metric"] is None
    assert evidence.content_digest() == before
    with pytest.raises(TypeError):
        evidence.metrics["test_metric"] = 30
    assert replace(evidence, notes="Different note").content_digest() != before


@pytest.mark.parametrize("bad", ["", "  ", "x", "ab", "id space", "a" * 129, 123, True])
def test_invalid_ids(registry, bad):
    with pytest.raises(ValueError):
        replace(registry["hypotheses"][0], hypothesis_id=bad)


def test_id_boundaries_and_single_claim(registry):
    for value in ("abc", "a" * 128):
        replace(registry["hypotheses"][0], hypothesis_id=value)
    for value in (["claim one", "claim two"], "", " "):
        with pytest.raises(ValueError):
            replace(registry["hypotheses"][0], claim=value)
    with pytest.raises(ValueError):
        replace(registry["hypotheses"][0], falsification_condition="")
    for features in ([], ["feature-1", "feature-1"], "feature-1"):
        with pytest.raises(ValueError):
            replace(registry["concept_mappings"][0], feature_refs=features)


@pytest.mark.parametrize("bad", [None, "", "2026-09-01", "2026-09-01T00:00:00", "invalid"])
def test_preregistration_required(registry, bad):
    with pytest.raises(ValueError):
        replace(registry["experiments"][0], preregistered_at=bad)


@pytest.mark.parametrize("started", ["2026-09-01T00:00:00Z", "2026-08-31T23:59:59Z",
                                     "2026-09-01T08:00:00+08:00"])
def test_registration_strictly_before_execution(registry, started):
    with pytest.raises(ValueError, match="precede"):
        replace(registry["experiments"][0], execution_started_at=started)


def test_timestamp_normalization_and_unexecuted_spec(registry):
    spec = registry["experiments"][0]
    assert replace(spec, preregistered_at="2026-09-01T08:00:00+08:00").content_digest() == spec.content_digest()
    registry["experiments"] = [replace(spec, execution_started_at=None)]
    validate_research_links(**registry)
    registry["evidence"] = [replace(registry["evidence"][0], metrics={"test_metric": 0},
                                    source_artifact_ref="synthetic/result", source_artifact_hash=HASH)]
    validate_research_links(**registry)
    with pytest.raises(ValueError, match="execution trace"):
        validate_research_links(**dict(registry, trace_store=None))


@pytest.mark.parametrize("value", [0, -1, 1.25, -0.0, 1e308])
def test_finite_measurement_requires_provenance(registry, value):
    obj = registry["evidence"][0]
    with pytest.raises(ValueError, match="require source"):
        replace(obj, metrics={"test_metric": value})
    measured = replace(obj, metrics={"test_metric": value},
                       source_artifact_ref="synthetic/result", source_artifact_hash=HASH)
    assert Evidence.from_dict(json.loads(json.dumps(measured.to_dict()))) == measured
    registry["evidence"] = [measured]
    validate_research_links(**registry)


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), -float("inf"),
                                   "Narrative says it works", [], {}, 10 ** 400])
def test_invalid_metric(registry, value):
    with pytest.raises(ValueError):
        replace(registry["evidence"][0], metrics={"test_metric": value},
                source_artifact_ref="synthetic/result", source_artifact_hash=HASH)


@pytest.mark.parametrize("value", ["a" * 63, "a" * 65, "g" * 64, "A" * 64, "", None, True])
def test_invalid_hashes(registry, value):
    with pytest.raises(ValueError):
        replace(registry["candidates"][0], artifact_hash=value)
    with pytest.raises(ValueError):
        replace(registry["evidence"][0], metrics={"test_metric": 0},
                source_artifact_ref="synthetic/result", source_artifact_hash=value)


def test_partial_provenance_and_narrative_unknown(registry):
    obj = registry["evidence"][0]
    for kwargs in ({"source_artifact_ref": "synthetic/result"}, {"source_artifact_hash": HASH},
                   {"metrics": {}}, {"metrics": {" ": None}}):
        with pytest.raises(ValueError):
            replace(obj, **kwargs)
    assert obj.to_dict()["metrics"] == {"test_metric": None}


def test_duplicate_ids(registry):
    obj = registry["experiments"][0]
    with pytest.raises(ValueError, match="duplicate"):
        index_by_id([obj, replace(obj, task_id="task-2")], "experiment_id")
    registry["experiments"].append(obj)
    with pytest.raises(ValueError, match="duplicate"):
        validate_research_links(**registry)


@pytest.mark.parametrize("collection,field,value", [
    ("hypotheses", "concept_mapping_id", "missing-mapping"),
    ("experiments", "hypothesis_id", "missing-hypothesis"),
    ("experiments", "scientific_family_id", "missing-family"),
    ("experiments", "benchmark_run_id", "missing-run"),
    ("families", "claim_id", "missing-claim"),
    ("candidates", "experiment_id", "unregistered-experiment"),
    ("candidates", "scientific_family_id", "wrong-family"),
    ("candidates", "benchmark_run_id", "wrong-run"),
    ("evidence", "experiment_id", "unregistered-experiment"),
    ("evidence", "candidate_id", "missing-candidate"),
])
def test_broken_links(registry, collection, field, value):
    registry[collection] = [replace(registry[collection][0], **{field: value})]
    with pytest.raises(ValueError):
        validate_research_links(**registry)


def test_evidence_wrong_registered_experiment(registry):
    registry["experiments"].append(replace(registry["experiments"][0], experiment_id="exp-2"))
    registry["evidence"] = [replace(registry["evidence"][0], experiment_id="exp-2")]
    with pytest.raises(ValueError, match="mismatch"):
        validate_research_links(**registry)


def test_family_diamond_union_and_immutable_parents(registry):
    root = registry["families"][0]
    left = replace(root, scientific_family_id="family-left", parent_family_ids=["family-1"])
    right = replace(root, scientific_family_id="family-right", parent_family_ids=["family-1"])
    parents = ["family-left", "family-right"]
    merged = replace(root, scientific_family_id="family-merged", parent_family_ids=parents)
    parents.clear()
    families = [root, left, right, merged]
    assert family_ancestry("family-merged", families) == frozenset(
        ["family-1", "family-left", "family-right", "family-merged"])
    registry["families"] = families
    for obj in families[1:]:
        registry['trace_store'].append(obj.scientific_family_id, 'FAMILY_REGISTERED', obj.to_dict())
    validate_research_links(**registry)
    assert "budget_root_run_id" not in merged.to_dict()
    assert "capability_score" not in merged.to_dict()


def test_family_invalid_ancestry(registry):
    root = registry["families"][0]
    for parents in (["family-1"], ["family-2", "family-2"], "family-2"):
        with pytest.raises(ValueError):
            replace(root, parent_family_ids=parents)
    missing = replace(root, parent_family_ids=["family-missing"])
    with pytest.raises(ValueError, match="unregistered"):
        family_ancestry("family-1", [missing])
    cyclic = replace(root, parent_family_ids=["family-2"])
    child = replace(root, scientific_family_id="family-2", parent_family_ids=["family-1"])
    with pytest.raises(ValueError, match="cyclic"):
        family_ancestry("family-1", [cyclic, child])


def test_cross_claim_parents_preserved(registry):
    root = registry["families"][0]
    registry["hypotheses"].append(replace(registry["hypotheses"][0], hypothesis_id="hyp-2", claim_id="claim-2"))
    descendant = replace(root, scientific_family_id="family-2", claim_id="claim-2",
                         parent_family_ids=["family-1"])
    registry["families"].append(descendant)
    registry['trace_store'].append('hyp-2', 'HYPOTHESIS_REGISTERED', registry['hypotheses'][-1].to_dict())
    registry['trace_store'].append('family-2', 'FAMILY_REGISTERED', descendant.to_dict())
    validate_research_links(**registry)
    assert "family-1" in family_ancestry("family-2", registry["families"])
    registry["experiments"] = [replace(registry["experiments"][0], scientific_family_id="family-2")]
    with pytest.raises(ValueError, match="claim"):
        validate_research_links(**registry)
