"""Offline supplement entry; original frozen harnesses are not modified."""
import argparse
import copy
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from quant_rsi.agents.worker import WorkerRequest
from quant_rsi.contracts.condition import AgentBenchmarkRun, BenchmarkCondition, TaskContract, load_decisions
from quant_rsi.contracts.data import DataSpec, SnapshotManifest
from quant_rsi.contracts.research import ConceptMapping, Hypothesis, ScientificSearchFamily
from quant_rsi.eval.replay import dependency_lock
from quant_rsi.harness.agent_workflow import ROOT, digest, parse_action, read, save
from quant_rsi.harness.supplement_chat import ControlledTransport, SupplementChatAdapter
from quant_rsi.harness.supplement_tasks import TASKS, SET_FIELDS, INTEGER_FIELDS, FIELD_ENUMS, VERSION
from quant_rsi.harness.supplement_tools import execute, UnknownToolUsage
from quant_rsi.harness.workflow_chat import messages
from quant_rsi.harness.workflow_v02 import usage_resources
from quant_rsi.harness.providers import ProviderReply
from quant_rsi.ledger.budget import SearchBudget, BudgetDenied
from quant_rsi.ledger.store import TraceStore

PACK = ROOT / 'benchmark/capability_supplement_v01'
LIMITS = dict(max_steps=8, max_tool_calls=6, request_input=32768, request_output=2048,
              task_input=262144, task_output=16384, automatic_retries=0)
ACTION_CONTRACT = dict(version=VERSION, actions=['TOOL_CALL', 'FINAL'],
    TOOL_CALL=dict(action='TOOL_CALL', tool='public_tool_name', arguments={'observations': 'all prior observation IDs in order'}),
    FINAL=dict(action='FINAL', conclusion='object matching conclusion_contract', evidence='unique actual observation/input IDs'),
    aliases=dict(type='action', args='arguments', result='conclusion'),
    boundary='Only supervisor executes whitelisted fixture operations. No shell, network, code submission or permission changes.')


def shape(value):
    if value is None:
        return 'null_or_declared_value'
    if type(value) is dict:
        return {k: shape(v) for k, v in value.items()}
    if type(value) is list:
        return dict(type='array', items='JSON values described in task; ordered unless declared a string set')
    return {bool: 'boolean', int: 'number', float: 'number', str: 'string'}[type(value)]


def context_for(case, observations, history):
    fields = {k: shape(v) for k, v in case['reference'].items()}
    if case['task_id'] == 'Q-AT-02':
        fields.update(selected_vintage='string_or_null', value='number_or_null')
    if case['task_id'] == 'Q-FA-02':
        fields.update(industry_means='object_or_null', residuals='array_or_null',
                      residual_industry_means='object_or_null')
    allowed = case['stages'] + case.get('optional_tools', [])
    contracts = {name: dict(arguments={'observations': 'array of ALL prior observation IDs in order'},
        prerequisites=case['stages'][:i] if name in case['stages'] else ['inspect_versions'],
        output_schema=case.get('tool_outputs', {}).get(name, 'engineering schema generation pending'),
        description='Execute ' + name.replace('_', ' ') + ' on frozen synthetic inputs')
        for i, name in enumerate(allowed)}
    if case['task_id'] == 'Q-AT-02':
        contracts['inspect_backup']['prerequisites'] = ['inspect_versions']
        contracts['inspect_backup']['condition'] = 'inspect_versions.eligible is empty'
        contracts['read_eligible_version']['condition'] = 'inspect_versions.eligible is nonempty'
    return dict(task={k: copy.deepcopy(case[k]) for k in ('task_id', 'kind', 'question', 'input')},
        action_contract=ACTION_CONTRACT, allowed_tools=allowed,
        tool_contracts=contracts,
        conclusion_contract=dict(fields=fields,
            categorical_vocabulary={k: v for k, v in FIELD_ENUMS.items() if k in fields},
            exit_identifier_pattern='holding_day_<integer>_close',
            absolute_tolerance=1e-8, unordered_string_set_fields=sorted(SET_FIELDS & set(case['reference'])),
            exact_integer_fields=sorted(INTEGER_FIELDS & set(case['reference'])),
            identifiers='exact', unknown=None, extra_fields='rejected',
            reference_scope='No truth values or reference answers are included'),
        input_sources=['INPUT:' + case['task_id']], limits=LIMITS,
        citation_policy=dict(required_direct_citation_tools=case['required_direct_citations'],
            terminal_derived_observation='must cite for workflow FINAL',
            other_dependencies='recorded tool reference graph; optional/redundant observations need not be cited',
            structured='cite the supplied INPUT source'),
        observations=copy.deepcopy(observations), history=copy.deepcopy(history))


