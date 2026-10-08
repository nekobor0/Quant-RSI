"""Atomic per-agent budgets, separately projected final-claim family accounting.

Trusted supervisor API: this records declared usage, it does not meter a worker
process or authenticate the caller. Those deployment services are not Stage A.
"""
from datetime import datetime, timezone

from quant_rsi.contracts.condition import (
    AgentBenchmarkRun, BenchmarkCondition, BUDGET_DIMENSIONS, RESOURCE_DIMENSIONS,
    counters, validate_run_lineage, validate_experiment_binding,
)
from quant_rsi.contracts.research import (
    ConceptMapping, Hypothesis, ExperimentSpec, ScientificSearchFamily, family_ancestry, _id, _hash,
)


class BudgetDenied(ValueError):
    pass


def _objects(events, kind, cls):
    return [cls.from_dict(e['payload']) for e in events if e['kind'] == kind]


def _runs(events):
    return {r.benchmark_run_id: r for r in _objects(events, 'RUN_REGISTERED', AgentBenchmarkRun)}


def _attempts(events):
    return {e['payload']['attempt_id']: e['payload'] for e in events if e['kind'] == 'ATTEMPT_STARTED'}


def _terminals(events):
    return {e['payload']['attempt_id']: e['payload'] for e in events if e['kind'] in ('ATTEMPT_SETTLED', 'USAGE_RECONCILED')}


def _usage(events, root):
    total = dict.fromkeys(BUDGET_DIMENSIONS, 0)
    blocked = False
    terminal = _terminals(events)
    for identity, attempt in _attempts(events).items():
        if attempt['budget_root_run_id'] != root:
            continue
        charge = dict(attempt['envelope'])
        result = terminal.get(identity)
        if result is not None:
            if result['actual_resources'] is not None:
                charge.update(result['actual_resources'])
            if result['usage_state'] in ('UNKNOWN', 'BREACH'):
                blocked = True
        for key, value in charge.items():
            total[key] += value
    return total, blocked


def _actual(value):
    if value is None:
        return None
    value = counters(value)
    if set(value) != set(RESOURCE_DIMENSIONS):
        raise ValueError('actual resources must report every resource dimension')
    return value


