"""Track A offline tool-driven loop; B1/B2 canonical ledger owns all reservations."""
import argparse
import copy
import json
import re
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from quant_rsi.agents.worker import WorkerRequest
from quant_rsi.contracts.condition import (AgentBenchmarkRun, BenchmarkCondition, TaskContract,
                                         RESOURCE_DIMENSIONS)
from quant_rsi.contracts.data import DataSpec, SnapshotManifest
from quant_rsi.contracts.research import ConceptMapping, Hypothesis, ScientificSearchFamily, ExperimentSpec
from quant_rsi.data.pit import canonical_bytes
from quant_rsi.eval.replay import dependency_lock
from quant_rsi.harness.workflow_agents import ScriptedAgent, ChatWorkflowAdapter
from quant_rsi.harness.workflow_tools import FixtureTools, validate_call
from quant_rsi.ledger.budget import SearchBudget, BudgetDenied
from quant_rsi.ledger.store import TraceStore, verify_events

ROOT = Path(__file__).resolve().parents[3]
PACK = ROOT / 'benchmark/agent_workflow_v01'


def digest(value):
    return sha256(canonical_bytes(value)).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_bytes(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode())


def suite():
    freeze = read(PACK / 'freeze.json')
    if freeze['runtime'] != dependency_lock():
        raise ValueError('WORKFLOW_RUNTIME_CHANGED')
    for ref, expected in freeze['sha256'].items():
        if sha256((ROOT / ref).read_bytes()).hexdigest() != expected:
            raise ValueError('WORKFLOW_FREEZE_CHANGED: ' + ref)
    return freeze, read(PACK / 'cases.json'), read(PACK / 'action_contract.json')


def _unique(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError('DUPLICATE_ACTION_KEY')
        obj[k] = v
    return obj


def parse_action(text):
    if type(text) is not str or len(text.encode()) > 65536:
        raise ValueError('INVALID_ACTION_OUTPUT')
    text = text.strip()
    if text.startswith('```'):
        fenced = re.fullmatch(r'```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```', text)
        if not fenced:
            raise ValueError('INVALID_ACTION_FENCE')
        text = fenced[1]
    obj = json.loads(text, object_pairs_hook=_unique,
                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError('NONFINITE_ACTION')))
    if type(obj) is not dict:
        raise ValueError('ACTION_NOT_OBJECT')
    for main, alias in (('action', 'type'), ('arguments', 'args'), ('conclusion', 'result')):
        if alias in obj:
            if main in obj and obj[main] != obj[alias]:
                raise ValueError('CONFLICTING_ACTION_ALIASES')
            obj[main] = obj.pop(alias)
    if obj.get('action') == 'TOOL_CALL':
        if set(obj) != {'action', 'tool', 'arguments'} or type(obj['tool']) is not str:
            raise ValueError('INVALID_TOOL_CALL_ACTION')
    elif obj.get('action') == 'FINAL':
        if (set(obj) != {'action', 'conclusion', 'evidence'} or type(obj['conclusion']) is not dict
                or type(obj['evidence']) is not list or any(type(v) is not str for v in obj['evidence'])
                or len(set(obj['evidence'])) != len(obj['evidence'])):
            raise ValueError('INVALID_FINAL_ACTION')
    else:
        raise ValueError('UNKNOWN_ACTION')
    return obj


def public_context(case, contract, observations, history):
    return {'task': case['initial'], 'action_contract': contract,
            'allowed_tools': case['tools'], 'conclusion_contract': case['conclusion_contract'],
            'limits': {'max_steps': 8, 'max_tool_calls': 6, 'retries': 0},
            'observations': observations, 'history': history}