def prepare():
    """Engineering binding generation before the retained end-to-end run."""
    PACK.mkdir(exist_ok=True)
    if (PACK / 'offline_run_verified').exists():
        raise ValueError('RETAINED_RUN_EXISTS_USE_NEW_VERSION_NOT_OVERWRITE')
    baseline = read(ROOT / 'benchmark/agent_workflow_v01/cases.json')['WFA-01-normal']
    decisions = load_decisions()
    save(PACK / 'decision_snapshot.json', decisions)
    cases = copy.deepcopy(TASKS)
    public_schemas = {}
    for case in cases.values():
        observations = []
        for i, name in enumerate(case['stages']):
            if case['task_id'] == 'Q-AT-02' and i:
                eligible = observations[0]['result']['eligible']
                if (name == 'inspect_backup' and eligible) or (name == 'read_eligible_version' and not eligible):
                    continue
            try:
                result = execute(case, name, {'observations': [o['observation_id'] for o in observations]}, observations)
            except UnknownToolUsage:
                result = None
            public_schemas[case['task_id'], name] = shape(result)
            observations.append(dict(observation_id=f'SCHEMA-{i}', tool=name, result=result, ok=result is not None))
        for name in case.get('optional_tools', []):
            result = execute(case, name, {'observations': [o['observation_id'] for o in observations]}, observations)
            public_schemas[case['task_id'], name] = shape(result)
    for case in cases.values():
        case['tool_outputs'] = {name: public_schemas[case['task_id'], name]
                               for name in case['stages'] + case.get('optional_tools', [])}
        if case['task_id'] == 'Q-AT-02':
            for name in ('read_eligible_version', 'inspect_backup'):
                case['tool_outputs'][name] = dict(verdict='string', selected_vintage='string_or_null',
                                                 value='number_or_null', backup_checked='boolean')
    frozen_at = datetime.now(timezone.utc).isoformat()
    for key, case in cases.items():
        spec = copy.deepcopy(baseline['data_spec'])
        spec.update(source_id='synthetic-' + key, source_revision=VERSION,
                    raw_artifact_hash=digest(case['fixture']), cleaning_spec_version=VERSION)
        data = DataSpec.from_dict(spec)
        snapshot = copy.deepcopy(baseline['snapshot'])
        snapshot.update(snapshot_id='SNAP-' + key, data_spec=data.to_dict(),
                        files=[dict(path='fixture.json', sha256=digest(case['fixture']))])
        manifest = SnapshotManifest.from_dict(snapshot)
        ledger = copy.deepcopy(baseline['ledger_task'])
        ledger.update(task_id=key, task_version=VERSION, benchmark_ref=VERSION, target=case['question'],
            data_spec_hash=data.content_hash(), snapshot_hash=manifest.content_hash(),
            cleaning_spec_version=VERSION, env_version=VERSION, evaluator_version=VERSION,
            frozen_at=frozen_at, decision_registry_hash=digest(decisions),
            decision_snapshot_ref='sha256:' + digest(decisions), decision_registry_version=decisions['version'])
        ledger['budget_limits'].update(input_tokens=LIMITS['task_input'], output_tokens=LIMITS['task_output'])
        if case['kind'] == 'STRUCTURED':
            ledger['budget_limits'].update(attempts=1, validation_queries=0,
                input_tokens=LIMITS['request_input'], output_tokens=LIMITS['request_output'])
        case.update(ledger_task=TaskContract.from_dict(ledger).to_dict(), data_spec=data.to_dict(), snapshot=manifest.to_dict())
    # Order is explicit; JSON object key ordering is not a workflow policy.
    order = [k for k, c in cases.items() if c['variant'] == 'base']
    save(PACK / 'cases.json', cases)
    save(PACK / 'action_contract.json', ACTION_CONTRACT)
    save(PACK / 'prompts.json', {k: messages(context_for(c, [], [])) for k, c in cases.items()})
    refs = ['benchmark/capability_supplement_v01/' + p for p in
            ('cases.json', 'action_contract.json', 'prompts.json', 'decision_snapshot.json')]
    refs += ['src/quant_rsi/harness/' + name for name in ('supplement.py', 'supplement_tasks.py',
             'supplement_tools.py', 'supplement_chat.py', 'supplement_oracle.py', 'supplement_cp.py')]
    # Transitive shared execution/scoring dependencies; no whole-repository scan.
    refs += ['src/quant_rsi/' + name for name in ('harness/providers.py', 'harness/agent_workflow.py',
        'harness/workflow_chat.py', 'harness/workflow_v02.py', 'harness/workflow_oracle.py', 'harness/workflow_tools.py',
        'agents/worker.py', 'contracts/condition.py', 'contracts/data.py', 'contracts/research.py',
        'ledger/budget.py', 'ledger/store.py', 'data/pit.py', 'eval/replay.py')]
    refs += ['tests/test_supplement.py', 'tests/test_supplement_cp.py']
    from quant_rsi.harness.supplement_cp import contracts
    save(PACK / 'cp_contracts.json', contracts())
    refs.append('benchmark/capability_supplement_v01/cp_contracts.json')
    freeze = dict(version=VERSION, created_at=frozen_at, case_order=order,
        variant_order=[k for k in cases if k not in order], limits=LIMITS, runtime=dependency_lock(),
        real_model_calls=0, real_network=False, currency='NOT_PRICED_SIMULATION', labels=['PUBLIC', 'UNSEALED', 'PROVISIONAL'],
        engineering_budget=dict(max_test_invocations=40, max_end_to_end_batches=3),
        cp_status='CONTRACT_AND_REFERENCE_ONLY_EXECUTION_BLOCKED',
        sha256={p: sha256((ROOT / p).read_bytes()).hexdigest() for p in refs})
    save(PACK / 'freeze.json', freeze)
    return freeze


