"""Create nine public synthetic fixtures; contains no oracle or expected outcomes."""
from pathlib import Path
import json
import random

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'benchmark/calibration/fixtures'


def fixtures():
    def null_panel(seed, mechanism):
        n = 24
        features = random.Random(seed).sample(range(1000), n)
        if mechanism == 'independent_alternating_labels':
            labels = [i % 2 for i in range(n)]
            random.Random(seed + 1000).shuffle(labels)
        else:
            blocks = [[j % 2] * 3 for j in range(n // 3)]
            random.Random(seed + 1000).shuffle(blocks)
            labels = [value for block in blocks for value in block]
        return {'seed': seed, 'mechanism': mechanism, 'features': features, 'labels': labels}

    field = {'decision_at': 10, 'available_at': 11, 'value': 7}
    revision = {'decision_at': 10, 'revision_available_at': 11,
                'prior_value': 7, 'revised_value': 7}
    p10_prices = {f'S{i:02d}': [100, 100 + i, 100 + 2*i, 100 + 3*i,
                                  102 + 3*i, 104 + 3*i, 106 + 3*i]
                  for i in range(10)}
    p10 = {'decision_month': 3, 'formation_observed_at': 3,
           'eligible_ids': list(p10_prices), 'monthly_closes': p10_prices,
           'next_open': {name: prices[3] + 1 for name, prices in p10_prices.items()},
           'entry_lag_sessions': 1}
    p20 = {'decision_month': 12, 'signal_observed_at': 12,
           'monthly_closes': {'A': list(range(100, 113)),
                              'B': list(range(100, 87, -1))},
           'next_open': {'A': 113, 'B': 89},
           'exit_close': {'A': 118, 'B': 94},
           'entry_lag_sessions': 1}
    null_a = null_panel(17, 'independent_alternating_labels')
    null_b = null_panel(29, 'independent_three_observation_blocks')
    cost = {'gross_pnl': '12', 'roundtrip_cost': '15', 'target_capital': '100'}
    decay = {'early_effect': ['0.08']*4, 'late_effect': ['0.00']*4,
             'retirement_threshold': '0.02'}
    execution = {'decision_session': 10, 'execution_session': 11,
                 'orders': [
                     {'id': 'suspension', 'side': 'buy', 'suspended': True,
                      'limit_locked': False, 'acquired_session': None},
                     {'id': 'limit_lock', 'side': 'buy', 'suspended': False,
                      'limit_locked': True, 'acquired_session': None},
                     {'id': 't_plus_one', 'side': 'sell', 'suspended': False,
                      'limit_locked': False, 'acquired_session': 11},
                 ]}
    return {
        'CAL-T1-FIELD': {'base': field,
                         'positive': {**field, 'available_at': 9},
                         'transfer': {**field, 'available_at': 10}},
        'CAL-T1-REVISION': {'base': revision,
                            'positive': {**revision, 'revision_available_at': 9},
                            'transfer': {**revision, 'revision_available_at': 10}},
        'CAL-T2-P10': {'base': p10,
                       'positive': {**p10, 'eligible_ids': list(p10_prices)[:-1]},
                       'negative': {**p10, 'formation_observed_at': 4}},
        'CAL-T2-P20': {'base': p20,
                       'positive': {**p20, 'monthly_closes': {**p20['monthly_closes'],
                                   'B': list(range(100, 112)) + [102]}},
                       'negative': {**p20, 'signal_observed_at': 13}},
        'CAL-T3-NULL-A': {'base': null_a,
                          'positive': {**null_a, 'labels': [int(x >= 500) for x in null_a['features']]},
                          'transfer': null_panel(18, 'independent_alternating_labels')},
        'CAL-T3-NULL-B': {'base': null_b,
                          'positive': {**null_b, 'labels': [int(x >= 500) for x in null_b['features']]},
                          'transfer': null_panel(30, 'independent_three_observation_blocks')},
        'CAL-T3-COST': {'base': cost,
                        'positive': {**cost, 'roundtrip_cost': '8'},
                        'transfer': {**cost, 'roundtrip_cost': '12'}},
        'CAL-T3-DECAY': {'base': decay,
                         'positive': {**decay, 'late_effect': ['0.08']*4},
                         'transfer': {**decay, 'late_effect': ['0.01']*4}},
        'CAL-T3-EXECUTION': {'base': execution,
                             'positive_suspension': {**execution, 'orders': [
                                 {**execution['orders'][0], 'suspended': False}]},
                             'positive_limit': {**execution, 'orders': [
                                 {**execution['orders'][1], 'limit_locked': False}]},
                             'positive_t_plus_one': {**execution, 'execution_session': 12,
                                 'orders': [execution['orders'][2]]}},
    }


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    values = fixtures()
    for case_id, variants in values.items():
        (OUT / f'{case_id}.json').write_text(json.dumps(
            {'case_id': case_id, 'exposure': 'PUBLIC_CALIBRATION',
             'variants': variants}, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(f'public_calibration_cases={len(values)}')