class SearchBudget:
    def __init__(self, trace_store):
        self.store = trace_store

    def register_concept(self, mapping):
        if type(mapping) is not ConceptMapping:
            raise ValueError('ConceptMapping required')
        return self.store.append('concept:' + mapping.concept_mapping_id, 'CONCEPT_REGISTERED', mapping.to_dict())

    def register_hypothesis(self, hypothesis):
        if type(hypothesis) is not Hypothesis:
            raise ValueError('Hypothesis required')
        with self.store.transaction() as tx:
            events = tx.events()
            if not any(e['kind'] == 'CONCEPT_REGISTERED' and e['payload']['concept_mapping_id'] == hypothesis.concept_mapping_id for e in events):
                raise ValueError('hypothesis references unregistered concept mapping')
            existing = _objects(events, 'HYPOTHESIS_REGISTERED', Hypothesis)
            if any(h.claim_id == hypothesis.claim_id and h.hypothesis_id != hypothesis.hypothesis_id for h in existing):
                raise ValueError('claim already belongs to another hypothesis')
            return tx.append('hypothesis:' + hypothesis.hypothesis_id, 'HYPOTHESIS_REGISTERED', hypothesis.to_dict())

    def register_family(self, family):
        if type(family) is not ScientificSearchFamily:
            raise ValueError('ScientificSearchFamily required')
        with self.store.transaction() as tx:
            events = tx.events()
            if not any(h.claim_id == family.claim_id for h in _objects(events, 'HYPOTHESIS_REGISTERED', Hypothesis)):
                raise ValueError('family references unregistered hypothesis claim')
            families = _objects(events, 'FAMILY_REGISTERED', ScientificSearchFamily)
            existing = next((f for f in families if f.scientific_family_id == family.scientific_family_id), None)
            if existing is None:
                family_ancestry(family.scientific_family_id, families + [family])
            return tx.append('family:' + family.scientific_family_id, 'FAMILY_REGISTERED', family.to_dict())

    def register_run(self, run, condition, *, decision_snapshot=None):
        if type(run) is not AgentBenchmarkRun or type(condition) is not BenchmarkCondition:
            raise ValueError('run and condition contracts required')
        condition.task.verify_frozen_condition(decision_snapshot)
        condition.task.authorize_dispatch()
        if run.condition_hash != condition.condition_hash:
            raise ValueError('run/condition hash mismatch')
        if datetime.fromisoformat(run.registered_at) < datetime.fromisoformat(condition.task.frozen_at):
            raise ValueError('run registered before task freeze')
        with self.store.transaction() as tx:
            if datetime.fromisoformat(run.registered_at) > datetime.now(timezone.utc):
                raise ValueError('run registration cannot be in the future')
            events = tx.events()
            families = _objects(events, 'FAMILY_REGISTERED', ScientificSearchFamily)
            ancestry = family_ancestry(run.scientific_family_id, families)
            runs = _runs(events)
            validate_run_lineage(run, runs.values())
            if run.parent_run_id and runs[run.parent_run_id].scientific_family_id not in ancestry:
                raise ValueError('continuation cannot erase scientific ancestry')
            tx.append(condition.task.decision_snapshot_ref, 'DECISION_SNAPSHOT', decision_snapshot)
            tx.append('condition:' + condition.condition_hash, 'CONDITION_REGISTERED', condition.to_dict())
            return tx.append('run:' + run.benchmark_run_id, 'RUN_REGISTERED', run.to_dict())

    def register_experiment(self, experiment):
        if type(experiment) is not ExperimentSpec or experiment.execution_started_at is not None:
            raise ValueError('only unexecuted preregistered ExperimentSpec may be registered')
        if datetime.fromisoformat(experiment.preregistered_at) >= datetime.now(timezone.utc):
            raise ValueError('preregistration cannot be in the future')
        with self.store.transaction() as tx:
            events = tx.events()
            run = _runs(events).get(experiment.benchmark_run_id)
            if run is None:
                raise ValueError('experiment run not registered')
            condition = next(BenchmarkCondition.from_dict(e['payload']) for e in events
                             if e['event_id'] == 'condition:' + run.condition_hash)
            validate_experiment_binding(experiment, condition.task, run)
            hypothesis = next((h for h in _objects(events, 'HYPOTHESIS_REGISTERED', Hypothesis)
                               if h.hypothesis_id == experiment.hypothesis_id), None)
            family = next(f for f in _objects(events, 'FAMILY_REGISTERED', ScientificSearchFamily)
                          if f.scientific_family_id == experiment.scientific_family_id)
            if hypothesis is None or hypothesis.claim_id != family.claim_id:
                raise ValueError('experiment references unregistered or mismatched hypothesis')
            return tx.append('experiment:' + experiment.experiment_id, 'EXPERIMENT_REGISTERED', experiment.to_dict())

    def reserve(self, benchmark_run_id, attempt_id, envelope, *, scientific_variant_id=None, retry_of=None, experiment_id=None):
        _id(attempt_id, 'attempt_id')
        supplied = counters(envelope)
        if not set(RESOURCE_DIMENSIONS) <= set(supplied):
            raise ValueError('every resource dimension requires an explicit reservation')
        envelope = {**dict.fromkeys(BUDGET_DIMENSIONS, 0), **supplied}
        if envelope['attempts'] != 1 or envelope['candidate_trials'] not in (0, 1):
            raise ValueError('one attempt and at most one candidate per reservation')
        if scientific_variant_id is not None:
            _id(scientific_variant_id, 'scientific_variant_id')
        if retry_of is not None:
            _id(retry_of, 'retry_of')
        denial = None
        with self.store.transaction() as tx:
            events = tx.events()
            runs = _runs(events)
            if benchmark_run_id not in runs:
                raise ValueError('unregistered benchmark run')
            run = runs[benchmark_run_id]
            payload = dict(attempt_id=attempt_id, benchmark_run_id=benchmark_run_id,
                           budget_root_run_id=run.budget_root_run_id, scientific_family_id=run.scientific_family_id,
                           condition_hash=run.condition_hash, scientific_variant_id=scientific_variant_id,
                           retry_of=retry_of, envelope=envelope, experiment_id=experiment_id)
            previous = next((e for e in events if e['event_id'] == 'attempt:' + attempt_id), None)
            if previous:
                expected = {k: v for k, v in previous['payload'].items() if k != 'denial_reason'}
                if expected != payload:
                    raise ValueError('attempt identity collision')
                if previous['kind'] == 'ATTEMPT_DENIED':
                    denial = previous['payload']['denial_reason']
                else:
                    return previous
            else:
                attempts, terminals = _attempts(events), _terminals(events)
                if scientific_variant_id is not None:
                    experiment = next((ExperimentSpec.from_dict(e['payload']) for e in events
                                       if e['kind'] == 'EXPERIMENT_REGISTERED' and e['payload']['experiment_id'] == experiment_id), None)
                    if experiment is None or experiment.benchmark_run_id != benchmark_run_id:
                        raise ValueError('scientific attempt requires its preregistered experiment')
                root_attempts = [a for a in attempts.values() if a['budget_root_run_id'] == run.budget_root_run_id]
                if retry_of:
                    prior = attempts.get(retry_of)
                    if (prior is None or retry_of not in terminals or prior['budget_root_run_id'] != run.budget_root_run_id
                            or prior['scientific_variant_id'] != scientific_variant_id
                            or prior['experiment_id'] != experiment_id
                            or terminals[retry_of]['status'] == 'SUCCEEDED' or envelope['retries'] != 1
                            or envelope['candidate_trials'] != 0):
                        raise ValueError('retry must reference a failed attempt in same budget root and variant')
                elif envelope['retries'] != 0 or (scientific_variant_id is None) != (envelope['candidate_trials'] == 0):
                    raise ValueError('new candidate identity and trial counter must agree')
                elif scientific_variant_id and any(a['scientific_variant_id'] == scientific_variant_id for a in root_attempts):
                    raise ValueError('existing variant requires explicit retry lineage')
                if not root_attempts and envelope['model_trials'] < 1:
                    raise ValueError('first root attempt must account for model trial')
                if run.parent_run_id and run.prompt_hash != runs[run.parent_run_id].prompt_hash:
                    if not any(a['benchmark_run_id'] == benchmark_run_id for a in root_attempts) and envelope['prompt_revisions'] < 1:
                        raise ValueError('changed continuation prompt must be counted')
                condition = next(BenchmarkCondition.from_dict(e['payload']) for e in events
                                 if e['kind'] == 'CONDITION_REGISTERED' and BenchmarkCondition.from_dict(e['payload']).condition_hash == run.condition_hash)
                snapshot = next(e['payload'] for e in events if e['event_id'] == condition.task.decision_snapshot_ref)
                condition.task.verify_frozen_condition(snapshot)
                condition.task.authorize_dispatch()
                used, blocked = _usage(events, run.budget_root_run_id)
                if blocked:
                    denial = 'UNRESOLVED_USAGE'
                elif any(used[k] + envelope[k] > condition.task.budget_limits[k] for k in BUDGET_DIMENSIONS):
                    denial = 'BUDGET_EXHAUSTED'
                if denial:
                    tx.append('attempt:' + attempt_id, 'ATTEMPT_DENIED', dict(payload, denial_reason=denial))
                else:
                    return tx.append('attempt:' + attempt_id, 'ATTEMPT_STARTED', payload)
        raise BudgetDenied(denial)

    def record_output(self, attempt_id, candidate_id, artifact_ref, artifact_hash, *, kind='STRATEGY'):
        """Bind an output while its attempt is open; state remains in this trace."""
        _id(candidate_id, 'candidate_id')
        _hash(artifact_hash)
        if type(artifact_ref) is not str or not artifact_ref.strip() or kind not in ('STRATEGY', 'FAILURE_DIAGNOSTIC', 'PUBLIC_FIXTURE'):
            raise ValueError('valid output reference and kind required')
        payload = dict(attempt_id=attempt_id, candidate_id=candidate_id, artifact_ref=artifact_ref,
                       artifact_hash=artifact_hash, kind=kind)
        with self.store.transaction() as tx:
            events = tx.events()
            attempt = _attempts(events).get(attempt_id)
            if kind == 'PUBLIC_FIXTURE' and (attempt is None or attempt_id in _terminals(events)):
                raise ValueError('public output requires open reserved attempt')
            previous = next((e for e in events if e['event_id'] == 'output:' + candidate_id), None)
            if previous is not None:
                if kind == 'PUBLIC_FIXTURE':
                    raise ValueError('one candidate output per public attempt')
                return tx.append('output:' + candidate_id, 'ATTEMPT_OUTPUT', payload)
            if attempt is None or attempt_id in _terminals(events):
                raise ValueError('output requires open reserved attempt')
            public = kind == 'PUBLIC_FIXTURE'
            if public:
                experiment = next((e['payload'] for e in events if e['kind'] == 'EXPERIMENT_REGISTERED'
                                   and e['payload']['experiment_id'] == attempt['experiment_id']), None)
                if (attempt['scientific_variant_id'] is not None or attempt['envelope']['candidate_trials'] != 0
                        or experiment is None or experiment['benchmark_run_id'] != attempt['benchmark_run_id']
                        or experiment['scientific_family_id'] != attempt['scientific_family_id']
                        or experiment['task_id'] != next((e['payload']['task']['task_id'] for e in events
                            if e['kind'] == 'CONDITION_REGISTERED'
                            and e['event_id'] == 'condition:' + attempt['condition_hash']), None)):
                    raise ValueError('public fixture requires counted zero-trial run/experiment binding')
            elif (attempt['scientific_variant_id'] is None
                    or (attempt['envelope']['candidate_trials'] != 1 and attempt['retry_of'] is None)):
                raise ValueError('scientific output requires counted variant or validated retry lineage')
            if any(e['kind'] == 'ATTEMPT_OUTPUT' and e['payload']['attempt_id'] == attempt_id for e in events):
                raise ValueError('one candidate output per attempt; new candidates require a counted attempt')
            return tx.append('output:' + candidate_id, 'ATTEMPT_OUTPUT', payload)

    def settle(self, attempt_id, status, actual_resources, *, artifact_hashes=None, failure=None):
        if status not in ('SUCCEEDED', 'FAILED', 'TIMEOUT', 'ABORTED', 'CANCELLED', 'UNKNOWN_TERMINATION'):
            raise ValueError('unknown terminal status')
        actual_resources = _actual(actual_resources)
        artifact_hashes = {} if artifact_hashes is None else dict(artifact_hashes)
        for path, digest in artifact_hashes.items():
            if type(path) is not str or not path.strip():
                raise ValueError('artifact reference required')
            _hash(digest)
        if status == 'SUCCEEDED' and (actual_resources is None or not artifact_hashes or failure is not None):
            raise ValueError('success requires measured usage and artifact hashes')
        if status != 'SUCCEEDED' and (type(failure) is not str or not failure.strip()):
            raise ValueError('failure or interruption reason must be preserved')
        with self.store.transaction() as tx:
            events = tx.events()
            attempt = _attempts(events).get(attempt_id)
            if attempt is None:
                raise ValueError('cannot settle an unstarted attempt')
            outputs = [e['payload'] for e in events if e['kind'] == 'ATTEMPT_OUTPUT' and e['payload']['attempt_id'] == attempt_id]
            if any(artifact_hashes.get(o['artifact_ref']) != o['artifact_hash'] for o in outputs):
                raise ValueError('settlement contradicts registered output artifacts')
            state = 'UNKNOWN' if actual_resources is None else (
                'BREACH' if any(actual_resources[k] > attempt['envelope'][k] for k in RESOURCE_DIMENSIONS) else 'KNOWN')
            return tx.append('settle:' + attempt_id, 'ATTEMPT_SETTLED', dict(
                attempt_id=attempt_id, status=status, actual_resources=actual_resources,
                usage_state=state, artifact_hashes=artifact_hashes, failure=failure))

    def reconcile(self, attempt_id, actual_resources):
        actual_resources = _actual(actual_resources)
        if actual_resources is None:
            raise ValueError('reconciliation requires measured usage')
        with self.store.transaction() as tx:
            events = tx.events()
            original = next((e['payload'] for e in events if e['event_id'] == 'settle:' + attempt_id), None)
            if original is None or original['usage_state'] != 'UNKNOWN':
                raise ValueError('only unknown usage can be reconciled')
            attempt = _attempts(events)[attempt_id]
            state = 'BREACH' if any(actual_resources[k] > attempt['envelope'][k] for k in RESOURCE_DIMENSIONS) else 'KNOWN'
            return tx.append('reconcile:' + attempt_id, 'USAGE_RECONCILED', dict(
                original, actual_resources=actual_resources, usage_state=state))

    def recover_incomplete(self):
        """Custodian calls only after ensuring no old worker is still executing."""
        with self.store.transaction() as tx:
            events = tx.events()
            terminals = _terminals(events)
            recovered = []
            for identity in _attempts(events):
                if identity not in terminals:
                    outputs = {e['payload']['artifact_ref']: e['payload']['artifact_hash'] for e in events
                               if e['kind'] == 'ATTEMPT_OUTPUT' and e['payload']['attempt_id'] == identity}
                    tx.append('settle:' + identity, 'ATTEMPT_SETTLED', dict(
                        attempt_id=identity, status='UNKNOWN_TERMINATION', actual_resources=None,
                        usage_state='UNKNOWN', artifact_hashes=outputs, failure='custodian recovery of incomplete attempt'))
                    recovered.append(identity)
            return recovered

    def capability_accounting(self, benchmark_run_id):
        events = self.store.read()
        run = _runs(events)[benchmark_run_id]
        usage, blocked = _usage(events, run.budget_root_run_id)
        return {'benchmark_run_id': benchmark_run_id, 'budget_root_run_id': run.budget_root_run_id,
                'usage': usage, 'blocked': blocked, 'capability_score': None,
                'score_status': 'NOT_IMPLEMENTED_W11_OUT_OF_SCOPE'}

    def scientific_accounting(self, scientific_family_id):
        events = self.store.read()
        ancestry = family_ancestry(scientific_family_id, _objects(events, 'FAMILY_REGISTERED', ScientificSearchFamily))
        attempts = [a for a in _attempts(events).values() if a['scientific_family_id'] in ancestry]
        variants = {(a['budget_root_run_id'], a['scientific_variant_id']) for a in attempts if a['scientific_variant_id']}
        return {'scientific_family_id': scientific_family_id, 'ancestry': sorted(ancestry),
                'attempt_count': len(attempts), 'candidate_variant_count': len(variants),
                'attempt_ids': sorted(a['attempt_id'] for a in attempts), 'effective_independent_trials': None,
                'calibration_status': 'D04B_DEFERRED', 'capability_penalty': None}