def suite():
    freeze = read(PACK / 'freeze.json')
    if freeze['runtime'] != dependency_lock():
        raise ValueError('SUPPLEMENT_RUNTIME_CHANGED')
    for ref, expected in freeze['sha256'].items():
        if sha256((ROOT / ref).read_bytes()).hexdigest() != expected:
            raise ValueError('SUPPLEMENT_BINDING_CHANGED:' + ref)
    if read(PACK / 'action_contract.json') != ACTION_CONTRACT:
        raise ValueError('PUBLIC_CONTRACT_CHANGED')
    return freeze, read(PACK / 'cases.json')


def setup(store, case, agent, run_id, freeze):
    budget = SearchBudget(store)
    claim = digest(dict(case=digest(case), model=agent.model_id))
    with store.transaction() as tx:
        if any(e['event_id'] == 'supplement-claim:' + claim for e in tx.events()):
            tx.append('rename-denied:' + run_id, 'SUPPLEMENT_RENAME_DENIED', dict(run_id=run_id, claim=claim))
            duplicate = True
        else:
            tx.append('supplement-claim:' + claim, 'SUPPLEMENT_CLAIMED', dict(run_id=run_id, claim=claim))
            duplicate = False
    if duplicate:
        raise ValueError('BUDGET_ROOT_ALREADY_CLAIMED')
    task = TaskContract.from_dict(case['ledger_task'])
    task.verify_data_bindings(DataSpec.from_dict(case['data_spec']), SnapshotManifest.from_dict(case['snapshot']))
    condition = BenchmarkCondition(task)
    budget.register_concept(ConceptMapping('MAP-' + run_id, 'synthetic conformance',
        'public observations', 'engineering only', ('FEAT-supplement',)))
    budget.register_hypothesis(Hypothesis('HYP-' + run_id, 'CLAIM-' + run_id,
        'synthetic contract conformance', 'predicate failure', 'MAP-' + run_id))
    budget.register_family(ScientificSearchFamily('FAM-' + run_id, 'CLAIM-' + run_id,
        'engineering only; no scientific variant search'))
    run = AgentBenchmarkRun(run_id, 'FAM-' + run_id, condition.condition_hash, agent.model_id,
        'controlled-simulation-v1', digest(context_for(case, [], [])), digest(freeze['sha256']),
        digest(freeze['runtime']), run_id, datetime.now(timezone.utc).isoformat(), provider=agent.provider_id)
    budget.register_run(run, condition, decision_snapshot=read(PACK / 'decision_snapshot.json'))
    return budget, run


