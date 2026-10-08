import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'data'))
from test_pit import record, view
from quant_rsi.env.daily import simulate


def fixture(*, sessions=4, action=None):
    rows = [record()]
    rows += [record(kind=k, value=v) for k, v in
             [('ST', False), ('board', 'MAIN'), ('venue', 'X'), ('suspended', False),
              ('lagged_ADV', '100000')]]
    if action:
        rows.append(record(kind='corporate_action', value=action, source='action',
                           effective='2000-01-06T09:30:00Z'))
    pit, task = view(rows)
    dates = [f'2000-01-0{i}T09:30:00+00:00' for i in range(3, 3 + sessions)]
    frozen = dict(env_version=task.env_version, market_rules_version=task.market_rules_version,
                  calendar_version=task.calendar_version, cost_model_version=task.cost_model_version,
                  execution_timing=task.execution_timing, synthetic=True, uncertain_policy='BLOCK',
                  sessions=dates, initial_cash='100000',
                  calendar_timezone='UTC', split_order_policy='ADJUST_RESIDUAL_UNITS',
                  capacity=dict(target_capital='100000', participation_cap='0.02', impact_stress='1'),
                  costs=dict(commission='0.001', tax='0.002', spread='0.001',
                             slippage='0.001', impact='0.001'),
                  rules=[dict(**{'from': '2000-01-01T00:00:00Z', 'to': None}, board='MAIN',
                              venue='X', st=False, listing=True, lot_size=100, tick_size='0.01',
                              t_plus_sessions=1, price_limit_pct='0.1')],
                  bars={s: {'AAA': dict(open='10', previous_close='10', mark='10',
                                          certified_open_volume=10000)} for s in dates},
                  orders=[])
    return pit, task, frozen


def order(day, side, quantity):
    return dict(entity='AAA', side=side, quantity=quantity,
                decision_at=f'2000-01-0{day}T16:00:00Z',
                signal_at=f'2000-01-0{day}T16:01:00Z',
                order_created_at=f'2000-01-0{day}T16:02:00Z')


def assert_conserved(result):
    json.dumps(result, sort_keys=True)
    for entry in result['ledger']:
        assert Decimal(entry['cash']) >= 0
        assert all(q >= 0 for q in entry['positions'].values())
        assert Decimal(entry['cash']) + Decimal(entry['positions_value']) == Decimal(entry['nav'])
    for fill in result['fills']:
        bridge = fill['cost_bridge']
        assert Decimal(bridge['net']) == Decimal(bridge['gross']) - sum(
            (Decimal(bridge[k]) for k in ('commission', 'tax', 'spread', 'slippage', 'impact')),
            Decimal(0))


def test_buy_sell_rebalance_timing_cost_and_nav():
    pit, task, frozen = fixture()
    frozen['orders'] = [order(3, 'buy', 100), order(4, 'sell', 100), order(5, 'buy', 100)]
    result = simulate(task, pit, frozen)
    assert [f['fill_at'] for f in result['fills']] == frozen['sessions'][1:]
    assert [f['side'] for f in result['fills']] == ['buy', 'sell', 'buy']
    assert result['decisions'][0]['decision_at'] < result['decisions'][0]['signal_at']
    assert result['decisions'][0]['signal_at'] < result['decisions'][0]['order_created_at']
    assert result['decisions'][0]['first_executable_at'] == frozen['sessions'][1]
    assert result['ledger'][-1]['positions']['AAA'] == 100
    assert Decimal(result['ledger'][-1]['nav']) == Decimal('100000') - sum(
        (sum((Decimal(v) for k, v in f['cost_bridge'].items() if k not in ('gross', 'net')),
             Decimal(0)) for f in result['fills']), Decimal(0))
    assert_conserved(result)
    assert result == simulate(task, pit, frozen)


def test_partial_capacity_and_unfilled_quantity():
    pit, task, frozen = fixture(sessions=3)
    frozen['capacity']['participation_cap'] = '0.01'  # 1000 currency = 100 shares/session
    frozen['orders'] = [order(3, 'buy', 300)]
    result = simulate(task, pit, frozen)
    assert [f['quantity'] for f in result['fills']] == [100, 100]
    assert result['remaining'] == [100]
    assert result['turnover'] == '0.02'
    assert_conserved(result)