def setup_budget(store, case, agent, run_id, freeze, contract):
    budget = SearchBudget(store)
    key = digest({'case_id': case['case_id'], 'model': agent.model_id})
    with store.transaction() as tx:
        if any(e['event_id'] == 'workflow-claim:' + key for e in tx.events()):
            tx.append('workflow-rename-denied:' + run_id, 'WORKFLOW_RENAME_DENIED',
                      {'run_id': run_id, 'case_id': case['case_id'], 'model_id': agent.model_id})
            duplicate = True
        else:
            tx.append('workflow-claim:' + key, 'WORKFLOW_CLAIMED',
                      {'run_id': run_id, 'case_id': case['case_id'], 'model_id': agent.model_id})
            duplicate = False
    if duplicate:
        raise ValueError('same fixture/model already owns a budget root; rename cannot reset it')
    task = TaskContract.from_dict(case['ledger_task'])
    condition = BenchmarkCondition(task)
    budget.register_concept(ConceptMapping('MAP-' + run_id, 'offline workflow conformance',
        'frozen fixture observations', 'synthetic engineering only', ('FEAT-workflow',)))
    budget.register_hypothesis(Hypothesis('HYP-' + run_id, 'CLAIM-' + run_id,
        'workflow conformance only', 'invariant failure', 'MAP-' + run_id))
    budget.register_family(ScientificSearchFamily('FAM-' + run_id, 'CLAIM-' + run_id,
        'offline fixture trial counters only; no strategy scientific qualification'))
    run = AgentBenchmarkRun(run_id, 'FAM-' + run_id, condition.condition_hash, agent.model_id, 'workflow-v01',
        digest(public_context(case, contract, [], [])), digest(freeze['sha256']),
        digest({'runtime': 'stdlib-and-existing-PyYAML'}), run_id,
        datetime.now(timezone.utc).isoformat(), provider=agent.provider_id)
    budget.register_run(run, condition, decision_snapshot=read(PACK / 'decision_snapshot.json'))
    experiment = ExperimentSpec('EXP-' + run_id, 'HYP-' + run_id, task.task_id,
        'DATA-' + task.data_spec_hash, task.cost_model_version, task.statistical_protocol_version,
        run.scientific_family_id, run_id, '2026-10-09T00:01:00Z')
    budget.register_experiment(experiment)
    tools = FixtureTools(case, budget, run, experiment, task,
                         DataSpec.from_dict(case['data_spec']), SnapshotManifest.from_dict(case['snapshot']))
    # Frozen prior trials are real ledger entries, not a resettable display counter.
    for i in range(case.get('prior_trials', 0)):
        attempt = f'PRIOR-{run_id}-{i}'
        budget.reserve(run_id, attempt, dict(attempts=1, candidate_trials=1, model_trials=int(i == 0),
            **dict.fromkeys(RESOURCE_DIMENSIONS, 0)), scientific_variant_id='VAR-' + attempt,
            experiment_id=experiment.experiment_id)
        budget.settle(attempt, 'FAILED', dict.fromkeys(RESOURCE_DIMENSIONS, 0),
                      failure='FROZEN_PRIOR_INVALID_SYNTHETIC_TRIAL')
    return budget, run, tools


def _envelope(budget, run, *, tool=False):
    first = budget.capability_accounting(run.benchmark_run_id)['usage']['attempts'] == 0
    return dict(attempts=1, candidate_trials=0, model_trials=int(first), validation_queries=int(tool),
                input_tokens=0, output_tokens=0, wall_milliseconds=1000, cpu_milliseconds=1000)


def _resources(started, cpu):
    return dict(input_tokens=0, output_tokens=0,
                wall_milliseconds=max(0, int((time.monotonic() - started) * 1000)),
                cpu_milliseconds=max(0, int((time.process_time() - cpu) * 1000)))


