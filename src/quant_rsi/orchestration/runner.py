"""Bounded synthetic coordinator; canonical budget and trace own execution state."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import sys

from quant_rsi.agents.worker import FakeProvider, WorkerRequest, invoke
from quant_rsi.agents.critic import CriticReport, admit, review
from quant_rsi.contracts.condition import AgentBenchmarkRun, BenchmarkCondition, load_decisions
from quant_rsi.contracts.data import DataSpec, SnapshotManifest
from quant_rsi.contracts.evaluation import EvalResult
from quant_rsi.contracts.manifest import RunManifest
from quant_rsi.contracts.research import Candidate, Evidence, _id
from quant_rsi.data.pit import PITView, canonical_bytes
from quant_rsi.env.daily import simulate
from quant_rsi.eval.gates import evaluate, evaluate_public
from quant_rsi.eval.replay import TOOL_VERSIONS
from quant_rsi.ledger.budget import BudgetDenied, SearchBudget


def _digest(raw):
    return sha256(raw).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _authorize(task):
    task.authorize_dispatch()
    activation = load_decisions().get('activation', {}).get('stage_B2', {})
    if (activation.get('authorized') is not True
            or activation.get('mode') != 'SYNTHETIC_AGENT_EVALUATOR_ONLY'
            or 'W14' not in activation.get('authorized_work_items', ())):
        raise ValueError('current Stage B2 dispatch not authorized')


def _empty(status):
    return dict(status=status, manifest=None, candidate=None, evidence=None,
                result=None, critic_report=None, eval_result=None)


def _restore(payload, artifacts):
    for ref, digest in payload['artifact_hashes'].items():
        if _digest(artifacts[ref]) != digest:
            raise ValueError('archived delivery artifact digest mismatch')
    result = _empty(payload['status'])
    classes = dict(manifest=RunManifest, candidate=Candidate, evidence=Evidence,
                   critic_report=CriticReport, eval_result=EvalResult)
    for key, ref in payload['refs'].items():
        value = json.loads(artifacts[ref])
        result[key] = classes[key].from_dict(value) if key in classes else value
    return result


def run_once(*, budget, run_id, experiment_id, delivery_id, attempt_id,
             scientific_variant_id, candidate_id, evidence_id, manifest_id,
             envelope, request, provider, artifacts, author, critic, issues=(),
             retry_of=None):
    """Execute one frozen operation, never retune/retry on evaluator feedback.

    An interrupted claimed delivery blocks redelivery. Only the custodian can
    establish quiescence and recover its reservation using the canonical budget.
    Inputs/identities are trusted-supervisor bindings, not OS authentication.
    """
    if type(budget) is not SearchBudget or type(provider) is not FakeProvider or type(request) is not WorkerRequest:
        raise ValueError('canonical budget and exact fake worker contracts required')
    for value in (run_id, experiment_id, delivery_id, attempt_id, scientific_variant_id,
                  candidate_id, evidence_id, manifest_id):
        _id(value, 'dispatch identity')
    inputs = {ref: artifacts[ref] for ref in request.input_hashes}
    input_hashes = {ref: _digest(raw) for ref, raw in inputs.items()}
    if input_hashes != dict(request.input_hashes):
        raise ValueError('request input artifact mismatch')
    fingerprint = _digest(canonical_bytes(dict(
        run_id=run_id, experiment_id=experiment_id, delivery_id=delivery_id,
        attempt_id=attempt_id, scientific_variant_id=scientific_variant_id,
        candidate_id=candidate_id, evidence_id=evidence_id, manifest_id=manifest_id,
        envelope=dict(envelope), request=request.to_dict(), provider=provider.to_dict(),
        input_hashes=input_hashes, author=author.to_dict(), critic=critic.to_dict(),
        issues=[i.to_dict() for i in issues], retry_of=retry_of)))
    store = budget.store
    with store.transaction() as tx:
        events = tx.events()
        by_id = {e['event_id']: e for e in events}
        prior = by_id.get('delivery:' + delivery_id)
        if prior:
            if prior['payload']['fingerprint'] != fingerprint:
                raise ValueError('delivery fingerprint mismatch')
            archived = by_id.get('archive:' + delivery_id)
            return _restore(archived['payload'], artifacts) if archived else _empty('IN_FLIGHT_BLOCKED')
        run = AgentBenchmarkRun.from_dict(by_id['run:' + run_id]['payload'])
        condition = BenchmarkCondition.from_dict(by_id['condition:' + run.condition_hash]['payload'])
        task = condition.task
        if (request.run_id != run_id or author.run_id != run_id
                or (request.actor_id, request.context_id) != (author.actor_id, author.context_id)
                or author.role != 'candidate_author' or critic.role != 'critic'
                or any(getattr(author, k) == getattr(critic, k) for k in ('actor_id', 'context_id', 'run_id'))):
            raise ValueError('author/worker/critic identity mismatch')
        if (request.model_id, request.model_version, request.provider, request.prompt_hash) != (
                run.agent_model, run.agent_model_version, run.provider, run.prompt_hash):
            raise ValueError('worker request differs from registered run')
        # Read roots from registered runs, never maintain a parallel counter.
        for event in events:
            if event['kind'] in ('DELIVERY_CLAIMED', 'ATTEMPT_STARTED'):
                other_id = event['payload'].get('run_id', event['payload'].get('benchmark_run_id'))
                other = by_id['run:' + other_id]['payload']
                if other['condition_hash'] == run.condition_hash and other['budget_root_run_id'] != run.budget_root_run_id:
                    raise ValueError('B2 forbids multiple budget roots for one frozen condition')
        if any(e['kind'] == 'DELIVERY_CLAIMED' and e['payload']['attempt_id'] == attempt_id for e in events):
            raise ValueError('attempt already claimed by another delivery')
        _authorize(task)
        tx.append('delivery:' + delivery_id, 'DELIVERY_CLAIMED', dict(
            fingerprint=fingerprint, run_id=run_id, attempt_id=attempt_id))

    outcome = _empty('FAILED')
    refs = {}
    archived_hashes = dict(input_hashes)

    def save(key, ref, value):
        raw = canonical_bytes(value.to_dict() if hasattr(value, 'to_dict') else value)
        if ref in artifacts and artifacts[ref] != raw:
            raise ValueError('immutable artifact reference collision')
        artifacts[ref] = raw
        refs[key] = ref
        archived_hashes[ref] = _digest(raw)
        outcome[key] = value

    def finish(status):
        outcome['status'] = status
        store.append('archive:' + delivery_id, 'DELIVERY_ARCHIVED', dict(
            fingerprint=fingerprint, status=status, refs=refs, artifact_hashes=archived_hashes))
        return outcome

    try:
        budget.reserve(run_id, attempt_id, envelope, scientific_variant_id=scientific_variant_id,
                       retry_of=retry_of, experiment_id=experiment_id)
    except BudgetDenied:
        return finish('BUDGET_EXHAUSTED')
    response = None
    outputs = {}
    try:
        _authorize(task)
        store.append('worker-binding:' + attempt_id, 'WORKER_DISPATCH_BOUND', dict(
            attempt_id=attempt_id, request=request.to_dict(), provider_digest=provider.content_digest()))
        response = invoke(request, provider, budget=budget, attempt_id=attempt_id)
        if response.status != 'SUCCEEDED' or response.actual_resources is None:
            status = 'TIMEOUT' if response.status == 'TIMEOUT' else 'FAILED'
            budget.settle(attempt_id, status, response.actual_resources,
                          failure=json.dumps(response.to_dict(), sort_keys=True))
            return finish(status)
        operation = json.loads(inputs['environment-input.json'])
        if (response.output != inputs['environment-input.json']
                or operation['operation'] != 'synthetic-daily-v1' or operation['comparison'] != 'exact'
                or response.randomness != operation['randomness']
                or (operation['randomness'] == 'fixed_seed_deterministic'
                    and (type(operation['seed']) is not int or operation['seed'] < 0))
                or (operation['randomness'] != 'fixed_seed_deterministic' and operation['seed'] is not None)):
            raise ValueError('worker output differs from supported frozen operation')
        data_ref, snapshot_ref = 'DATA-' + task.data_spec_hash, 'SNAPSHOT-' + task.snapshot_hash
        data = DataSpec.from_dict(json.loads(inputs[data_ref]))
        snapshot = SnapshotManifest.from_dict(json.loads(inputs[snapshot_ref]))
        result = simulate(task, PITView(task, data, snapshot, inputs.__getitem__), operation['environment'])
        output_ref = 'result-' + attempt_id + '.json'
        save('result', output_ref, result)
        digest = archived_hashes[output_ref]
        budget.record_output(attempt_id, candidate_id, output_ref, digest)
        outputs[output_ref] = digest
    except Exception as exc:
        budget.settle(attempt_id, 'FAILED', None if response is None else response.actual_resources,
                      artifact_hashes=outputs, failure=type(exc).__name__ + ': ' + str(exc))
        return finish('FAILED')


    budget.settle(attempt_id, 'SUCCEEDED', response.actual_resources, artifact_hashes=outputs)
    try:
        candidate = Candidate(candidate_id, experiment_id, run.scientific_family_id, run_id,
                              output_ref, digest, run.code_hash, attempt_id)
        evidence = Evidence(evidence_id, experiment_id, candidate_id,
                            {'synthetic_final_nav': float(result['ledger'][-1]['nav'])}, output_ref, digest)
        save('candidate', candidate_id, candidate)
        save('evidence', evidence_id, evidence)
        manifest = RunManifest(manifest_id, run_id, run.content_digest(), attempt_id, task.task_id,
            task.content_digest(), 'condition:' + condition.condition_hash, condition.condition_hash,
            run.scientific_family_id, data_ref, snapshot_ref,
            {candidate_id: candidate.content_digest()}, {evidence_id: evidence.content_digest()},
            input_hashes, outputs, 'prompt.txt', 'code-tree.json', 'dependencies.json', sys.version,
            TOOL_VERSIONS, operation['randomness'], operation['seed'],
            {e['event_id']: e['event_hash'] for e in store.read()}, _now())
        save('manifest', manifest_id, manifest)
        store.append('manifest:' + attempt_id, 'EXECUTION_MANIFEST_COMPLETED', dict(
            manifest_ref=manifest_id, manifest_digest=manifest.manifest_digest, attempt_id=attempt_id))
        try:
            report = review(candidate, [evidence], author=author, critic=critic, issues=issues)
            save('critic_report', 'critic:' + report.content_digest(), report)
            admitted = admit(report, candidate, [evidence], author=author, critic=critic)
            reason = report.review_status
        except ValueError as exc:
            admitted, reason = False, str(exc)
        store.append('admission:' + attempt_id, 'ADMISSION_GRANTED' if admitted else 'ADMISSION_BLOCKED',
                     dict(attempt_id=attempt_id, candidate_id=candidate_id, reason=reason,
                     candidate_digest=candidate.content_digest(), evidence_digests={evidence_id: evidence.content_digest()},
                     manifest_digest=manifest.manifest_digest, critic_report_ref=refs.get('critic_report'),
                     critic_report_digest=outcome['critic_report'].content_digest() if outcome['critic_report'] is not None else None))
        if not admitted:
            return finish('ADMISSION_BLOCKED')
        evaluation = evaluate(manifest, expected_manifest_digest=manifest.manifest_digest,
            trace_store=store, resolve_artifact=artifacts.__getitem__, critic_report=report,
            author=author, critic=critic, created_at=_now())
        save('eval_result', evaluation.eval_result_id, evaluation)
        store.append('evaluation:' + attempt_id, 'EVALUATION_COMPLETED', dict(
            attempt_id=attempt_id, eval_result_ref=evaluation.eval_result_id,
            eval_result_digest=evaluation.content_digest(), manifest_digest=manifest.manifest_digest))
        return finish('EVALUATED')
    except Exception as exc:
        # Compute is already settled. Preserve delivery failure separately.
        store.append('delivery-failure:' + delivery_id, 'DELIVERY_FAILED', dict(
            attempt_id=attempt_id, delivery_id=delivery_id,
            failure=type(exc).__name__ + ': ' + str(exc),
            partial_refs=dict(refs), artifact_hashes=dict(archived_hashes)))
        return finish('FAILED')

def run_public_once(*, budget, run_id, experiment_id, attempt_id, candidate_id,
                    evidence_id, manifest_id, envelope, request, provider, artifacts,
                    author, critic, issues=()):
    """Canonical public-fixture path; every reserved response keeps one denominator."""
    if type(budget) is not SearchBudget or type(provider) is not FakeProvider or type(request) is not WorkerRequest:
        raise ValueError('canonical budget and fake provider required')
    for identity in (run_id, experiment_id, attempt_id, candidate_id, evidence_id, manifest_id):
        _id(identity, 'public dispatch identity')
    store = budget.store
    by_id = {e['event_id']: e for e in store.read()}
    run = AgentBenchmarkRun.from_dict(by_id['run:' + run_id]['payload'])
    condition = BenchmarkCondition.from_dict(by_id['condition:' + run.condition_hash]['payload'])
    task = condition.task
    _authorize(task)
    if (task.evaluator_version != 'C2-public-v1' or request.run_id != run_id
            or author.run_id != run_id or author.role != 'candidate_author' or critic.role != 'critic'
            or any(getattr(author, k) == getattr(critic, k) for k in ('actor_id', 'context_id', 'run_id'))
            or (request.actor_id, request.context_id) != (author.actor_id, author.context_id)
            or (request.model_id, request.model_version, request.provider, request.prompt_hash) != (
                run.agent_model, run.agent_model_version, run.provider, run.prompt_hash)
            or envelope['candidate_trials'] != 0
            or any(_digest(artifacts[ref]) != digest for ref, digest in request.input_hashes.items())):
        raise ValueError('public run, identity, inputs and zero-trial budget must match')
    budget.reserve(run_id, attempt_id, envelope, experiment_id=experiment_id)
    store.append('worker-binding:' + attempt_id, 'WORKER_DISPATCH_BOUND', dict(
        attempt_id=attempt_id, request=request.to_dict(), provider_digest=provider.content_digest()))
    response = invoke(request, provider, budget=budget, attempt_id=attempt_id)
    output_ref = 'public-output-' + attempt_id + '.json'
    output_raw = canonical_bytes({'response_hex': response.output.hex(), 'response_status': response.status})
    if output_ref in artifacts:
        raise ValueError('public output artifact reference already exists')
    artifacts[output_ref] = output_raw
    digest = _digest(output_raw)
    budget.record_output(attempt_id, candidate_id, output_ref, digest, kind='PUBLIC_FIXTURE')
    status = 'TIMEOUT' if response.status == 'TIMEOUT' else ('SUCCEEDED' if response.status == 'SUCCEEDED' else 'FAILED')
    budget.settle(attempt_id, status, response.actual_resources, artifact_hashes={output_ref: digest},
                  failure=None if status == 'SUCCEEDED' else response.status)

    candidate = Candidate(candidate_id, experiment_id, run.scientific_family_id, run_id,
                          output_ref, digest, run.code_hash, attempt_id, kind='PUBLIC_FIXTURE')
    evidence = Evidence(evidence_id, experiment_id, candidate_id,
                        {'public_fixture_observed': None}, output_ref, digest, kind='PUBLIC_FIXTURE')
    artifacts[candidate_id] = canonical_bytes(candidate.to_dict())
    artifacts[evidence_id] = canonical_bytes(evidence.to_dict())
    data_ref, snapshot_ref = 'DATA-' + task.data_spec_hash, 'SNAPSHOT-' + task.snapshot_hash
    operation = json.loads(artifacts['public-input.json'])
    inputs = {ref: _digest(raw) for ref, raw in artifacts.items()
              if ref in (data_ref, snapshot_ref, 'prompt.txt', 'code-tree.json',
                         'dependencies.json', 'public-input.json')}
    manifest = RunManifest(manifest_id, run_id, run.content_digest(), attempt_id, task.task_id,
        task.content_digest(), 'condition:' + condition.condition_hash, condition.condition_hash,
        run.scientific_family_id, data_ref, snapshot_ref,
        {candidate_id: candidate.content_digest()}, {evidence_id: evidence.content_digest()},
        inputs, {output_ref: digest}, 'prompt.txt', 'code-tree.json', 'dependencies.json',
        sys.version, TOOL_VERSIONS, 'fixed_seed_deterministic', 0,
        {e['event_id']: e['event_hash'] for e in store.read()}, _now())
    artifacts[manifest_id] = canonical_bytes(manifest.to_dict())
    store.append('manifest:' + attempt_id, 'EXECUTION_MANIFEST_COMPLETED', dict(
        manifest_ref=manifest_id, manifest_digest=manifest.manifest_digest, attempt_id=attempt_id))
    report = review(candidate, [evidence], author=author, critic=critic, issues=issues)
    report_ref = 'critic:' + report.content_digest()
    artifacts[report_ref] = canonical_bytes(report.to_dict())
    admitted = admit(report, candidate, [evidence], author=author, critic=critic)
    store.append('admission:' + attempt_id, 'ADMISSION_GRANTED' if admitted else 'ADMISSION_BLOCKED',
        dict(attempt_id=attempt_id, candidate_id=candidate_id, reason=report.review_status,
             candidate_digest=candidate.content_digest(), evidence_digests={evidence_id: evidence.content_digest()},
             manifest_digest=manifest.manifest_digest, critic_report_ref=report_ref,
             critic_report_digest=report.content_digest()))
    evaluation = evaluate_public(manifest, expected_manifest_digest=manifest.manifest_digest,
        trace_store=store, resolve_artifact=artifacts.__getitem__, critic_report=report,
        author=author, critic=critic, created_at=_now())
    artifacts[evaluation.eval_result_id] = canonical_bytes(evaluation.to_dict())
    store.append('evaluation:' + attempt_id, 'EVALUATION_COMPLETED', dict(
        attempt_id=attempt_id, eval_result_ref=evaluation.eval_result_id,
        eval_result_digest=evaluation.content_digest(), manifest_digest=manifest.manifest_digest))
    return dict(status='EVALUATED', candidate=candidate, evidence=evidence, manifest=manifest,
                critic_report=report, eval_result=evaluation, response=response, public_release=operation)
