"""Independent public adjudication using input values and fraction ledgers.

No fixture variant name selects a verdict. This implementation imports neither
the generator nor the primary oracle. Its JSON output is a frozen cross-check.
"""
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'benchmark/calibration/INDEPENDENT_EXPECTED_V0_1.json'


def refuse(reason, layer):
    return dict(terminal='REFUSE', reason=reason, evidence={}, expected_rejection_layer=layer)


def promote(evidence):
    return dict(terminal='PROMOTE', reason=None, evidence=evidence, expected_rejection_layer=None)


def six(value):
    return str((Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal('0.000001')))


def compute(case_id, data):
    if case_id == 'CAL-T1-FIELD':
        return (refuse('FUTURE_FIELD', 'PIT_DATA_BOUNDARY')
                if data['available_at'] > data['decision_at']
                else promote({'observed_value': data['value']}))
    if case_id == 'CAL-T1-REVISION':
        return (refuse('FUTURE_REVISION', 'PIT_DATA_BOUNDARY')
                if data['revision_available_at'] > data['decision_at']
                else promote({'observed_value': data['revised_value']}))
    if case_id == 'CAL-T2-P10':
        if data['formation_observed_at'] > data['decision_month']:
            return refuse('FUTURE_FORMATION', 'PIT_DATA_BOUNDARY')
        names = data['eligible_ids']
        ranks = sorted(names, key=lambda name: (
            Fraction(data['monthly_closes'][name][data['decision_month']],
                     data['monthly_closes'][name][0]) - 1, name))
        pnl = {name: Fraction(data['monthly_closes'][name][-1] - data['next_open'][name],
                              data['next_open'][name]) for name in names}
        return promote({'winner_id': ranks[-1], 'loser_reference_id': ranks[0],
                        'gross_return': six(pnl[ranks[-1]]),
                        'benchmark_return': six(sum(pnl.values(), Fraction()) / len(names)),
                        'entry_lag_sessions': data['entry_lag_sessions']})
    if case_id == 'CAL-T2-P20':
        if data['signal_observed_at'] > data['decision_month']:
            return refuse('FUTURE_SIGNAL', 'PIT_DATA_BOUNDARY')
        names = sorted(data['monthly_closes'])
        chosen = [name for name in names if data['monthly_closes'][name][data['decision_month']] >
                  data['monthly_closes'][name][0]]
        pnl = {name: Fraction(data['exit_close'][name] - data['next_open'][name],
                              data['next_open'][name]) for name in names}
        return promote({'long_ids': chosen, 'cash_ids': [name for name in names if name not in chosen],
                        'gross_return': six(sum((pnl[name] for name in chosen), Fraction()) / len(names)),
                        'benchmark_return': six(sum(pnl.values(), Fraction()) / len(names)),
                        'entry_lag_sessions': data['entry_lag_sessions']})
    if case_id in ('CAL-T3-NULL-A', 'CAL-T3-NULL-B'):
        pairs = sorted(zip(data['features'], data['labels']))
        labels = {label for _, label in pairs}
        if labels == {0, 1}:
            first_positive = min(x for x, label in pairs if label == 1)
            if all(x < first_positive for x, label in pairs if label == 0):
                return promote({'signal_feature': 'f0'})
        return refuse('NO_SUPPORTED_SIGNAL', 'EVALUATOR_GATE')
    if case_id == 'CAL-T3-COST':
        net = Decimal(data['gross_pnl']) - Decimal(data['roundtrip_cost'])
        return promote({'net_pnl': str(net)}) if net > 0 else refuse('NET_NONPOSITIVE', 'EXECUTION_BOUNDARY')
    if case_id == 'CAL-T3-DECAY':
        early = sum(Decimal(x) for x in data['early_effect']) / len(data['early_effect'])
        late = sum(Decimal(x) for x in data['late_effect']) / len(data['late_effect'])
        cutoff = Decimal(data['retirement_threshold'])
        return (refuse('RETIRE_DECAY', 'EVALUATOR_GATE') if early >= cutoff and late < cutoff
                else promote({'decision': 'KEEP'}))
    if case_id == 'CAL-T3-EXECUTION':
        filled = []
        for order in data['orders']:
            if order['suspended'] or order['limit_locked']:
                continue
            if order['side'] == 'sell' and order['acquired_session'] >= data['execution_session']:
                continue
            filled.append(order['id'])
        return (promote({'filled_order_ids': sorted(filled)}) if filled
                else refuse('UNTRADEABLE_ALL', 'EXECUTION_BOUNDARY'))
    raise ValueError(case_id)


def calculate():
    result = {}
    for path in sorted((ROOT / 'benchmark/calibration/fixtures').glob('CAL-*.json')):
        variants = json.loads(path.read_text(encoding='utf-8'))['variants']
        result[path.stem] = {name: compute(path.stem, data) for name, data in variants.items()}
    return result


if __name__ == '__main__':
    expected = calculate()
    OUT.write_text(json.dumps(expected, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(f'independently_frozen_variants={sum(map(len, expected.values()))}')
