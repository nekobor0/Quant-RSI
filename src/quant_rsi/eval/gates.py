"""Deterministic, blocked-aware synthetic evaluator; never a worker/LLM judge."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

from quant_rsi.contracts.condition import BenchmarkCondition, AgentBenchmarkRun, validate_experiment_binding, validate_run_lineage
from quant_rsi.contracts.data import DataSpec, SnapshotManifest
from quant_rsi.contracts.research import Candidate, Evidence, ExperimentSpec
from quant_rsi.contracts.evaluation import EvalResult, GATES, BLOCK_REASONS
from quant_rsi.data.pit import PITView, canonical_bytes
from quant_rsi.env.daily import simulate
from quant_rsi.eval.replay import replay
from quant_rsi.ledger.budget import SearchBudget, _usage, _terminals

VERSION = 'B2-gates-v1'
PUBLIC_VERSION = 'C2-public-v1'


def pit_observations(task, data, snapshot, resolve_artifact, environment):
    view = PITView(task,data,snapshot,resolve_artifact)
    return [{'decision_at':o['decision_at'], 'visible':[
        {'source_id':r.data_spec.source_id, 'revision':r.data_spec.source_revision,
         'data_hash':r.data_spec.content_hash()} for r in view.at(o['decision_at'])]}
        for o in environment['orders']]


def evaluate(manifest, *, expected_manifest_digest, trace_store, resolve_artifact,
             critic_report, author, critic, created_at):
    """Input evidence is verified/recomputed. No caller gate list or verdict input.

    Trust boundary: registered contracts and bytes come from the custodian;
    this local process is not cryptographic identity or sealed isolation.
    """
    from quant_rsi.agents.critic import admit, CriticReport
    from quant_rsi.agents.worker import WorkerRequest, WorkerResponse
    before = trace_store.read()
    by_id = {e['event_id']:e for e in before}
    admission = by_id.get('admission:'+manifest.attempt_id, {})
    review_ref = admission.get('payload', {}).get('critic_report_ref')
    gates = {g:dict(status='BLOCK',reason='MISSING_OR_INVALID_EVIDENCE',scope='SYNTHETIC_ONLY') for g in GATES}
    for g,reason in BLOCK_REASONS.items():
        gates[g] = dict(status='BLOCK',reason=reason,scope='FORMAL_RESEARCH')
    def passed(g, reason): gates[g].update(status='PASS',reason=reason)
    def obj(ref, cls): return cls.from_dict(json.loads(resolve_artifact(ref)))
    candidates=[]; evidence=[]; condition=None; run=None
    try:
        if manifest.manifest_digest != expected_manifest_digest:
            raise ValueError('manifest digest differs from custodian pin')
        condition=BenchmarkCondition.from_dict(by_id[manifest.condition_ref]['payload'])
        task=condition.task
        run=AgentBenchmarkRun.from_dict(by_id['run:'+manifest.benchmark_run_id]['payload'])
        task.verify_frozen_condition(by_id[task.decision_snapshot_ref]['payload'])
        if task.mode!='SYNTHETIC' or task.evaluator_version!=VERSION:
            raise ValueError('unsupported evaluator version or mode')
        if (manifest.task_hash!=task.content_digest() or manifest.condition_hash!=condition.condition_hash
                or run.condition_hash!=condition.condition_hash or manifest.run_hash!=run.content_digest()):
            raise ValueError('task/condition/run mismatch')
        attempt=by_id['attempt:'+manifest.attempt_id]
        if attempt['kind']!='ATTEMPT_STARTED':raise ValueError('attempt not started')
        experiment=ExperimentSpec.from_dict(by_id['experiment:'+attempt['payload']['experiment_id']]['payload'])
        validate_experiment_binding(experiment,task,run)
        if experiment.execution_started_at is not None or datetime.fromisoformat(experiment.preregistered_at)>=datetime.fromisoformat(attempt['created_at']):
            raise ValueError('preregistration must precede execution')
        passed('G0','FROZEN_CONTRACT_AND_PREREGISTRATION_VERIFIED')
    except (ValueError,KeyError,TypeError,OSError):
        gates['G0'].update(status='FAIL',reason='CONTRACT_OR_VERSION_BINDING_INVALID')
    if gates['G0']['status']=='PASS':
        try:
            data=obj(manifest.data_spec_ref,DataSpec); snapshot=obj(manifest.snapshot_ref,SnapshotManifest)
            candidates=[obj(ref,Candidate) for ref in manifest.candidate_hashes]
            evidence=[obj(ref,Evidence) for ref in manifest.evidence_hashes]
            if len(candidates)!=1 or not evidence:raise ValueError('one candidate and evidence required')
            manifest.verify_bindings(trace_store=trace_store,condition=condition,run=run,data_spec=data,snapshot=snapshot,
                candidates=candidates,evidence=evidence,resolve_artifact=resolve_artifact)
            request=WorkerRequest.from_dict(by_id['worker-request:'+manifest.attempt_id]['payload']['request'])
            if (author.actor_id,author.context_id,author.run_id)!=(request.actor_id,request.context_id,request.run_id):
                raise ValueError('review author differs from canonical worker provenance')
            admitted = admission.get('payload', {})
            if (admission.get('kind')!='ADMISSION_GRANTED'
                    or admitted.get('attempt_id')!=manifest.attempt_id
                    or admitted.get('candidate_id')!=candidates[0].candidate_id
                    or admitted.get('candidate_digest')!=candidates[0].content_digest()
                    or admitted.get('evidence_digests')!=dict(manifest.evidence_hashes)
                    or admitted.get('manifest_digest')!=manifest.manifest_digest
                    or admitted.get('critic_report_digest')!=critic_report.content_digest()
                    or review_ref!='critic:'+critic_report.content_digest()):
                raise ValueError('canonical admission missing, blocked or bound to different review')
            report_bytes=resolve_artifact(review_ref)
            if (sha256(report_bytes).hexdigest()!=critic_report.content_digest()
                    or CriticReport.from_dict(json.loads(report_bytes))!=critic_report):
                raise ValueError('canonical critic report bytes missing or mismatched')
            if not admit(critic_report,candidates[0],evidence,author=author,critic=critic):
                raise ValueError('critic admission denied')
            passed('G7','CANONICAL_LINEAGE_AND_INDEPENDENT_ADMISSION_VERIFIED')
        except (ValueError,KeyError,TypeError,OSError):
            gates['G7']['reason']='LINEAGE_OR_ADMISSION_INVALID'
        try:
            budget=SearchBudget(trace_store)
            accounting=budget.capability_accounting(run.benchmark_run_id)
            if accounting['blocked'] or any(v>condition.task.budget_limits[k] for k,v in accounting['usage'].items()):
                raise ValueError('unknown usage or overspend')
            family=budget.scientific_accounting(run.scientific_family_id)
            effective_terminals=_terminals(before)
            runs=[AgentBenchmarkRun.from_dict(e['payload']) for e in before if e['kind']=='RUN_REGISTERED']
            for r in runs:validate_run_lineage(r,runs)
            for identity in family['attempt_ids']:
                a=by_id['attempt:'+identity]; terminal=by_id['settle:'+identity]
                a_run=next(r for r in runs if r.benchmark_run_id==a['payload']['benchmark_run_id'])
                if (a['payload']['budget_root_run_id']!=a_run.budget_root_run_id
                        or a['payload']['scientific_family_id']!=a_run.scientific_family_id):
                    raise ValueError('denominator identity escape')
                reconciliations=[e for e in before if e['kind']=='USAGE_RECONCILED' and e['payload']['attempt_id']==identity]
                if any(manifest.trace_refs.get(e['event_id'])!=e['event_hash'] for e in (a,terminal,*reconciliations)):
                    raise ValueError('family attempt/failure omitted from evidence')
                if effective_terminals[identity]['usage_state']!='KNOWN':raise ValueError('unresolved resources')
                worker_request=by_id.get('worker-request:'+identity)
                worker_response=by_id.get('worker-response:'+identity)
                if terminal['payload']['status']=='SUCCEEDED' or worker_request is not None:
                    if worker_request is None or worker_response is None:raise ValueError('worker provenance missing')
                    request=WorkerRequest.from_dict(worker_request['payload']['request'])
                    response=WorkerResponse.from_dict(worker_response['payload']['response'])
                    binding=by_id['worker-binding:'+identity]
                    if (request.run_id!=a_run.benchmark_run_id
                            or (request.model_id,request.model_version,request.provider,request.prompt_hash)!=(
                                a_run.agent_model,a_run.agent_model_version,a_run.provider,a_run.prompt_hash)
                            or binding['payload']!=worker_request['payload']
                            or worker_response['payload']['request_digest']!=request.content_digest()
                            or worker_response['payload']['provider_digest']!=binding['payload']['provider_digest']
                            or not a['sequence']<binding['sequence']<worker_request['sequence']<worker_response['sequence']<terminal['sequence']
                            or terminal['payload']['actual_resources']!=response.actual_resources):
                        raise ValueError('worker provenance or resource settlement differs')
                    if identity==manifest.attempt_id:
                        for ref,digest in request.input_hashes.items():
                            if manifest.input_artifacts.get(ref)!=digest or sha256(resolve_artifact(ref)).hexdigest()!=digest:
                                raise ValueError('worker input binding differs from manifest')
                        if terminal['payload']['status']=='SUCCEEDED' and (response.status!='SUCCEEDED'
                                or response.output!=resolve_artifact('environment-input.json')
                                or response.randomness!=manifest.randomness):
                            raise ValueError('worker output/randomness contradicts frozen operation')
                c=BenchmarkCondition.from_dict(by_id['condition:'+a_run.condition_hash]['payload'])
                usage,blocked=_usage(before,a_run.budget_root_run_id)
                if blocked or any(v>c.task.budget_limits[k] for k,v in usage.items()):raise ValueError('root budget breach')
            for event in before:
                if event['kind']=='WORKER_REQUEST':
                    identity=event['payload']['attempt_id']
                    if 'attempt:'+identity not in by_id or 'settle:'+identity not in by_id:
                        raise ValueError('unaccounted worker invocation')
            passed('G3','CANONICAL_ATTEMPTS_FAILURES_AND_BUDGET_ROOTS_ACCOUNTED')
        except (ValueError,KeyError,TypeError,StopIteration,OSError):
            gates['G3']['reason']='INCOMPLETE_OR_UNRESOLVED_SEARCH_LEDGER'
        if gates['G7']['status']=='PASS':
            try:
                operation=json.loads(resolve_artifact('environment-input.json'))
                if 'pit-observations.json' not in manifest.input_artifacts:raise ValueError('PIT evidence absent')
                expected=pit_observations(task,data,snapshot,resolve_artifact,operation['environment'])
                if canonical_bytes(expected)!=resolve_artifact('pit-observations.json'):raise ValueError('PIT visibility differs')
                passed('G1','PIT_VISIBLE_SET_RECOMPUTED_SYNTHETIC')
            except (ValueError,KeyError,TypeError,OSError):
                gates['G1']['reason']='PIT_EVIDENCE_MISSING_OR_FUTURE_CONTAMINATED'
            reproduction=replay(manifest,expected_manifest_digest=expected_manifest_digest,replay_id='REPLAY-'+manifest.attempt_id,
                trace_store=trace_store,resolve_artifact=resolve_artifact)
            if reproduction['assurance']=='DETERMINISTIC_REPRODUCED':passed('G2','EXACT_SUPPORTED_DETERMINISTIC_REPLAY')
            else:gates['G2']['reason']=reproduction['assurance']
            try:
                operation=json.loads(resolve_artifact('environment-input.json'))
                output=canonical_bytes(simulate(task,PITView(task,data,snapshot,resolve_artifact),operation['environment']))
                if output!=resolve_artifact(candidates[0].artifact_ref):raise ValueError('execution output mismatch')
                passed('G5','SYNTHETIC_EXECUTION_CONFORMANCE_ONLY_D11_D12_UNCALIBRATED')
            except (ValueError,KeyError,TypeError,OSError,ArithmeticError):
                gates['G5']['reason']='EXECUTION_TIMING_ACCOUNTING_COST_OR_CAPACITY_INVALID'
    if trace_store.read()!=before:
        gates['G3'].update(status='BLOCK',reason='TRACE_CHANGED_DURING_EVALUATION')
    # Strategy measurements are not trusted just because an Evidence object exists.
    metrics={}
    if gates['G5']['status']=='PASS':
        result=json.loads(resolve_artifact(candidates[0].artifact_ref))
        metrics={'synthetic_final_nav':result['ledger'][-1]['nav']}
        if any(dict(e.metrics)!={'synthetic_final_nav':float(metrics['synthetic_final_nav'])} for e in evidence):
            gates['G7'].update(status='BLOCK',reason='FABRICATED_OR_UNSUPPORTED_MEASUREMENT'); metrics={}
    source=Path(__file__).read_bytes()
    return EvalResult('EVAL-'+manifest.attempt_id,manifest.task_ref,manifest.condition_hash,manifest.benchmark_run_id,
        manifest.scientific_family_id,manifest.attempt_id,next(iter(manifest.candidate_hashes)),VERSION,
        'src/quant_rsi/eval/gates.py',sha256(source).hexdigest(),gates,dict(manifest.evidence_hashes),metrics,
        {'capability_score':None,'score_vector_status':'NOT_CALIBRATED','ledger_complete':gates['G3']['status']=='PASS'},
        review_ref or 'unavailable-critic:'+manifest.attempt_id,dict(manifest.output_artifacts),'settle:'+manifest.attempt_id,created_at)


def evaluate_public(manifest, *, expected_manifest_digest, trace_store, resolve_artifact,
                    critic_report, author, critic, created_at):
    """Evaluate a public fixture through canonical contracts, never formal promotion."""
    from quant_rsi.agents.critic import admit, CriticReport
    from quant_rsi.agents.worker import WorkerRequest, WorkerResponse
    from quant_rsi.benchmark_public.oracle import check

    events = trace_store.read()
    by_id = {event['event_id']: event for event in events}
    gates = {g: dict(status='BLOCK', reason='MISSING_OR_INVALID_EVIDENCE', scope='PUBLIC_SYNTHETIC') for g in GATES}
    for gate, reason in BLOCK_REASONS.items():
        gates[gate] = dict(status='BLOCK', reason=reason, scope='FORMAL_RESEARCH')
    gates['G2']['reason'] = 'PUBLIC_DETERMINISTIC_REPLAY_NOT_IMPLEMENTED'
    diagnostic = 'EVALUATOR_BLOCK'
    oracle = None
    candidate = None
    try:
        if manifest.manifest_digest != expected_manifest_digest:
            raise ValueError('manifest pin mismatch')
        condition = BenchmarkCondition.from_dict(by_id[manifest.condition_ref]['payload'])
        task = condition.task
        run = AgentBenchmarkRun.from_dict(by_id['run:' + manifest.benchmark_run_id]['payload'])
        task.verify_frozen_condition(by_id[task.decision_snapshot_ref]['payload'])
        if (task.mode != 'SYNTHETIC' or task.evaluator_version != PUBLIC_VERSION
                or run.condition_hash != condition.condition_hash
                or manifest.task_hash != task.content_digest()):
            raise ValueError('unsupported public evaluator or contract')
        attempt = by_id['attempt:' + manifest.attempt_id]
        if (attempt['kind'] != 'ATTEMPT_STARTED' or attempt['payload']['scientific_variant_id'] is not None
                or attempt['payload']['envelope']['candidate_trials'] != 0):
            raise ValueError('public attempt identity invalid')
        experiment = ExperimentSpec.from_dict(by_id['experiment:' + attempt['payload']['experiment_id']]['payload'])
        validate_experiment_binding(experiment, task, run)
        gates['G0'].update(status='PASS', reason='PUBLIC_FROZEN_CONTRACT_AND_PREREGISTRATION')

        data = DataSpec.from_dict(json.loads(resolve_artifact(manifest.data_spec_ref)))
        snapshot = SnapshotManifest.from_dict(json.loads(resolve_artifact(manifest.snapshot_ref)))
        candidates = [Candidate.from_dict(json.loads(resolve_artifact(ref))) for ref in manifest.candidate_hashes]
        evidence = [Evidence.from_dict(json.loads(resolve_artifact(ref))) for ref in manifest.evidence_hashes]
        if len(candidates) != 1 or len(evidence) != 1:
            raise ValueError('one canonical public candidate and evidence required')
        candidate = candidates[0]
        if candidate.kind != 'PUBLIC_FIXTURE' or evidence[0].kind != 'PUBLIC_FIXTURE':
            raise ValueError('scientific output cannot enter public evaluation')
        manifest.verify_bindings(trace_store=trace_store, condition=condition, run=run,
                                 data_spec=data, snapshot=snapshot, candidates=candidates,
                                 evidence=evidence, resolve_artifact=resolve_artifact)
        gates['G1'].update(status='PASS', reason='PUBLIC_SNAPSHOT_AND_ASOF_BINDINGS_VERIFIED')

        accounting = SearchBudget(trace_store).capability_accounting(run.benchmark_run_id)
        scientific = SearchBudget(trace_store).scientific_accounting(run.scientific_family_id)
        terminal = by_id['settle:' + manifest.attempt_id]
        response = WorkerResponse.from_dict(by_id['worker-response:' + manifest.attempt_id]['payload']['response'])
        request_event = by_id['worker-request:' + manifest.attempt_id]
        request = WorkerRequest.from_dict(request_event['payload']['request'])
        binding = by_id['worker-binding:' + manifest.attempt_id]
        if (accounting['blocked'] or accounting['usage']['candidate_trials'] != 0
                or accounting['usage']['attempts'] != 1 or scientific['candidate_variant_count'] != 0
                or terminal['payload']['actual_resources'] != response.actual_resources
                or request_event['payload'] != binding['payload']
                or request.run_id != run.benchmark_run_id
                or (request.actor_id, request.context_id, request.run_id) != (
                    author.actor_id, author.context_id, author.run_id)
                or by_id['worker-response:' + manifest.attempt_id]['payload']['request_digest'] != request.content_digest()
                or by_id['worker-response:' + manifest.attempt_id]['payload']['provider_digest'] != binding['payload']['provider_digest']
                or not attempt['sequence'] < binding['sequence'] < request_event['sequence']
                < by_id['worker-response:' + manifest.attempt_id]['sequence'] < terminal['sequence']
                or any(manifest.trace_refs.get(ref) != by_id[ref]['event_hash']
                       for ref in ('attempt:' + manifest.attempt_id, 'settle:' + manifest.attempt_id))):
            raise ValueError('public denominator or worker provenance invalid')
        gates['G3'].update(status='PASS', reason='ONE_ASSIGNED_ATTEMPT_ZERO_SCIENTIFIC_TRIALS_ACCOUNTED')

        admission = by_id['admission:' + manifest.attempt_id]
        report_ref = 'critic:' + critic_report.content_digest()
        if (admission['payload']['critic_report_ref'] != report_ref
                or admission['payload']['manifest_digest'] != manifest.manifest_digest
                or admission['payload']['critic_report_digest'] != critic_report.content_digest()
                or CriticReport.from_dict(json.loads(resolve_artifact(report_ref))) != critic_report):
            raise ValueError('critic binding invalid')
        admitted = admit(critic_report, candidate, evidence, author=author, critic=critic)
        if admitted and admission['kind'] == 'ADMISSION_GRANTED':
            gates['G7'].update(status='PASS', reason='INDEPENDENT_PUBLIC_CRITIC_ADMISSION')
        else:
            gates['G7']['reason'] = 'CRITIC_REJECTION'

        output_record = json.loads(resolve_artifact(candidate.artifact_ref))
        if (output_record['response_hex'] != response.output.hex()
                or output_record['response_status'] != response.status):
            raise ValueError('canonical output differs from worker response')
        if response.status == 'TIMEOUT':
            diagnostic = 'TIMEOUT'
        else:
            try:
                output = json.loads(response.output)
            except (ValueError, UnicodeDecodeError):
                output = None
            release = json.loads(resolve_artifact('public-input.json'))
            oracle = check(release, output)
            diagnostic = oracle['diagnostic']
        if gates['G7']['reason'] == 'CRITIC_REJECTION':
            diagnostic = 'CRITIC_REJECTION'
        if diagnostic == 'CORRECT_PUBLIC_OUTPUT' and gates['G7']['status'] == 'PASS':
            gates['G5'].update(status='PASS', reason='PUBLIC_ORACLE_CROSS_CHECK_ONLY')
        else:
            gates['G5'].update(status='FAIL', reason=diagnostic)
    except (ValueError, KeyError, TypeError, OSError, IndexError):
        gates['G5'].update(status='BLOCK', reason='EVALUATOR_BLOCK')
        diagnostic = 'EVALUATOR_BLOCK'
    return EvalResult('EVAL-' + manifest.attempt_id, manifest.task_ref, manifest.condition_hash,
        manifest.benchmark_run_id, manifest.scientific_family_id, manifest.attempt_id,
        next(iter(manifest.candidate_hashes)), PUBLIC_VERSION, 'src/quant_rsi/eval/gates.py',
        sha256(Path(__file__).read_bytes()).hexdigest(), gates, dict(manifest.evidence_hashes), {},
        {'assigned_denominator': 1, 'public_oracle_full_pass': bool(oracle and oracle['full_pass']),
         'terminal_diagnostic': diagnostic, 'oracle_expected_sha256': None if oracle is None else oracle['expected_sha256'],
         'scientific_candidate_trials': 0}, 'critic:' + critic_report.content_digest(),
        dict(manifest.output_artifacts), 'settle:' + manifest.attempt_id, created_at)