def run_case(store, case_key, run_id, *, profile='correct', fault=None):
    freeze, cases = suite()
    case = cases[case_key]
    agent = SupplementChatAdapter(ControlledTransport(profile, fault))
    budget, run = setup(store, case, agent, run_id, freeze)
    binding = sha256((PACK / 'freeze.json').read_bytes()).hexdigest()
    store.append('supp-start:' + run_id, 'SUPPLEMENT_STARTED', dict(run_id=run_id, case_key=case_key,
        case_hash=digest(case), freeze_hash=binding, initial_context_hash=digest(context_for(case, [], []))))
    observations, history, final, supervisor = [], [], None, None
    status, error = 'MAX_STEPS_EXCEEDED', None
    max_steps = 1 if case['kind'] == 'STRUCTURED' else LIMITS['max_steps']
    for step in range(1, max_steps + 1):
        attempt = f'CHAT-{run_id}-{step}'
        first = budget.capability_accounting(run_id)['usage']['attempts'] == 0
        envelope = dict(attempts=1, candidate_trials=0, model_trials=int(first), input_tokens=32768,
                        output_tokens=2048, wall_milliseconds=1000, cpu_milliseconds=1000)
        try:
            budget.reserve(run_id, attempt, envelope)
        except BudgetDenied:
            status, error = 'BUDGET_EXHAUSTED', 'CHAT_BUDGET_DENIED'
            break
        context = context_for(case, observations, history)
        request = WorkerRequest(run_id, 'ACT-' + run_id, 'CTX-' + run_id, agent.provider_id,
            agent.model_id, VERSION, digest(context), digest(ACTION_CONTRACT), tuple(context['allowed_tools']),
            {'context': digest(context), 'fixture': digest(case['fixture']), 'case': digest(case)})
        store.append('supp-request:' + attempt, 'SUPPLEMENT_CHAT_REQUEST', dict(run_id=run_id,
            step=step, attempt_id=attempt, request=request.to_dict(), context=context))
        if len(json.dumps(messages(context)).encode()) > envelope['input_tokens']:
            error, status = 'INPUT_RESERVATION_TOO_SMALL', 'BUDGET_EXHAUSTED'
            budget.settle(attempt, 'FAILED', dict(input_tokens=0, output_tokens=0,
                wall_milliseconds=0, cpu_milliseconds=0), failure=error)
            break
        try:
            reply = agent.step(request, context)
        except (Exception, KeyboardInterrupt) as exc:
            failure = 'WORKFLOW_INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'CHAT_ADAPTER_FAILED'
            reply = ProviderReply(False, None, None, failure, None, None, 0, 1, failure_class=failure)
            if agent.last_exchange is None:
                agent.last_exchange = dict(messages=messages(context), messages_hash=digest(messages(context)),
                    request_body=dict(messages=messages(context), model=agent.model_id, max_tokens=2048), response=None)
        error, action = reply.failure_type, None
        if not error and reply.observed_model != agent.model_id:
            error = 'PROVIDER_MODEL_MISMATCH'
        if not error and reply.finish_reason != 'stop':
            error = 'FINISH_REASON_UNKNOWN'
        if not error:
            try:
                action = parse_action(reply.text)
            except json.JSONDecodeError:
                error = 'ACTION_JSON_INVALID'
            except (ValueError, TypeError):
                error = 'ACTION_SCHEMA_INVALID'
        resources = usage_resources(reply)
        if resources is None:
            error = error or 'USAGE_UNKNOWN_OR_INVALID'
        store.append('supp-action:' + attempt, 'SUPPLEMENT_CHAT_ACTION', dict(run_id=run_id,
            step=step, attempt_id=attempt, raw=reply.text, action=action, error=error,
            reply=asdict(reply), exchange=agent.last_exchange,
            cost=dict(state='NOT_PRICED_SIMULATION', actual=None, budget_root_run_id=run_id)))
        budget.settle(attempt, 'FAILED' if error else 'SUCCEEDED', resources,
            artifact_hashes={'action': digest(action)} if not error else {}, failure=error)
        history.append(action)
        if error:
            status = 'INVALID_ACTION' if error.startswith('ACTION_') else 'PROVIDER_FAILED'
            break
        if budget.capability_accounting(run_id)['blocked']:
            status, error = 'BUDGET_EXHAUSTED', 'CHAT_USAGE_BREACH'
            break
        if action['action'] == 'FINAL':
            final, status = action, 'COMPLETED'
            break
        tool_attempt = f'TOOL-{run_id}-{step}'
        try:
            budget.reserve(run_id, tool_attempt, dict(attempts=1, candidate_trials=0,
                validation_queries=1, input_tokens=0, output_tokens=0, wall_milliseconds=1000, cpu_milliseconds=1000))
        except BudgetDenied:
            status, error = 'BUDGET_EXHAUSTED', 'TOOL_BUDGET_DENIED'
            break
        start, cpu = time.perf_counter(), time.process_time()
        observation = dict(observation_id=f'OBS-{run_id}-{step}', run_id=run_id, step=step,
            attempt_id=tool_attempt, tool=action['tool'], arguments=action['arguments'], ok=True, result=None, error=None)
        unknown = False
        controlled_tool_failure = fault == 'tool_failure'
        try:
            if controlled_tool_failure:
                raise RuntimeError('CONTROLLED_TOOL_EXECUTION_FAILED')
            observation['result'] = execute(case, action['tool'], action['arguments'], observations)
        except UnknownToolUsage as exc:
            observation.update(ok=False, error=str(exc))
            unknown = True
        except ValueError as exc:
            observation.update(ok=False, error=str(exc))
        except RuntimeError:
            observation.update(ok=False, error='CONTROLLED_TOOL_EXECUTION_FAILED')
        actual = None if unknown else dict(input_tokens=0, output_tokens=0,
            wall_milliseconds=max(0, int((time.perf_counter()-start)*1000)),
            cpu_milliseconds=max(0, int((time.process_time()-cpu)*1000)))
        store.append('supp-observation:' + tool_attempt, 'SUPPLEMENT_TOOL_RESULT', copy.deepcopy(observation))
        budget.settle(tool_attempt, 'SUCCEEDED' if observation['ok'] else 'FAILED', actual,
            artifact_hashes={'observation': digest(observation)} if observation['ok'] else {}, failure=observation['error'])
        observations.append(observation)
        if unknown:
            status, error = 'EXECUTION_INCOMPLETE', observation['error']
            supervisor = dict(terminal=status, actual_usage=None, reservation_retained=True,
                new_tool_executions=0, research_claim_established=False)
            store.append('supervisor-stop:' + run_id, 'SUPERVISOR_TERMINAL', dict(run_id=run_id, conclusion=supervisor))
            if profile == 'over_budget':
                # Controlled adversarial boundary probe, NOT another Agent dispatch.
                store.append('adversarial:' + run_id, 'CONTROLLED_POST_STOP_REQUEST', dict(run_id=run_id))
                try:
                    budget.reserve(run_id, 'DENIED-' + run_id, envelope)
                except BudgetDenied:
                    pass
                else:
                    raise AssertionError('UNKNOWN_USAGE_DID_NOT_BLOCK')
            break
        if not observation['ok']:
            if controlled_tool_failure:
                continue  # Known usage permits examining failure; success claims remain invalid.
            status, error = 'INVALID_TOOL_ACTION', observation['error']
            break
        if budget.capability_accounting(run_id)['blocked']:
            status, error = 'BUDGET_EXHAUSTED', 'TOOL_RESOURCE_BREACH'
            break
    result = dict(run_id=run_id, case_key=case_key, task_id=case['task_id'], profile=profile,
        model_id=agent.model_id, status=status, error=error, final=final, supervisor=supervisor,
        steps=len(history), tool_calls=len(observations), transport_calls=agent.transport.calls,
        usage=budget.capability_accounting(run_id), scientific=budget.scientific_accounting(run.scientific_family_id),
        real_agent_ability='UNVERIFIED', real_calls=0, single_total_score=None)
    store.append('supp-end:' + run_id, 'SUPPLEMENT_COMPLETED', result)
    from quant_rsi.harness.supplement_oracle import evaluate
    result['evaluation'] = evaluate(case, result, store.read())
    store.append('supp-eval:' + run_id, 'SUPPLEMENT_EVALUATED', dict(run_id=run_id, **result['evaluation']))
    return result


