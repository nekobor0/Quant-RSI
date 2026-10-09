"""Offline fixture tools. Only the supervisor owns artifacts and ledger handles."""
from decimal import Decimal, InvalidOperation

from quant_rsi.data.pit import PITView, instant
from quant_rsi.data.pit import canonical_bytes
from hashlib import sha256

TOOL_ARGUMENTS = {
    'read_fixture': {'fixture_id': str},
    'inspect_response': {'response_ref': str},
    'validate_rows': {'response_ref': str},
    'list_vintages': {},
    'read_vintage': {'vintage_id': str},
    'check_asof_eligibility': {'vintage_ids': list},
    'inspect_budget': {},
    'reserve_trial': {},
    'run_synthetic_trial': {'trial_ref': str},
    'settle_trial': {'trial_ref': str},
}


def validate_call(tool, arguments, allowed):
    if tool not in allowed or tool not in TOOL_ARGUMENTS:
        raise ValueError('TOOL_NOT_ALLOWED')
    schema = TOOL_ARGUMENTS[tool]
    if type(arguments) is not dict or set(arguments) != set(schema):
        raise ValueError('INVALID_TOOL_ARGUMENTS')
    if any(type(arguments[k]) is not kind for k, kind in schema.items()):
        raise ValueError('INVALID_TOOL_ARGUMENT_TYPES')
    if 'vintage_ids' in arguments and (not arguments['vintage_ids'] or
            any(type(v) is not str for v in arguments['vintage_ids']) or
            len(set(arguments['vintage_ids'])) != len(arguments['vintage_ids'])):
        raise ValueError('INVALID_VINTAGE_IDS')


def row_check(document, policy):
    """Fixed row validation, independent of the Agent's summary or conclusion."""
    accepted, rejected = [], []
    for row in document['items']:
        reason = None
        if row.get('security') != policy['security']:
            reason = 'SECURITY_MISMATCH'
        elif row.get('trade_date') not in policy['trade_dates']:
            reason = 'DATE_OUTSIDE_REQUEST'
        else:
            try:
                value = Decimal(str(row.get('close')))
                if type(row.get('close')) is bool or not value.is_finite() or value <= 0:
                    reason = 'INVALID_PRICE'
            except InvalidOperation:
                reason = 'INVALID_PRICE'
        if reason:
            rejected.append({'row_id': row['row_id'], 'reason': reason})
        else:
            accepted.append(row['row_id'])
    return {'accepted_row_ids': accepted, 'rejected_rows': rejected, 'effective_rows': len(accepted)}


def vintage_metadata(row):
    spec = row['data_spec']
    return {'vintage_id': row['value']['vintage_id'], 'event_effective_date': spec['effective_from'],
            'published_at': spec['published_at'], 'available_at': spec['available_at']}


def synthetic_trial(fixture):
    training, validation = fixture['train_scores'], fixture['validation_scores']
    diagnostics = []
    if len(set(training)) <= 1:
        diagnostics.append('CONSTANT_SIGNAL')
    if not validation:
        diagnostics.append('NO_VALIDATION_SAMPLE')
    return {'status': 'INVALID' if diagnostics else 'SYNTHETIC_CHECK_ONLY',
            'diagnostics': diagnostics, 'evidence_sufficient': not diagnostics,
            'strategy_scientific_pass': False}