def test_no_certification_uncertain_and_zero_volume_no_fill():
    pit, task, frozen = fixture(sessions=2)
    frozen['orders'] = [order(3, 'buy', 100)]
    del frozen['bars'][frozen['sessions'][1]]['AAA']['certified_open_volume']
    result = simulate(task, pit, frozen)
    assert result['decisions'][0]['status'] == 'UNCERTAIN'
    assert result['fills'] == [] and result['ledger'][-1]['nav'] == '100000'
    frozen['bars'][frozen['sessions'][1]]['AAA']['certified_open_volume'] = 0
    assert simulate(task, pit, frozen)['decisions'][0]['status'] == 'NOT_EXECUTABLE'


def test_t_plus_one_and_suspension_and_limit_queue():
    pit, task, frozen = fixture(sessions=3)
    frozen['orders'] = [order(3, 'buy', 100), order(3, 'sell', 100)]
    result = simulate(task, pit, frozen)
    assert result['decisions'][1]['status'] == 'NOT_EXECUTABLE'
    assert result['fills'][-1]['fill_at'] == frozen['sessions'][2]
    rows = [record()] + [record(kind=k, value=v) for k, v in
             [('ST', False), ('board', 'MAIN'), ('venue', 'X'), ('lagged_ADV', '100000')]]
    rows += [record(kind='suspended', value=True)]
    suspended, task2 = view(rows)
    assert simulate(task2, suspended, frozen)['decisions'][0]['status'] == 'NOT_EXECUTABLE'
    frozen['bars'][frozen['sessions'][1]]['AAA']['open'] = '11'
    assert simulate(task, pit, frozen)['decisions'][0]['status'] == 'UNCERTAIN'


@pytest.mark.parametrize('change', [
    lambda f: f.update(cost_model_version='wrong'),
    lambda f: f.update(uncertain_policy='FILL'),
    lambda f: f['rules'].clear(),
])
def test_frozen_versions_policy_and_unknown_rules_block(change):
    pit, task, frozen = fixture(sessions=2)
    frozen['orders'] = [order(3, 'buy', 100)]
    change(frozen)
    with pytest.raises(ValueError):
        simulate(task, pit, frozen)


def test_pit_future_st_and_listing_state_block():
    pit, task, frozen = fixture(sessions=2)
    frozen['orders'] = [order(3, 'buy', 100)]
    rows = [record()] + [record(kind=k, value=v) for k, v in
             [('ST', False), ('board', 'MAIN'), ('venue', 'X'), ('suspended', False),
              ('lagged_ADV', '100000')]]
    rows.append(record(kind='ST', value=True, revision='r2', available='2000-01-04T09:00:00Z'))
    changed, task2 = view(rows)
    assert pit.state('2000-01-03T16:00:00Z', 'AAA', 'ST') is False
    with pytest.raises(ValueError, match='rule'):
        simulate(task2, changed, frozen)


def test_split_and_dividend_preserve_nav():
    for action in (dict(type='split', ratio=2), dict(type='dividend', per_share='1')):
        pit, task, frozen = fixture(action=action)
        frozen['costs'] = dict.fromkeys(frozen['costs'], '0')
        frozen['orders'] = [order(3, 'buy', 100)]
        if action['type'] == 'split':
            frozen['bars'][frozen['sessions'][3]]['AAA'].update(open='5', previous_close='5', mark='5')
        else:
            frozen['bars'][frozen['sessions'][3]]['AAA'].update(open='9', previous_close='9', mark='9')
        result = simulate(task, pit, frozen)
        assert Decimal(result['ledger'][-1]['nav']) == Decimal('100000')
        assert result['ledger'][-1]['positions']['AAA'] == (200 if action['type'] == 'split' else 100)
        assert_conserved(result)


def test_lagged_adv_must_precede_decision():
    rows = [record()] + [record(kind=k, value=v) for k, v in
             [('ST', False), ('board', 'MAIN'), ('venue', 'X'), ('suspended', False)]]
    rows.append(record(kind='lagged_ADV', value='100000', event='2000-01-04T00:00:00Z'))
    pit, task = view(rows)
    _, _, frozen = fixture(sessions=2)
    frozen['orders'] = [order(3, 'buy', 100)]
    with pytest.raises(ValueError, match='ADV'):
        simulate(task, pit, frozen)