def run_suite(output):
    """Three-batch engineering cap uses the SAME canonical Budget/Trace types."""
    if output.exists():
        raise ValueError('OUTPUT_EXISTS_APPEND_ONLY_DO_NOT_OVERWRITE')
    freeze, cases = suite()
    batch_store = TraceStore(PACK / 'engineering_batches.sqlite')
    budget = SearchBudget(batch_store)
    root = 'ENG-SUPPLEMENT-BATCHES-V01'
    if not any(e['kind'] == 'RUN_REGISTERED' and e['payload']['benchmark_run_id'] == root for e in batch_store.read()):
        case = copy.deepcopy(cases[freeze['case_order'][0]])
        case['ledger_task'].update(task_id='ENGINEERING-SUPPLEMENT', target='offline engineering batches only')
        caps = dict.fromkeys(case['ledger_task']['budget_limits'], 0)
        caps.update(attempts=3, model_trials=1, wall_milliseconds=3600000, cpu_milliseconds=3600000)
        case['ledger_task']['budget_limits'] = caps
        setup(batch_store, case, SupplementChatAdapter(ControlledTransport('batch-control')), root, freeze)
    count = budget.capability_accounting(root)['usage']['attempts']
    attempt = f'BATCH-{count+1}'
    budget.reserve(root, attempt, dict(attempts=1, model_trials=int(count == 0), candidate_trials=0,
        input_tokens=0, output_tokens=0, wall_milliseconds=1200000, cpu_milliseconds=1200000))
    start, cpu = time.perf_counter(), time.process_time()
    status, failure = 'FAILED', 'ENGINEERING_BATCH_INTERRUPTED_OR_FAILED'
    artifacts = {}
    try:
        records = _run_suite_body(output)
        artifacts = {'manifest': sha256((output / 'manifest.json').read_bytes()).hexdigest()}
        status, failure = 'SUCCEEDED', None
        return records
    finally:
        budget.settle(attempt, status, dict(input_tokens=0, output_tokens=0,
            wall_milliseconds=max(0, int((time.perf_counter()-start)*1000)),
            cpu_milliseconds=max(0, int((time.process_time()-cpu)*1000))), artifact_hashes=artifacts, failure=failure)
        save(output / 'engineering_batch_trace.json', batch_store.read()) if output.exists() else None