class FixtureTools:
    def __init__(self, case, budget, run, experiment, task, data, snapshot):
        self.case, self.budget, self.run = case, budget, run
        self.experiment, self.task = experiment, task
        self.observations = {}
        self.trials = {}
        self.view = (PITView(task, data, snapshot, lambda ref: canonical_bytes(case['fixture']))
                     if case['workflow_id'] == 'WFA-02' else None)

    def budget_result(self):
        used = self.budget.capability_accounting(self.run.benchmark_run_id)['usage']['candidate_trials']
        cap = self.task.budget_limits['candidate_trials']
        return {'used_trials': used, 'trial_limit': cap, 'remaining_trials': cap - used,
                'synthetic_only': True}

    def eligibility(self, row):
        meta = vintage_metadata(row)
        at = self.case['initial']['decision_asof']
        visible = {r.value['vintage_id'] for r in self.view.at(at)}
        reason = ('AVAILABLE_AFTER_DECISION' if instant(meta['available_at']) > instant(at)
                  else 'NOT_EFFECTIVE_OR_SUPERSEDED' if meta['vintage_id'] not in visible else None)
        return dict(meta, decision_asof=at, eligible=meta['vintage_id'] in visible, rejection_reason=reason)

    def execute(self, tool, args):
        if tool == 'read_fixture':
            if args['fixture_id'] != 'response':
                raise ValueError('UNKNOWN_FIXTURE')
            return self.case['fixture']
        if tool in ('inspect_response', 'validate_rows'):
            observation = self.observations.get(args['response_ref'])
            if not observation or observation['tool'] != 'read_fixture' or not observation['ok']:
                raise ValueError('UNAUTHENTICATED_RESPONSE_REFERENCE')
            raw = observation['result']
            if tool == 'inspect_response':
                return {'declared_count': raw['count'], 'items_len': len(raw['items']),
                        'metadata_consistent': raw['count'] == len(raw['items'])}
            return row_check(raw, self.case['row_policy'])
        if tool == 'list_vintages':
            return {'vintages': [vintage_metadata(row) for row in self.case['fixture']]}
        if tool in ('read_vintage', 'check_asof_eligibility'):
            rows = {r['value']['vintage_id']: r for r in self.case['fixture']}
            ids = [args['vintage_id']] if tool == 'read_vintage' else args['vintage_ids']
            listed = {v['vintage_id'] for o in self.observations.values()
                      if o['tool'] == 'list_vintages' and o['ok'] for v in o['result']['vintages']}
            if not set(ids) <= listed:
                raise ValueError('VINTAGE_NOT_LISTED')
            if any(v not in rows for v in ids):
                raise ValueError('UNKNOWN_VINTAGE')
            checks = [self.eligibility(rows[v]) for v in ids]
            if tool == 'check_asof_eligibility':
                return {'checks': checks}
            result = checks[0]
            # Unavailable versions return rejection metadata, never their data value.
            return dict(result, value=rows[ids[0]]['value']['estimate'] if result['eligible'] else None)
        if tool == 'inspect_budget':
            return self.budget_result()
        if tool == 'reserve_trial':
            if any(t['state'] != 'SETTLED' for t in self.trials.values()):
                raise ValueError('TRIAL_ALREADY_OPEN')
            trial = 'TRIAL-' + self.run.benchmark_run_id + '-' + str(len(self.trials) + 1)
            envelope = dict(attempts=1, candidate_trials=1, input_tokens=0, output_tokens=0,
                            wall_milliseconds=1000, cpu_milliseconds=1000)
            self.budget.reserve(self.run.benchmark_run_id, trial, envelope,
                                scientific_variant_id='VAR-' + trial, experiment_id=self.experiment.experiment_id)
            self.trials[trial] = {'state': 'RESERVED'}
            return {'trial_ref': trial, 'state': 'RESERVED', **self.budget_result()}
        if tool in ('run_synthetic_trial', 'settle_trial'):
            trial = args['trial_ref']
            state = self.trials.get(trial)
            if not state:
                raise ValueError('UNAUTHENTICATED_TRIAL_REFERENCE')
            if tool == 'run_synthetic_trial':
                if state['state'] != 'RESERVED':
                    raise ValueError('TRIAL_NOT_RESERVED')
                result = {'trial_ref': trial, **synthetic_trial(self.case['fixture'])}
                state.update(state='EXECUTED', result=result)
                self.budget.store.append('trial-result:' + trial, 'WORKFLOW_TRIAL_RESULT', result)
                return result
            if state['state'] != 'EXECUTED':
                raise ValueError('TRIAL_NOT_EXECUTED')
            result = state['result']
            self.budget.settle(trial, 'FAILED', dict(input_tokens=0, output_tokens=0,
                wall_milliseconds=0, cpu_milliseconds=0),
                artifact_hashes={'synthetic-trial-result': sha256(canonical_bytes(result)).hexdigest()},
                failure='INVALID_SYNTHETIC_TRIAL_NO_SCIENTIFIC_PASS')
            state['state'] = 'SETTLED'
            return {'trial_ref': trial, 'state': 'SETTLED', **self.budget_result()}
        raise ValueError('TOOL_NOT_IMPLEMENTED')