def test_mark_without_order_and_shared_session_volume():
    pit, task, frozen = fixture(sessions=3)
    frozen['costs'] = dict.fromkeys(frozen['costs'], '0')
    frozen['orders'] = [order(3, 'buy', 100)]
    frozen['bars'][frozen['sessions'][2]]['AAA']['mark'] = '11'
    result = simulate(task, pit, frozen)
    assert Decimal(result['ledger'][-1]['nav']) == Decimal('100100')
    assert_conserved(result)

    frozen['orders'] = [order(3, 'buy', 100), order(3, 'buy', 100)]
    frozen['capacity']['participation_cap'] = '0.01'
    frozen['bars'][frozen['sessions'][1]]['AAA']['certified_open_volume'] = 100
    result = simulate(task, pit, frozen)
    assert [d['filled_quantity'] for d in result['decisions'][:2]] == [100, 0]
    assert_conserved(result)


def test_critic_02_unknown_suspension_blocks():
    rows=[record()]+[record(kind=k,value=v) for k,v in [('ST',False),('board','MAIN'),('venue','X'),('suspended',None),('lagged_ADV','100000')]]
    pit,task=view(rows);_,_,frozen=fixture(sessions=2);frozen['orders']=[order(3,'buy',100)]
    with pytest.raises(ValueError,match='suspension'):simulate(task,pit,frozen)


@pytest.mark.parametrize('field',['quantity','lot_size','t_plus_sessions','certified_open_volume','split_ratio'])
@pytest.mark.parametrize('value',[100.9,True])
def test_critic_03_execution_counts_are_exact_integers(field,value):
    pit,task,frozen=fixture(action={'type':'split','ratio':value} if field=='split_ratio' else None)
    frozen['orders']=[order(3,'buy',100)]
    if field=='quantity':frozen['orders'][0][field]=value
    elif field in ('lot_size','t_plus_sessions'):frozen['rules'][0][field]=value
    elif field=='certified_open_volume':frozen['bars'][frozen['sessions'][1]]['AAA'][field]=value
    with pytest.raises(ValueError,match='exact non-bool integer'):simulate(task,pit,frozen)


def test_critic_04_multiple_opens_same_trading_date_block():
    pit,task,frozen=fixture(sessions=3)
    bar=frozen['bars'][frozen['sessions'][1]]
    frozen['sessions']=['2000-01-03T09:30:00Z','2000-01-04T09:30:00Z','2000-01-04T13:00:00Z']
    frozen['bars']={'2000-01-04T09:30:00+00:00':bar,'2000-01-04T13:00:00+00:00':bar}
    frozen['orders']=[order(3,'buy',100),order(3,'sell',100)]
    with pytest.raises(ValueError,match='daily'):simulate(task,pit,frozen)


def test_critic_05_split_adjusts_residual_order_units():
    pit,task,frozen=fixture(action={'type':'split','ratio':2})
    frozen['costs']=dict.fromkeys(frozen['costs'],'0');frozen['capacity']['participation_cap']='0.01'
    frozen['orders']=[order(3,'buy',300)]
    frozen['bars'][frozen['sessions'][3]]['AAA'].update(open='5',previous_close='5',mark='5')
    result=simulate(task,pit,frozen)
    assert result['ledger'][-1]['positions']['AAA']==600
    assert result['fills'][-1]['quantity']==200 and result['remaining']==[0]


def test_critic_06_unfunded_sale_costs_block():
    pit,task,frozen=fixture(sessions=3)
    frozen['initial_cash']=frozen['capacity']['target_capital']='3000'
    frozen['capacity']['participation_cap']='1';frozen['costs']=dict.fromkeys(frozen['costs'],'0');frozen['costs']['commission']='2'
    frozen['orders']=[order(3,'buy',100),order(4,'sell',100)]
    frozen['bars'][frozen['sessions'][2]]['AAA'].update(open='100',previous_close='100',mark='100')
    with pytest.raises(ValueError,match='proceeds|cash'):simulate(task,pit,frozen)


