"""Trusted CP references only. This module NEVER loads or executes submissions."""
import copy
import math


def number(value, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('FINITE_REAL_REQUIRED')
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError('NUMBER_OUT_OF_RANGE')
    return value


def sequence(value):
    if type(value) is not list:
        raise ValueError('LIST_REQUIRED')
    return [number(v) for v in value]


def normalize_rows(rows):
    if type(rows) is not list:
        raise ValueError('LIST_REQUIRED')
    keyed = {}
    for row in rows:
        if type(row) is not dict or set(row) != {'security', 'date', 'price'}:
            raise ValueError('ROW_FIELDS_INVALID')
        if any(type(row[k]) is not str or not row[k] for k in ('security', 'date')):
            raise ValueError('NONEMPTY_STRING_REQUIRED')
        price = number(row['price'], positive=True)
        key = row['security'], row['date']
        if key in keyed and keyed[key]['price'] != price:
            raise ValueError('CONFLICTING_PRICE')
        keyed[key] = copy.deepcopy(row)
    return [keyed[key] for key in sorted(keyed)]


def lagged_mean(values, window):
    values = sequence(values)
    if type(window) is not int or window <= 0:
        raise ValueError('POSITIVE_INTEGER_WINDOW_REQUIRED')
    return [None if t < window else sum(values[t-window:t])/window for t in range(len(values))]


def interval_pnl(returns, signals, cost_rate):
    returns, signals = sequence(returns), sequence(signals)
    cost = number(cost_rate, nonnegative=True)
    if len(returns) != len(signals):
        raise ValueError('LENGTH_MISMATCH')
    positions = [0] + signals[:-1] if signals else []
    turnover = [abs(q-(positions[t-1] if t else 0)) for t, q in enumerate(positions)]
    pnl = [q*r-cost*turn for q, r, turn in zip(positions, returns, turnover)]
    return dict(positions=positions, turnover=turnover, pnl=pnl, pnl_sum=sum(pnl))


def build_ledger(events):
    if type(events) is not list:
        raise ValueError('LIST_REQUIRED')
    ledger, running = [], 0
    for event in events:
        if type(event) is not dict or set(event) != {'event_id', 'amount'}:
            raise ValueError('EVENT_FIELDS_INVALID')
        if type(event['event_id']) is not str or not event['event_id']:
            raise ValueError('NONEMPTY_EVENT_ID_REQUIRED')
        running += number(event['amount'])
        ledger.append(dict(event_id=event['event_id'], amount=event['amount'], cumulative_amount=running))
    return ledger


BROKEN_LEDGER_SOURCE = '''def build_ledger(events, ledger=[]):
    running = 0
    for event in events:
        running += event["amount"]
        ledger.append({"event_id": event["event_id"], "amount": event["amount"], "cumulative_amount": running})
    return ledger
'''


def contracts():
    return dict(status='PREPARED_NOT_EXECUTION_ACCEPTED', model_code_executions=0,
        environment_status='BLOCKED_ENVIRONMENT_CAPABILITY', route='Docker Desktop WSL2 Linux',
        future_execution=dict(network='none', user='nonroot', root_filesystem='read_only',
            capabilities='drop_all', no_new_privileges=True, seccomp='default',
            memory_mb=512, pids=32, cpu=.5, timeout_seconds=5, tmpfs_mb=16,
            submission_bytes=65536, output_bytes=262144, image_digest=None,
            mounts='submission/public_input_only; no repository, oracle, credentials or Docker socket'),
        common=dict(number='finite int/float; never bool', container='list only',
            invalid='ValueError', input_mutation='forbidden', tolerance=1e-8,
            references='src/quant_rsi/harness/supplement_cp.py; trusted author code, not model submission'),
        tasks={
            'Q-CP-01': dict(signature='normalize_rows(rows)', fields=['security', 'date', 'price'],
                strings='nonempty, preserve exactly', price='strictly positive finite real',
                output='sorted by (security,date), merge identical rows; conflicting key price raises ValueError',
                example_input=[dict(security='B', date='D1', price=2), dict(security='A', date='D1', price=1)],
                properties=['empty', 'permutation_invariant', 'duplicate_idempotent', 'conflicting_prices',
                            'invalid_fields_types_values', 'fresh_result_no_input_mutation']),
            'Q-CP-02': dict(signature='lagged_mean(values, window)', window='positive int, never bool',
                output='length equals input; mean of values[t-window:t], null if insufficient history',
                example_input=dict(values=[10, 12, 14, 16], window=2), example_output=[None, None, 11, 13],
                properties=['empty', 'window_boundaries', 'future_suffix_invariance', 'current_value_exclusion',
                            'invalid_window_and_values', 'input_preserved']),
            'Q-CP-03': dict(signature='interval_pnl(returns, signals, cost_rate)',
                output_fields=['positions', 'turnover', 'pnl', 'pnl_sum'],
                formula='q[0]=0; q[t]=signals[t-1]; turn[t]=abs(q[t]-q[t-1]), q[-1]=0; pnl=q*r-cost*turn',
                interpretation='arithmetic interval PnL sum, NOT compound wealth return',
                example_input=dict(returns=[0, .1, -.1, .05], signals=[1, 1, 0, -1], cost_rate=.01),
                example_output=dict(positions=[0, 1, 1, 0], turnover=[0, 1, 0, 1], pnl=[0, .09, -.1, -.01], pnl_sum=-.02),
                properties=['empty', 'zero_signals', 'short_positions', 'direction_changes', 'length_mismatch',
                            'nonnegative_finite_cost', 'signal_lag', 'input_preserved']),
            'Q-CP-04': dict(signature='build_ledger(events)', event_fields=['event_id', 'amount'],
                output_fields=['event_id', 'amount', 'cumulative_amount'], broken_source=BROKEN_LEDGER_SOURCE,
                semantics='append each current-call event with cumulative current-call amount; no cross-call state',
                example_input=[dict(event_id='E1', amount=2), dict(event_id='E2', amount=-1), dict(event_id='E3', amount=3)],
                properties=['empty', 'same_process_twice', 'A_B_A', 'return_mutation_independence',
                            'input_preserved', 'invalid_events'],
                session_rule='all repetition and mutation probes run in the SAME isolated process')})

_normalize = normalize_rows
def normalize_rows(rows):
    if type(rows) is not list: raise ValueError('LIST_REQUIRED')
    keyed = {}
    for row in rows:
        _normalize([row])
        keyed[(row['security'],row['date'])] = copy.deepcopy(row)
    return [keyed[k] for k in sorted(keyed)]

# Controlled instrumentation: observations only, no expected answers or scoring.
_candidate_functions = {n: globals()[n] for n in
    ('normalize_rows', 'lagged_mean', 'interval_pnl', 'build_ledger')}
def _decode_fixture(x):
    if isinstance(x, dict) and set(x) == {'$float'}:
        return float(x['$float'])
    if isinstance(x, dict) and set(x) == {'$tuple'}:
        return tuple(_decode_fixture(v) for v in x['$tuple'])
    if isinstance(x, list):
        return [_decode_fixture(v) for v in x]
    if isinstance(x, dict):
        return {k: _decode_fixture(v) for k, v in x.items()}
    return x
def _snapshot(x):
    if isinstance(x, float) and not math.isfinite(x):
        return {'$float': 'nan' if math.isnan(x) else 'inf' if x > 0 else '-inf'}
    if isinstance(x, tuple):
        return {'$tuple': [_snapshot(v) for v in x]}
    if isinstance(x, list):
        return [_snapshot(v) for v in x]
    if isinstance(x, dict):
        return {k: _snapshot(v) for k, v in x.items()}
    return x
def inspect_call(name, encoded_args, mutate_result=None):
    args = _decode_fixture(encoded_args)
    before = _snapshot(args)
    result, error = None, None
    try:
        result = _candidate_functions[name](*args)
        if mutate_result is not None:
            obj = result
            for key in mutate_result['path'][:-1]:
                obj = obj[key]
            obj[mutate_result['path'][-1]] = mutate_result['value']
    except Exception as exc:
        error = type(exc).__name__
    # Preserve normal result object identity for same-process retained mutation.
    return {'result': result, 'exception': error, 'before': before, 'after': _snapshot(args)}