def run_workflow(store, case_id, agent, run_id):
    if isinstance(agent, ChatWorkflowAdapter) or agent.provider_id != 'scripted-offline':
        raise ValueError('offline Workflow v0.1 prohibits real providers')
    freeze, cases, contract = suite()
    case = cases[case_id]
    budget, run, tools = setup_budget(store, case, agent, run_id, freeze, contract)
    store.append('workflow-start:' + run_id, 'WORKFLOW_STARTED', {
        'run_id': run_id, 'case_id': case_id, 'freeze_sha256': sha256((PACK / 'freeze.json').read_bytes()).hexdigest(),
        'fixture_hash': digest(case['fixture']), 'case_hash': digest(case), 'policy_hash': digest(contract),
        'model_id': agent.model_id, 'budget_limits': dict(tools.task.budget_limits)})
    observations, history, final = [], [], None
    status, error = 'MAX_STEPS_EXCEEDED', None
    for step in range(1, freeze['max_steps'] + 1):
        attempt = f'STEP-{run_id}-{step}'
        try:
            budget.reserve(run_id, attempt, _envelope(budget, run))
        except BudgetDenied:
            status, error = 'BUDGET_EXHAUSTED', 'STEP_BUDGET_DENIED'
            break
        context = public_context(case, contract, observations, history)
        request = WorkerRequest(run_id, 'ACT-' + run_id, 'CTX-' + run_id, agent.provider_id,
            agent.model_id, 'workflow-v01', digest(context), digest(contract), tuple(case['tools']),
            {'context': digest(context), 'fixture': digest(case['fixture']), 'case': digest(case)})
        store.append('workflow-request:' + attempt, 'WORKFLOW_AGENT_REQUEST',
                     {'run_id': run_id, 'step': step, 'attempt_id': attempt,
                      'request': request.to_dict(), 'context': context})
        started, cpu = time.monotonic(), time.process_time()
        action, raw = None, None
        try:
            reply = agent.step(request, copy.deepcopy(context))
            if (not reply.ok or reply.failure_type or reply.finish_reason != 'stop'
                    or reply.input_tokens != 0 or reply.output_tokens != 0):
                raise RuntimeError('AGENT_PROVIDER_FAILED_OR_NONZERO_TOKENS')
            raw = reply.text
        except Exception:
            status, error = 'AGENT_FAILED', 'AGENT_PROVIDER_FAILED'
        else:
            try:
                action = parse_action(raw)
            except (ValueError, TypeError):
                status, error = 'INVALID_ACTION', 'ACTION_CONTRACT_REJECTED'
        used = _resources(started, cpu)
        if any(used[k] > 1000 for k in ('wall_milliseconds', 'cpu_milliseconds')):
            status, error = 'BUDGET_EXHAUSTED', 'STEP_RESOURCE_BREACH'
            action = None
        store.append('workflow-action:' + attempt, 'WORKFLOW_AGENT_ACTION',
                     {'run_id': run_id, 'step': step, 'attempt_id': attempt,
                      'raw': raw, 'action': action, 'error': error})
        budget.settle(attempt, 'SUCCEEDED' if action else 'FAILED', used,
            artifact_hashes={'action': digest(action)} if action else {}, failure=error if not action else None)
        history.append(action)
        if action is None:
            break
        if action['action'] == 'FINAL':
            final, status = action, 'COMPLETED'
            if any(t['state'] != 'SETTLED' for t in tools.trials.values()):
                status, error = 'INVALID_ACTION', 'FINAL_WITH_UNSETTLED_TRIAL'
            break
        try:
            validate_call(action['tool'], action['arguments'], case['tools'])
        except ValueError:
            status, error = 'INVALID_ACTION', 'TOOL_CONTRACT_REJECTED'
            break
        tool_attempt = f'TOOL-{run_id}-{step}'
        try:
            budget.reserve(run_id, tool_attempt, _envelope(budget, run, tool=True))
        except BudgetDenied:
            status, error = 'BUDGET_EXHAUSTED', 'TOOL_BUDGET_DENIED'
            break
        started, cpu = time.monotonic(), time.process_time()
        observation = {'observation_id': f'OBS-{run_id}-{step}', 'run_id': run_id, 'step': step,
                       'tool': action['tool'], 'arguments': action['arguments'], 'ok': True,
                       'result': None, 'error': None, 'attempt_id': tool_attempt}
        try:
            observation['result'] = tools.execute(action['tool'], action['arguments'])
        except BudgetDenied:
            observation.update(ok=False, error='TRIAL_BUDGET_DENIED')
            status, error = 'BUDGET_EXHAUSTED', observation['error']
        except Exception as exc:
            observation.update(ok=False, error=type(exc).__name__)
            status, error = 'TOOL_ERROR', observation['error']
        observation = copy.deepcopy(observation)
        store.append('workflow-observation:' + tool_attempt, 'WORKFLOW_TOOL_RESULT', observation)
        used = _resources(started, cpu)
        budget.settle(tool_attempt, 'SUCCEEDED' if observation['ok'] else 'FAILED', used,
            artifact_hashes={'observation': digest(observation)} if observation['ok'] else {},
            failure=observation['error'] if not observation['ok'] else None)
        observations.append(observation)
        tools.observations[observation['observation_id']] = observation
        if not observation['ok']:
            break
        if budget.capability_accounting(run_id)['blocked']:
            status, error = 'BUDGET_EXHAUSTED', 'RESOURCE_BREACH'
            break
    payload = {'run_id': run_id, 'case_id': case_id, 'model_id': agent.model_id,
        'status': status, 'error': error, 'final': final, 'steps': len(history),
        'tool_calls': len(observations), 'usage': budget.capability_accounting(run_id),
        'synthetic_trial_accounting': budget.scientific_accounting(run.scientific_family_id),
        'strategy_scientific_pass': False, 'real_agent_ability': 'UNVERIFIED'}
    store.append('workflow-end:' + run_id, 'WORKFLOW_COMPLETED', payload)
    from quant_rsi.harness.workflow_oracle import evaluate_workflow
    payload['evaluation'] = evaluate_workflow(case, payload, store.read())
    store.append('workflow-eval:' + run_id, 'WORKFLOW_EVALUATED', {'run_id': run_id, **payload['evaluation']})
    return payload