def _run_suite_body(output):
    from quant_rsi.harness.supplement_oracle import replay
    if output.exists():
        raise ValueError('OUTPUT_EXISTS_APPEND_ONLY_DO_NOT_OVERWRITE')
    output.mkdir(parents=True)
    freeze, cases = suite()
    keys = freeze['case_order'] + freeze['variant_order']
    records, traces = [], {}
    for i, key in enumerate(keys):
        for profile in ('correct', 'over_budget' if key == 'Q-AT-03' else 'wrong_final'):
            run_id = f'SUP-{i:02}-{profile}'
            store = TraceStore(output / (run_id + '.sqlite'))
            result = run_case(store, key, run_id, profile=profile)
            expected_pass = profile == 'correct'
            if result['evaluation']['task_pass'] != expected_pass:
                save(output / (run_id + '-unexpected.json'), result)
                raise ValueError('REFERENCE_OR_NEGATIVE_CALIBRATION_FAILED:' + run_id)
            events = store.read()
            anchor = store.checkpoint()
            checked = replay(events, result, expected_anchor=anchor)
            traces[run_id] = events
            records.append(dict(result=result, anchor=asdict(anchor), replay=checked))
    save(output / 'results.json', records)
    save(output / 'trace.json', traces)
    # SQLite is a run cache; retained JSON contains the complete original events.
    save(output / 'manifest.json', dict(freeze_hash=sha256((PACK / 'freeze.json').read_bytes()).hexdigest(),
        records=len(records), source_clusters=len({c['source_cluster'] for c in cases.values()}),
        sha256={p: sha256((output / p).read_bytes()).hexdigest() for p in ('results.json', 'trace.json')},
        real_calls=0, cp_execution='BLOCKED_ENVIRONMENT_CAPABILITY'))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--run', type=Path)
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare()
        print('SUPPLEMENT_BOUND: 28 tasks, 2 extra arms, CP preparation only')
    elif args.run:
        records = run_suite(args.run)
        print(json.dumps(dict(records=len(records), replay_matches=len(records), real_calls=0)))
    elif args.replay:
        from quant_rsi.harness.supplement_oracle import replay_saved
        print(json.dumps(replay_saved(args.replay)))
    else:
        parser.error('choose --prepare, --run or --replay')


if __name__ == '__main__':
    main()
