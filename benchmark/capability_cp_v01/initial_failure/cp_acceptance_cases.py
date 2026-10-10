"""Public CP probes and independently specified expected observations.

No submitted code is evaluated here. All candidate functions run in Docker.
Non-JSON numbers/tuples are transported as explicit synthetic fixture tags.
"""
import copy

from quant_rsi.harness.agent_workflow import ROOT, read


DRIVER = '''
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
'''


def materials():
    contracts = read(ROOT / 'benchmark/capability_supplement_v01/cp_contracts.json')
    tasks = {}
    functions = ['normalize_rows', 'lagged_mean', 'interval_pnl', 'build_ledger']
    for number, function in enumerate(functions, 1):
        task = f'Q-CP-{number:02}'
        tasks[task] = dict(function=function, cases=[], operations=[], links=[])

    def add(n, label, args, expected=None, error=None, properties=(), mutate=None):
        task = tasks[f'Q-CP-{n:02}']
        observed = dict(result=expected, exception=error, before=copy.deepcopy(args), after=copy.deepcopy(args))
        op = dict(function='inspect_call', args=[task['function'], args, mutate])
        task['operations'].append(op)
        task['cases'].append(dict(label=label, properties=list(properties), expected=observed))
        return len(task['cases'])-1

    def invalid(n, label, args, property):
        add(n, label, args, error='ValueError', properties=[property])

    def link(n, label, left, right, property, prefix=None):
        tasks[f'Q-CP-{n:02}']['links'].append(dict(label=label, left=left, right=right,
            property=property, prefix=prefix))

    a = dict(security='A', date='D1', price=1)
    b = dict(security='B', date='D1', price=2)
    c = dict(security='A', date='D2', price=3)
    add(1, 'empty', [[]], [], properties=['empty'])
    i = add(1, 'sorted', [[b, c, a]], [a, c, b], properties=['permutation_invariant'])
    j = add(1, 'permuted', [[a, b, c]], [a, c, b], properties=['permutation_invariant'])
    link(1, 'permutation', i, j, 'permutation_invariant')
    k = add(1, 'duplicates', [[a, b, c, a, b]], [a, c, b], properties=['duplicate_idempotent'])
    link(1, 'duplicate', j, k, 'duplicate_idempotent')
    invalid(1, 'conflict', [[a, dict(a, price=2)]], 'conflicting_prices')
    invalid(1, 'conflict_below_output_tolerance', [[a, dict(a, price=1+1e-9)]], 'conflicting_prices')
    add(1, 'exact_strings', [[dict(security=' A ', date=' D ', price=1)]],
        [dict(security=' A ', date=' D ', price=1)], properties=['invalid_fields_types_values'])
    add(1, 'fresh_input', [[a]], [dict(a, price=999)], properties=['fresh_result_no_input_mutation'],
        mutate=dict(path=[0, 'price'], value=999))
    invalid(1, 'tuple_container', [{'$tuple': [a]}], 'invalid_fields_types_values')
    invalid(1, 'row_not_dict', [[1]], 'invalid_fields_types_values')
    for label, row in [('missing', {'security': 'A', 'price': 1}), ('extra', dict(a, extra=0)),
                       ('empty_security', dict(a, security='')), ('empty_date', dict(a, date='')),
                       ('numeric_id', dict(a, security=1)), ('bool_date', dict(a, date=True))]:
        invalid(1, label, [[row]], 'invalid_fields_types_values')
    for value in (0, -1, True, '1', None, {'$float': 'nan'}, {'$float': 'inf'}, {'$float': '-inf'}):
        invalid(1, 'price-'+str(value), [[dict(a, price=value)]], 'invalid_fields_types_values')

    add(2, 'empty', [[], 2], [], properties=['empty'])
    i = add(2, 'window2', [[10, 12, 14, 16], 2], [None, None, 11, 13], properties=['window_boundaries', 'input_preserved'])
    j = add(2, 'changed_future', [[10, 12, 999, 777], 2], [None, None, 11, 505.5],
        properties=['future_suffix_invariance', 'current_value_exclusion'])
    link(2, 'prefix_through_current', i, j, 'current_value_exclusion', 3)
    k = add(2, 'extended_future', [[10, 12, 14, 16, 999], 2], [None, None, 11, 13, 15], properties=['future_suffix_invariance'])
    link(2, 'suffix_append', i, k, 'future_suffix_invariance', 4)
    add(2, 'window1', [[-2, 0, 5], 1], [None, -2, 0], properties=['window_boundaries'])
    add(2, 'window_equal', [[1, 2], 2], [None, None], properties=['window_boundaries'])
    add(2, 'window_larger', [[1, 2], 3], [None, None], properties=['window_boundaries'])
    for value in (0, -1, True, 2.0, '2', None):
        invalid(2, 'window-'+str(value), [[1, 2], value], 'invalid_window_and_values')
    for value in (True, '1', None, {'$float': 'nan'}, {'$float': 'inf'}, {'$float': '-inf'}):
        invalid(2, 'value-'+str(value), [[1, value], 1], 'invalid_window_and_values')
    invalid(2, 'tuple', [{'$tuple': [1, 2]}, 1], 'invalid_window_and_values')
    invalid(2, 'invalid_empty_window', [[], 0], 'invalid_window_and_values')

    def pnl(q, turn, p):
        return dict(positions=q, turnover=turn, pnl=p, pnl_sum=sum(p))
    add(3, 'empty', [[], [], 0], pnl([], [], []), properties=['empty'])
    add(3, 'zeros', [[.1, -.2, .3], [0, 0, 0], .02], pnl([0, 0, 0], [0, 0, 0], [0, 0, 0]), properties=['zero_signals'])
    i = add(3, 'lag_cost', [[0, .1, -.1, .05], [1, 1, 0, -1], .01],
        pnl([0, 1, 1, 0], [0, 1, 0, 1], [0, .09, -.1, -.01]), properties=['signal_lag', 'input_preserved'])
    j = add(3, 'last_signal', [[0, .1, -.1, .05], [1, 1, 0, 999], .01],
        pnl([0, 1, 1, 0], [0, 1, 0, 1], [0, .09, -.1, -.01]), properties=['signal_lag'])
    link(3, 'last_signal_not_used', i, j, 'signal_lag')
    add(3, 'short', [[.1, -.1, .2], [-1, -1, 0], .01],
        pnl([0, -1, -1], [0, 1, 0], [0, .09, -.2]), properties=['short_positions'])
    add(3, 'flip', [[0, .1, .1, -.1], [1, -1, 1, 0], .01],
        pnl([0, 1, -1, 1], [0, 1, 2, 2], [0, .09, -.12, -.12]), properties=['direction_changes'])
    add(3, 'zero_cost_sum', [[0, .5, .5], [1, 1, 1], 0],
        pnl([0, 1, 1], [0, 1, 0], [0, .5, .5]), properties=['nonnegative_finite_cost', 'signal_lag'])
    invalid(3, 'length', [[.1], [], 0], 'length_mismatch')
    for value in (-.01, True, '0', None, {'$float': 'nan'}, {'$float': 'inf'}, {'$float': '-inf'}):
        invalid(3, 'cost-'+str(value), [[.1], [1], value], 'nonnegative_finite_cost')
    invalid(3, 'invalid_empty_cost', [[], [], -1], 'nonnegative_finite_cost')
    for field in (0, 1):
        for value in (True, '1', None, {'$float': 'nan'}, {'$float': 'inf'}, {'$float': '-inf'}):
            args = [[.1], [1], 0]
            args[field] = [value]
            invalid(3, f'series{field}-'+str(value), args, 'input_preserved')
        args = [[.1], [1], 0]
        args[field] = {'$tuple': args[field]}
        invalid(3, f'tuple{field}', args, 'input_preserved')

    a = [dict(event_id='A1', amount=2), dict(event_id='A2', amount=-1)]
    b = [dict(event_id='B1', amount=100)]
    av = [dict(a[0], cumulative_amount=2), dict(a[1], cumulative_amount=1)]
    add(4, 'empty', [[]], [], properties=['empty'])
    i = add(4, 'A_first', [a], av, properties=['same_process_twice', 'A_B_A', 'input_preserved'])
    j = add(4, 'A_repeat', [a], av, properties=['same_process_twice'])
    link(4, 'repeat', i, j, 'same_process_twice')
    add(4, 'B', [b], [dict(b[0], cumulative_amount=100)], properties=['A_B_A'])
    k = add(4, 'A_after_B', [a], av, properties=['A_B_A', 'return_mutation_independence'])
    link(4, 'A_B_A', i, k, 'A_B_A')
    tasks['Q-CP-04']['operations'].append(dict(mutate_previous=dict(index=i, path=['result', 0, 'amount'], value=999)))
    add(4, 'A_after_mutation', [a], av, properties=['return_mutation_independence'])
    add(4, 'empty_after_calls', [[]], [], properties=['empty', 'same_process_twice'])
    add(4, 'duplicate_event_ids', [[dict(event_id='D', amount=.5), dict(event_id='D', amount=-2)]],
        [dict(event_id='D', amount=.5, cumulative_amount=.5), dict(event_id='D', amount=-2, cumulative_amount=-1.5)],
        properties=['input_preserved'])
    add(4, 'fresh_input', [a], [dict(av[0], amount=999), av[1]], properties=['input_preserved'],
        mutate=dict(path=[0, 'amount'], value=999))
    invalid(4, 'tuple', [{'$tuple': a}], 'invalid_events')
    for event in (1, {}, {'event_id': 'X'}, dict(event_id='X', amount=1, extra=0),
                  dict(event_id='', amount=1), dict(event_id=1, amount=1)):
        invalid(4, 'event-'+str(event), [[event]], 'invalid_events')
    for value in (True, '1', None, {'$float': 'nan'}, {'$float': 'inf'}, {'$float': '-inf'}):
        invalid(4, 'amount-'+str(value), [[dict(event_id='X', amount=value)]], 'invalid_events')

    for task_id, task in tasks.items():
        task['property_names'] = contracts['tasks'][task_id]['properties']
        retained = []
        index = 0
        for op in task['operations']:
            if 'mutate_previous' in op:
                change = op['mutate_previous']
                obj = retained[change['index']]
                for key in change['path'][:-1]:
                    obj = obj[key]
                obj[change['path'][-1]] = change['value']
            else:
                retained.append(copy.deepcopy(task['cases'][index]['expected']))
                index += 1
        task['expected_retained'] = retained
    return tasks


