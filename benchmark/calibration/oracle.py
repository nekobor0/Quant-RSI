"""Independent public reference oracle; never imports fixture generator."""
from decimal import Decimal


def _ratio(end, start):
    return Decimal(end) / Decimal(start) - 1


def _six(value):
    return str(value.quantize(Decimal('0.000001')))


def _refuse(reason, layer):
    return {'terminal': 'REFUSE', 'reason': reason, 'evidence': {},
            'expected_rejection_layer': layer}


def _promote(evidence):
    return {'terminal': 'PROMOTE', 'reason': None, 'evidence': evidence,
            'expected_rejection_layer': None}


def reference(case_id, data):
    if case_id == 'CAL-T1-FIELD':
        if data['available_at'] > data['decision_at']:
            return _refuse('FUTURE_FIELD', 'PIT_DATA_BOUNDARY')
        return _promote({'observed_value': data['value']})
    if case_id == 'CAL-T1-REVISION':
        if data['revision_available_at'] > data['decision_at']:
            return _refuse('FUTURE_REVISION', 'PIT_DATA_BOUNDARY')
        return _promote({'observed_value': data['revised_value']})
    if case_id == 'CAL-T2-P10':
        if data['formation_observed_at'] > data['decision_month']:
            return _refuse('FUTURE_FORMATION', 'PIT_DATA_BOUNDARY')
        ids = data['eligible_ids']
        ordered = sorted(ids, key=lambda name: (
            _ratio(data['monthly_closes'][name][data['decision_month']],
                   data['monthly_closes'][name][0]), name))
        winner, loser = ordered[-1], ordered[0]
        winner_return = _ratio(data['monthly_closes'][winner][-1], data['next_open'][winner])
        benchmark = sum((_ratio(data['monthly_closes'][name][-1], data['next_open'][name])
                         for name in ids), Decimal(0)) / len(ids)
        return _promote({'winner_id': winner, 'loser_reference_id': loser,
                         'gross_return': _six(winner_return),
                         'benchmark_return': _six(benchmark),
                         'entry_lag_sessions': data['entry_lag_sessions']})
    if case_id == 'CAL-T2-P20':
        if data['signal_observed_at'] > data['decision_month']:
            return _refuse('FUTURE_SIGNAL', 'PIT_DATA_BOUNDARY')
        names = sorted(data['monthly_closes'])
        long_ids = [name for name in names if _ratio(
            data['monthly_closes'][name][data['decision_month']],
            data['monthly_closes'][name][0]) > 0]
        portfolio = sum((_ratio(data['exit_close'][name], data['next_open'][name])
                         for name in long_ids), Decimal(0)) / len(names)
        benchmark = sum((_ratio(data['exit_close'][name], data['next_open'][name])
                         for name in names), Decimal(0)) / len(names)
        return _promote({'long_ids': long_ids,
                         'cash_ids': [name for name in names if name not in long_ids],
                         'gross_return': _six(portfolio),
                         'benchmark_return': _six(benchmark),
                         'entry_lag_sessions': data['entry_lag_sessions']})
    if case_id in ('CAL-T3-NULL-A', 'CAL-T3-NULL-B'):
        xs, ys = data['features'], data['labels']
        supported = len(set(ys)) > 1 and any(
            all(int(x >= threshold) == y for x, y in zip(xs, ys))
            for threshold in set(xs))
        return _promote({'signal_feature': 'f0'}) if supported else _refuse(
            'NO_SUPPORTED_SIGNAL', 'EVALUATOR_GATE')
    if case_id == 'CAL-T3-COST':
        net = Decimal(data['gross_pnl']) - Decimal(data['roundtrip_cost'])
        return _promote({'net_pnl': str(net)}) if net > 0 else _refuse(
            'NET_NONPOSITIVE', 'EXECUTION_BOUNDARY')
    if case_id == 'CAL-T3-DECAY':
        early = sum(map(Decimal, data['early_effect'])) / len(data['early_effect'])
        late = sum(map(Decimal, data['late_effect'])) / len(data['late_effect'])
        threshold = Decimal(data['retirement_threshold'])
        return _refuse('RETIRE_DECAY', 'EVALUATOR_GATE') if early >= threshold and late < threshold else _promote(
            {'decision': 'KEEP'})
    if case_id == 'CAL-T3-EXECUTION':
        fills = []
        for order in data['orders']:
            eligible = not order['suspended'] and not order['limit_locked']
            if order['side'] == 'sell':
                eligible = eligible and order['acquired_session'] < data['execution_session']
            if eligible:
                fills.append(order['id'])
        return _promote({'filled_order_ids': sorted(fills)}) if fills else _refuse(
            'UNTRADEABLE_ALL', 'EXECUTION_BOUNDARY')
    raise ValueError(f'unknown public calibration case: {case_id}')


def adjudicate(case_id, data, output):
    """Assigned denominator is one even for malformed, missing or timeout output."""
    expected = reference(case_id, data)
    required = {'terminal', 'reason', 'evidence', 'expected_rejection_layer'}
    if not isinstance(output, dict) or set(output) != required or not isinstance(output.get('evidence'), dict):
        return {'assigned_denominator': 1, 'terminal_correct': False,
                'evidence_correct': False, 'full_pass': False,
                'failure_type': 'MISSING_OR_INVALID', 'expected': expected}
    terminal = output.get('terminal')
    terminal_ok = terminal == expected['terminal']
    evidence_ok = (output.get('evidence') == expected['evidence']
                   if expected['terminal'] == 'PROMOTE'
                   else output.get('reason') == expected['reason'])
    layer_ok = output['expected_rejection_layer'] == expected['expected_rejection_layer']
    shape_ok = ((terminal == 'REFUSE' and output['evidence'] == {})
                or (terminal == 'PROMOTE' and output['reason'] is None))
    full = bool(terminal_ok and evidence_ok and layer_ok and shape_ok)
    return {'assigned_denominator': 1, 'terminal_correct': terminal_ok,
            'evidence_correct': evidence_ok, 'full_pass': full,
            'failure_type': None if full else 'WRONG_OR_INCOMPLETE_OUTPUT',
            'expected': expected}
