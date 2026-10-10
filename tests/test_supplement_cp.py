"""Local tests of trusted references; these are NOT CP sandbox acceptance."""
import copy

import pytest

from quant_rsi.harness.supplement_cp import normalize_rows, lagged_mean, interval_pnl, build_ledger, contracts


def test_normalize_rows_properties():
    a = dict(security='A', date='D1', price=1)
    b = dict(security='B', date='D2', price=2)
    rows = [b, a, a]
    original = copy.deepcopy(rows)
    assert normalize_rows(rows) == normalize_rows(list(reversed(rows))) == [a, b]
    assert rows == original
    result = normalize_rows(rows)
    result[0]['price'] = 999
    assert normalize_rows(rows) == [a, b]
    assert normalize_rows([]) == []
    with pytest.raises(ValueError, match='CONFLICTING_PRICE'):
        normalize_rows([a, {**a, 'price': 2}])


@pytest.mark.parametrize('row', [{}, dict(security='', date='D', price=1),
    dict(security='A', date='D', price=True), dict(security='A', date='D', price=0),
    dict(security='A', date='D', price=float('nan')), dict(security='A', date='D', price=float('inf')),
    dict(security='A', date='D', price=1, extra=0)])
def test_invalid_normalization(row):
    with pytest.raises(ValueError):
        normalize_rows([row])


def test_lagged_mean_metamorphic():
    values = [10, 12, 14, 16]
    assert lagged_mean(values, 2) == [None, None, 11, 13]
    assert lagged_mean([10, 12, 999, 777], 2)[:3] == [None, None, 11]
    assert lagged_mean([], 1) == []
    assert lagged_mean([1, 3, 5], 1) == [None, 1, 3]
    assert values == [10, 12, 14, 16]


@pytest.mark.parametrize('values,window', [([True], 1), ([float('nan')], 1), ([None], 1),
    ([1], True), ([1], 0), ([1], -1), ([1], 1.2), ('bad', 1)])
def test_invalid_lag(values, window):
    with pytest.raises(ValueError):
        lagged_mean(values, window)


def test_pnl_lag_and_cost():
    result = interval_pnl([0, .1, -.1, .05], [1, 1, 0, -1], .01)
    assert result['positions'] == [0, 1, 1, 0]
    assert result['turnover'] == [0, 1, 0, 1]
    assert result['pnl'] == pytest.approx([0, .09, -.1, -.01], abs=1e-8)
    assert result['pnl_sum'] == pytest.approx(-.02, abs=1e-8)
    assert interval_pnl([], [], 0)['pnl'] == []
    assert interval_pnl([.1, .1], [-1, 1], .01)['pnl_sum'] == pytest.approx(-.11)
    assert interval_pnl([.1]*4, [0]*4, .01)['pnl_sum'] == 0


@pytest.mark.parametrize('r,s,c', [([1], [], 0), ([True], [1], 0), ([1], [float('inf')], 0),
    ([1], [1], -1), ([1], [1], True), ([1], [1], float('nan'))])
def test_invalid_pnl(r, s, c):
    with pytest.raises(ValueError):
        interval_pnl(r, s, c)


def test_ledger_same_process_state():
    a = [dict(event_id='E1', amount=2), dict(event_id='E2', amount=-1), dict(event_id='E3', amount=3)]
    b = [dict(event_id='B1', amount=100)]
    original = copy.deepcopy(a)
    expected = [dict(event_id='E1', amount=2, cumulative_amount=2),
                dict(event_id='E2', amount=-1, cumulative_amount=1),
                dict(event_id='E3', amount=3, cumulative_amount=4)]
    result = build_ledger(a)
    assert result == build_ledger(a) == expected
    assert len(build_ledger(b)) == 1
    assert build_ledger(a) == expected
    result[0]['amount'] = 999
    assert build_ledger(a) == expected
    assert a == original
    assert build_ledger([]) == []


def test_controlled_wrong_implementations():
    # Trusted author-written negative controls; no exec/eval or submission loading.
    assert [10, 12, 14, 16] != lagged_mean([10, 12, 14, 16], 1)
    assert [.1, -.1] != interval_pnl([.1, -.1], [1, 0], 0)['pnl']
    shared = []
    def broken(events):
        shared.extend(copy.deepcopy(events))
        return shared
    events = [dict(event_id='E', amount=1)]
    assert len(broken(events)) == 1
    assert len(broken(events)) == 2
    assert len(build_ledger(events)) == 1
    conflicting = [dict(security='A', date='D1', price=1), dict(security='A', date='D1', price=2)]
    # A drop-last deduplicator silently accepts conflict; the reference must reject it.
    wrong_cleaned = [conflicting[-1]]
    assert len(wrong_cleaned) == 1
    with pytest.raises(ValueError):
        normalize_rows(conflicting)
    assert contracts()['model_code_executions'] == 0


@pytest.mark.parametrize('events', [[{}], [dict(event_id='', amount=1)],
    [dict(event_id='E', amount=True)], [dict(event_id='E', amount=float('nan'))],
    [dict(event_id='E', amount=1, extra=0)], 'bad'])
def test_invalid_ledger(events):
    with pytest.raises(ValueError):
        build_ledger(events)


def test_pnl_future_signal_invariance():
    returns = [.01, -.02, .03, -.04]
    a = interval_pnl(returns, [1, -1, 1, 0], .01)
    b = interval_pnl(returns, [1, -1, 1, 999], .01)
    assert a == b