def candidates():
    reference = (ROOT / 'src/quant_rsi/harness/supplement_cp.py').read_text(encoding='utf-8')
    changed = {
        'Q-CP-01': [
            ('silent-conflict', "_normalize = normalize_rows\ndef normalize_rows(rows):\n    if type(rows) is not list: raise ValueError('LIST_REQUIRED')\n    keyed = {}\n    for row in rows:\n        _normalize([row])\n        keyed[(row['security'],row['date'])] = copy.deepcopy(row)\n    return [keyed[k] for k in sorted(keyed)]\n"),
            ('input-alias', "_normalize = normalize_rows\ndef normalize_rows(rows):\n    _normalize(rows)\n    return [next(r for r in rows if (r['security'],r['date']) == k) for k in sorted({(r['security'],r['date']) for r in rows})]\n")],
        'Q-CP-02': [
            ('current-lookahead', "_mean = lagged_mean\ndef lagged_mean(values, window):\n    out = _mean(values,window)\n    return [None if t<window else sum(values[t-window+1:t+1])/window for t in range(len(values))]\n"),
            ('mutates-input', "_mean = lagged_mean\ndef lagged_mean(values, window):\n    out = _mean(values,window)\n    values.reverse()\n    return out\n")],
        'Q-CP-03': [
            ('wrong-cost', "_pnl = interval_pnl\ndef interval_pnl(returns,signals,cost_rate):\n    out = _pnl(returns,signals,cost_rate)\n    out['pnl'] = [q*r-cost_rate*abs(q) for q,r in zip(out['positions'],returns)]\n    out['pnl_sum'] = sum(out['pnl'])\n    return out\n"),
            ('compound-sum', "_pnl = interval_pnl\ndef interval_pnl(returns,signals,cost_rate):\n    out = _pnl(returns,signals,cost_rate)\n    wealth = 1\n    for p in out['pnl']: wealth *= 1+p\n    out['pnl_sum'] = wealth-1\n    return out\n")],
        'Q-CP-04': [
            ('mutable-default', "_ledger = build_ledger\ndef build_ledger(events, ledger=[]):\n    ledger.extend(_ledger(events))\n    return ledger\n"),
            ('shared-return', "_ledger = build_ledger\n_cache = {}\ndef build_ledger(events):\n    out = _ledger(events)\n    key = repr(events)\n    if key not in _cache: _cache[key] = out\n    return _cache[key]\n")],
    }
    equivalent = {
        'Q-CP-01': "_normalize = normalize_rows\ndef normalize_rows(rows):\n    out = _normalize(rows)\n    return [dict(price=r['price'], date=r['date'], security=r['security']) for r in out]\n",
        'Q-CP-02': "def lagged_mean(values,window):\n    values = sequence(values)\n    if type(window) is not int or window <= 0: raise ValueError('WINDOW')\n    out = [None]*len(values)\n    for t in range(window,len(values)): out[t] = math.fsum(values[t-window:t])/window\n    return out\n",
        'Q-CP-03': "_pnl = interval_pnl\ndef interval_pnl(returns,signals,cost_rate):\n    out = _pnl(returns,signals,cost_rate)\n    out['pnl_sum'] = math.fsum(out['pnl'])\n    return out\n",
        'Q-CP-04': "def build_ledger(events):\n    if type(events) is not list: raise ValueError('LIST')\n    amounts, out = [], []\n    for e in events:\n        if type(e) is not dict or set(e) != {'event_id','amount'}: raise ValueError('FIELDS')\n        if type(e['event_id']) is not str or not e['event_id']: raise ValueError('ID')\n        amounts.append(number(e['amount']))\n        out.append(dict(cumulative_amount=math.fsum(amounts),amount=e['amount'],event_id=e['event_id']))\n    return out\n",
    }
    for task_id in changed:
        yield task_id, 'reference', reference + DRIVER
        yield task_id, 'equivalent', reference + '\n' + equivalent[task_id] + DRIVER
        for label, patch in changed[task_id]:
            yield task_id, label, reference + '\n' + patch + DRIVER