def replay(events, result, *, expected_anchor):
    """Read frozen observations only; no Agent/provider/tool execution or sampling."""
    from quant_rsi.harness.workflow_oracle import evaluate_workflow, verify_workflow_trace
    verify_events(events, expected_anchor)
    freeze, cases, contract = suite()
    case = cases[result['case_id']]
    verify_workflow_trace(case, result, events, contract)
    end = next(e['payload'] for e in events if e['event_id'] == 'workflow-end:' + result['run_id'])
    if end != {k: v for k, v in result.items() if k != 'evaluation'}:
        raise ValueError('WORKFLOW_RESULT_CHANGED')
    evaluation = evaluate_workflow(case, result, events)
    if evaluation != result['evaluation']:
        raise ValueError('WORKFLOW_SCORE_DRIFT')
    saved = next(e['payload'] for e in events if e['event_id'] == 'workflow-eval:' + result['run_id'])
    if saved != {'run_id': result['run_id'], **evaluation}:
        raise ValueError('WORKFLOW_EVALUATION_CHANGED')
    return {'status': 'FROZEN_OBSERVATIONS_REPLAY_MATCH', 'run_id': result['run_id'],
            'tool_reexecutions': 0, 'agent_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PACK / 'offline_run')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    freeze, cases, _ = suite()
    store = TraceStore(args.output / 'trace.sqlite')
    results = [run_workflow(store, case, ScriptedAgent(wrong),
                           'RUN-' + case + ('-wrong' if wrong else '-correct'))
               for case in freeze['case_order'] for wrong in (False, True)]
    events, anchor = store.read(), store.checkpoint()
    replay_results = [replay(events, r, expected_anchor=anchor) for r in results]
    report = {'status': 'OFFLINE_ENGINEERING_EXECUTED', 'labels': ['PUBLIC', 'UNSEALED', 'PROVISIONAL'],
        'previous_pilot': {'status': 'PASS_OFFLINE_COMPATIBILITY_READINESS', 'real_compatibility': 'UNVERIFIED',
                           'execution': 'DEFERRED_BY_USER'},
        'workflow_count': 3, 'fixture_cases': len(cases), 'results': results,
        'replay': replay_results, 'trace_anchor': {'sequence': anchor.sequence, 'event_hash': anchor.event_hash},
        'real_api_calls': 0, 'real_agent_workflow': 'UNVERIFIED', 'strategy_scientific_pass': False,
        'independence': {'same_author_agent_truth_evaluator': True, 'D08_achieved': False},
        'freeze_sha256': sha256((PACK / 'freeze.json').read_bytes()).hexdigest()}
    save(args.output / 'results.json', report)
    save(args.output / 'trace.json', events)
    print(json.dumps({'workflows': 3, 'cases': len(cases), 'executions': len(results),
                      'replays': len(replay_results), 'real_api_calls': 0}, indent=2))


if __name__ == '__main__':
    main()