@pytest.mark.parametrize('value', [Decimal('100.9'), float('nan'), float('inf'), Decimal('NaN'), Decimal('Infinity'), -1])
@pytest.mark.parametrize('field', ['quantity', 'lot_size', 't_plus_sessions', 'certified_open_volume'])
def test_override_invalid_integral_inputs(field, value):
    test_critic_03_execution_counts_are_exact_integers(field, value)


@pytest.mark.parametrize('value,error,reason', [
    (Decimal('100.9'), TypeError, 'not JSON serializable'),
    (float('nan'), ValueError, 'Out of range float values'),
    (float('inf'), ValueError, 'Out of range float values'),
    (Decimal('NaN'), TypeError, 'not JSON serializable'),
    (Decimal('Infinity'), TypeError, 'not JSON serializable'),
])
def test_split_noncanonical_payload_rejected_at_pit_boundary(value, error, reason):
    # No simulator call: canonical PIT construction must reject this payload.
    with pytest.raises(error, match=reason):
        fixture(action={'type':'split','ratio':value})


def test_split_negative_json_integer_rejected_by_execution():
    # Construction is outside raises: -1 must reach the execution validator.
    test_critic_03_execution_counts_are_exact_integers('split_ratio', -1)


@pytest.mark.parametrize('value', [0, 1, 'False', [], {}])
def test_override_unknown_suspension_types(value):
    rows = [record()] + [record(kind=k, value=v) for k,v in
        [('ST',False),('board','MAIN'),('venue','X'),('suspended',value),('lagged_ADV','100000')]]
    pit,task = view(rows); _,_,frozen = fixture(sessions=2)
    frozen['orders'] = [order(3,'buy',100)]
    with pytest.raises(ValueError, match='suspension'):
        simulate(task,pit,frozen)


def test_override_missing_suspension_blocks():
    rows = [record()] + [record(kind=k, value=v) for k,v in
        [('ST',False),('board','MAIN'),('venue','X'),('lagged_ADV','100000')]]
    pit,task = view(rows); _,_,frozen = fixture(sessions=2)
    frozen['orders'] = [order(3,'buy',100)]
    with pytest.raises(ValueError, match='PIT state'):
        simulate(task,pit,frozen)


def test_override_partial_sell_split_inventory_and_completion():
    pit,task,frozen = fixture(action={'type':'split','ratio':2})
    frozen['costs'] = dict.fromkeys(frozen['costs'],'0')
    frozen['capacity']['participation_cap'] = '1'
    frozen['orders'] = [order(3,'buy',300),order(4,'sell',300)]
    frozen['bars'][frozen['sessions'][2]]['AAA']['certified_open_volume'] = 100
    frozen['bars'][frozen['sessions'][3]]['AAA'].update(open='5',previous_close='5',mark='5',certified_open_volume=400)
    result = simulate(task,pit,frozen)
    assert [f['quantity'] for f in result['fills']] == [300,100,400]
    assert result['ledger'][-1]['positions']['AAA'] == 0
    assert result['remaining'] == [0,0]
    assert Decimal(result['ledger'][-1]['cash']) == Decimal('100000')
    assert_conserved(result)


def test_override_split_residual_lot_misalignment_blocks():
    pit,task,frozen = fixture(action={'type':'split','ratio':2})
    frozen['capacity']['participation_cap'] = '0.01'
    frozen['orders'] = [order(3,'buy',300)]
    old = frozen['rules'][0]
    changed = dict(old, lot_size=300)
    changed['from'] = old['to'] = '2000-01-06T09:30:00Z'
    frozen['rules'].append(changed)
    with pytest.raises(ValueError,match='split residual'):
        simulate(task,pit,frozen)


def test_override_t_plus_dates_and_explicit_policies():
    pit,task,frozen = fixture(sessions=4)
    frozen['rules'][0]['t_plus_sessions'] = 2
    frozen['orders'] = [order(3,'buy',100),order(3,'sell',100)]
    result = simulate(task,pit,frozen)
    assert [f['fill_at'] for f in result['fills']] == [frozen['sessions'][1],frozen['sessions'][3]]
    assert_conserved(result)
    for field in ('calendar_timezone','split_order_policy'):
        changed = dict(frozen); changed.pop(field)
        with pytest.raises(ValueError): simulate(task,pit,changed)
