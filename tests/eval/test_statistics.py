"""Analytical/hand-enumerated W10A examples; synthetic data only."""
import math
import random

import pytest

from quant_rsi.eval.statistics import (
    block_bootstrap, dsr, pbo_cscv, psr, sharpe_moments, white_reality_check,
)


BLOCKS = ((0, 1), (2, 3))
UNIT_BLOCKS = ((0,), (1,))
ROWS = ((-2, 2), (0, 0), (2, -2), (4, -4))


def assert_failure(result, status, reason):
    assert result == {'status': status, 'reason': reason}


def test_sharpe_and_psr_hand_calculation():
    # [0,1,2]: mean=1, sample sd=1, m2=2/3, m4=2/3,
    # skew=0, kurt=3/2. Variance factor=9/8; z=sqrt(2)/sqrt(9/8)=4/3.
    moments = sharpe_moments([0, 1, 2])
    assert moments['status'] == 'ok'
    assert moments['sharpe'] == pytest.approx(1)
    assert moments['skewness'] == pytest.approx(0)
    assert moments['kurtosis'] == pytest.approx(1.5)
    result = psr([0, 1, 2], reference_sharpe=0, iid=True)
    assert result['variance_factor'] == pytest.approx(9 / 8)
    assert result['z'] == pytest.approx(4 / 3)
    # Independent tabulated standard-normal CDF, not a duplicate implementation.
    assert result['probability'] == pytest.approx(0.9087887802741321, abs=1e-14)
    assert psr([0, 1, 2], reference_sharpe=1, iid=True)['probability'] == pytest.approx(0.5, abs=1e-15, rel=0)


def test_psr_symmetry_and_positive_scale_invariance():
    positive = psr([0, 1, 2], reference_sharpe=0, iid=True)
    negative = psr([0, -1, -2], reference_sharpe=0, iid=True)
    assert positive['probability'] + negative['probability'] == pytest.approx(1)
    for scale in (1e-250, 1e250):
        scaled = psr([0, scale, 2 * scale], reference_sharpe=0, iid=True)
        assert scaled['probability'] == pytest.approx(positive['probability'])
    assert psr([-1e308, 0, 1e308], reference_sharpe=0, iid=True)['probability'] == 0.5


@pytest.mark.parametrize('values', [[], [1]])
def test_short_sharpe(values):
    assert_failure(sharpe_moments(values), 'unsupported', 'AT_LEAST_TWO_OBSERVATIONS')


@pytest.mark.parametrize('values', [[0, 0], [7, 7, 7]])
def test_constant_sharpe(values):
    assert_failure(psr(values, reference_sharpe=0, iid=True), 'unsupported', 'ZERO_VARIANCE')


def test_two_observations_are_algebraically_supported_not_sample_policy():
    assert psr([-1, 1], reference_sharpe=0, iid=True)['probability'] == 0.5


@pytest.mark.parametrize('iid', [False, None, 1, 'true'])
def test_psr_no_dependence_fallback(iid):
    assert_failure(psr([0, 1, 2], reference_sharpe=0, iid=iid),
                   'unsupported', 'IID_FINITE_FOURTH_MOMENT_REQUIRED')


def test_extreme_empirical_moments_have_closed_form_oracle():
    # Bernoulli empirical distribution p=1/100: skew=98/sqrt(99),
    # kurt=((99**3)+1)/(100*99). Mean-centering makes SR=0 exactly here.
    values = [-1] * 99 + [99]
    result = psr(values, reference_sharpe=0, iid=True)
    assert result['skewness'] == pytest.approx(98 / math.sqrt(99))
    assert result['kurtosis'] == pytest.approx((99 ** 3 + 1) / (100 * 99))
    assert result['probability'] == pytest.approx(0.5)


def test_numeric_range_does_not_report_probability():
    assert_failure(psr([-1, 0, 1] * 3, reference_sharpe=1e308, iid=True),
                   'unsupported', 'NUMERIC_RANGE')


def dsr_example(**overrides):
    arguments = dict(trial_sharpes=[-1, 1], n_trials=2, independent_trials=True,
                     complete_trials=True, iid=True)
    arguments.update(overrides)
    return dsr([0, 1, 2], **arguments)


def test_dsr_single_trial_is_zero_reference_psr():
    result = dsr_example(trial_sharpes=[1], n_trials=1)
    assert result['reference_sharpe'] == 0
    assert result['trial_sd'] is None
    assert result['probability'] == pytest.approx(0.9087887802741321)


def test_dsr_two_trial_approximation_oracle():
    result = dsr_example(trial_sharpes=[-1 / math.sqrt(2), 1 / math.sqrt(2)])
    # Sample spread=1. N=2 first quantile=0; second quantile about .90045.
    # gamma * .90045 = .51975 (normal table precision, NOT exact E[max]=1/sqrt(pi)).
    assert result['trial_sd'] == pytest.approx(1)
    assert result['reference_sharpe'] == pytest.approx(0.51975, abs=2e-5)
    assert 0.5 < result['probability'] < 0.9087887802741321


@pytest.mark.parametrize('flag', [False, None, 1])
def test_dsr_independence_must_be_explicit(flag):
    assert_failure(dsr_example(independent_trials=flag),
                   'unsupported', 'INDEPENDENT_GAUSSIAN_TRIALS_REQUIRED')


def test_dsr_completeness_missing_numeric_and_identical_trials():
    assert_failure(dsr_example(complete_trials=False), 'unsupported', 'COMPLETE_TRIAL_RESULTS_REQUIRED')
    assert_failure(dsr_example(n_trials=3), 'invalid', 'TRIAL_COUNT_MISMATCH')
    assert_failure(dsr_example(trial_sharpes=[None, 1]), 'invalid', 'FINITE_REAL_REQUIRED')
    assert_failure(dsr_example(trial_sharpes=[1, 1]), 'unsupported', 'ZERO_TRIAL_VARIANCE')
    assert_failure(dsr_example(iid=False), 'unsupported', 'IID_FINITE_FOURTH_MOMENT_REQUIRED')
    assert_failure(dsr_example(n_trials=True), 'invalid', 'INTEGER_OUT_OF_RANGE')


def test_dsr_trial_location_does_not_change_zero_null_reference():
    assert dsr_example(trial_sharpes=[9, 11])['reference_sharpe'] == pytest.approx(
        dsr_example()['reference_sharpe'])


def test_bootstrap_fixed_rng_exact_draws_no_global_state_or_mutation():
    blocks = [[0, 1], [2, 3]]
    state = random.getstate()
    result = block_bootstrap(4, blocks=blocks, resamples=5, seed=0)
    # Seed-0 block choices: BB, AB, BB, BB, BA. Blocks remain intact.
    expected = ((2, 3, 2, 3), (0, 1, 2, 3), (2, 3, 2, 3), (2, 3, 2, 3), (2, 3, 0, 1))
    assert result == {'status': 'ok', 'indices': expected}
    assert block_bootstrap(4, blocks=blocks, resamples=5, seed=0) == result
    assert random.getstate() == state
    assert blocks == [[0, 1], [2, 3]]


@pytest.mark.parametrize('blocks,reason', [
    ([], 'EMPTY_BLOCKS'), ([[]], 'EMPTY_BLOCKS'),
    ([[0], [1, 2, 3]], 'UNEQUAL_BLOCK_LENGTH'),
    ([[0, 1], [1, 2]], 'ORDERED_CONTIGUOUS_PARTITION_REQUIRED'),
    ([[2, 3], [0, 1]], 'ORDERED_CONTIGUOUS_PARTITION_REQUIRED'),
    ([[0, 2], [1, 3]], 'ORDERED_CONTIGUOUS_PARTITION_REQUIRED'),
    ([[0, 1]], 'ORDERED_CONTIGUOUS_PARTITION_REQUIRED'),
    ([[0, 1], [2, 4]], 'ORDERED_CONTIGUOUS_PARTITION_REQUIRED'),
    ([[False, 1], [2, 3]], 'ORDERED_CONTIGUOUS_PARTITION_REQUIRED'),
])
def test_invalid_blocks(blocks, reason):
    assert_failure(block_bootstrap(4, blocks=blocks, resamples=1, seed=0), 'invalid', reason)
    assert_failure(white_reality_check(ROWS, blocks=blocks, resamples=1, seed=0, stationary=True),
                   'invalid', reason)
    assert_failure(pbo_cscv(ROWS, blocks=blocks), 'invalid', reason)


def test_degenerate_block_and_invalid_rng_parameters():
    assert_failure(block_bootstrap(4, blocks=[range(4)], resamples=1, seed=0),
                   'invalid', 'LIST_OR_TUPLE_REQUIRED')
    assert_failure(block_bootstrap(4, blocks=[[0, 1, 2, 3]], resamples=1, seed=0),
                   'unsupported', 'AT_LEAST_TWO_BLOCKS')
    assert_failure(block_bootstrap(4, blocks=BLOCKS, resamples=0, seed=0), 'invalid', 'INTEGER_OUT_OF_RANGE')
    assert_failure(block_bootstrap(4, blocks=BLOCKS, resamples=1, seed=None), 'invalid', 'INTEGER_SEED_REQUIRED')
    assert_failure(block_bootstrap(4.0, blocks=BLOCKS, resamples=1, seed=0), 'invalid', 'INTEGER_OUT_OF_RANGE')


def test_white_rc_hand_enumerated_dependent_candidate_oracle():
    # Means=(1,-1), T=2. Centered block means are (-2,2), (2,-2).
    # Exhaustive ordered block draws AA,AB,BA,BB have max statistics 4,0,0,4.
    # The seed-0 Monte Carlo sample BB,AB,BB,BB,BA thus gives 3/5, not exact 1/2.
    result = white_reality_check(ROWS, blocks=BLOCKS, resamples=5, seed=0, stationary=True)
    assert result['statistic'] == 2
    assert result['bootstrap_statistics'] == (4, 0, 4, 4, 0)
    assert result['tail_count'] == 3
    assert result['tail_probability'] == 3 / 5
    assert white_reality_check(ROWS, blocks=BLOCKS, resamples=5, seed=0, stationary=True) == result
    duplicated = tuple(row + (row[0],) for row in ROWS)
    assert white_reality_check(duplicated, blocks=BLOCKS, resamples=5, seed=0, stationary=True) == result


def test_white_rc_ties_negative_statistics_and_monte_carlo_zero():
    def run(values):
        return white_reality_check([(value,) for value in values], blocks=BLOCKS,
                                   resamples=5, seed=0, stationary=True)
    ties = run([-3, -1, 1, 3])
    assert ties['statistic'] == 0
    assert ties['tail_count'] == 5  # Includes the two exact-zero ties.
    negative = run([-6, -4, -2, 0])
    assert negative['statistic'] == -6  # No hidden positive-part modification.
    assert negative['tail_probability'] == 1
    assert run([0, 2, 4, 6])['tail_probability'] == 0


def test_white_rc_assumptions_and_constant_columns():
    assert_failure(white_reality_check(ROWS, blocks=BLOCKS, resamples=1, seed=0, stationary=False),
                   'unsupported', 'STATIONARY_WEAK_DEPENDENCE_REQUIRED')
    assert_failure(white_reality_check([(0,), (0,)], blocks=UNIT_BLOCKS, resamples=1, seed=0, stationary=True),
                   'unsupported', 'ZERO_VARIANCE_COLUMN')


def test_cscv_reversal_and_persistent_winner_oracles():
    reversal = pbo_cscv([[3, 1], [1, 3]], blocks=UNIT_BLOCKS)
    assert reversal['split_count'] == 2
    assert reversal['pbo'] == 1
    assert [split['train_blocks'] for split in reversal['splits']] == [(0,), (1,)]
    assert [split['winners'] for split in reversal['splits']] == [(0,), (1,)]
    assert all(split['test_ranks'] == (1.0,) for split in reversal['splits'])
    assert all(split['logits'][0] == pytest.approx(-math.log(2)) for split in reversal['splits'])
    persistent = pbo_cscv([[3, 1], [4, 2]], blocks=UNIT_BLOCKS)
    assert persistent['pbo'] == 0
    assert all(split['logits'][0] == pytest.approx(math.log(2)) for split in persistent['splits'])


def test_cscv_training_ties_midranks_and_column_permutation():
    # Train row 0 ties A,B. In row 1 A ranks 3 (above median), B ranks 1:
    # contribution 1/2. Reverse direction selects A, tied test rank 2.5:
    # contribution 0. Total PBO=1/4. No arbitrary first-winner choice.
    rows = [[2, 2, 0], [3, 0, 1]]
    result = pbo_cscv(rows, blocks=UNIT_BLOCKS)
    assert result['pbo'] == 0.25
    assert result['splits'][0]['winners'] == (0, 1)
    assert result['splits'][0]['winner_weight'] == 0.5
    assert result['splits'][0]['test_ranks'] == (3, 1)
    assert result['splits'][1]['test_ranks'] == (2.5,)
    assert pbo_cscv([list(reversed(row)) for row in rows], blocks=UNIT_BLOCKS)['pbo'] == 0.25
    assert rows == [[2, 2, 0], [3, 0, 1]]


def test_cscv_identical_constant_candidates_and_all_six_splits():
    result = pbo_cscv([[0, 0]] * 4, blocks=[[0], [1], [2], [3]])
    assert result['split_count'] == 6  # C(4,2), including both complement orientations.
    assert result['pbo'] == 1
    assert all(split['logits'] == (0, 0) for split in result['splits'])
    train_sets = {split['train_blocks'] for split in result['splits']}
    assert train_sets == {(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)}


def test_cscv_representable_subnormal_winner_is_not_rounded_into_tie():
    tiny = float.fromhex('0x0.0000000000001p-1022')
    result = pbo_cscv([[tiny, 0.0]] * 4, blocks=[[0], [1], [2], [3]])
    assert result['status'] == 'ok' and result['pbo'] == 0
    assert all(split['winners'] == (0,) and split['test_ranks'] == (2,) for split in result['splits'])


def test_cscv_raw_sum_overflow_is_explicitly_unsupported():
    assert_failure(pbo_cscv([[1e308, 0.0]] * 4, blocks=[[0], [1], [2], [3]]),
                   'unsupported', 'NUMERIC_RANGE')


def test_cscv_algebraic_requirements():
    assert_failure(pbo_cscv([[1], [2]], blocks=UNIT_BLOCKS), 'unsupported', 'AT_LEAST_TWO_CANDIDATES')
    assert_failure(pbo_cscv([[1, 2]] * 3, blocks=[[0], [1], [2]]), 'invalid', 'EVEN_BLOCK_COUNT_REQUIRED')


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_input_across_every_numeric_entrypoint(bad):
    calls = [sharpe_moments([0, bad]), psr([0, bad], reference_sharpe=0, iid=True),
             psr([0, 1], reference_sharpe=bad, iid=True), dsr_example(trial_sharpes=[bad, 1]),
             dsr([0, bad], trial_sharpes=[1], n_trials=1, independent_trials=True,
                 complete_trials=True, iid=True),
             white_reality_check([[0, 1], [bad, 2]], blocks=UNIT_BLOCKS, resamples=1, seed=0, stationary=True),
             pbo_cscv([[0, 1], [bad, 2]], blocks=UNIT_BLOCKS)]
    for result in calls:
        assert_failure(result, 'invalid', 'NONFINITE_INPUT')


@pytest.mark.parametrize('rows', [[[], []], [[1, 2], [3]], [[1, 2], []]])
def test_matrix_geometry(rows):
    assert_failure(pbo_cscv(rows, blocks=UNIT_BLOCKS), 'invalid', 'NONEMPTY_RECTANGULAR_MATRIX_REQUIRED')
    assert_failure(white_reality_check(rows, blocks=UNIT_BLOCKS, resamples=1, seed=0, stationary=True),
                   'invalid', 'NONEMPTY_RECTANGULAR_MATRIX_REQUIRED')


@pytest.mark.parametrize('rows', [[], [[1, 2]]])
def test_matrix_short_samples(rows):
    assert_failure(pbo_cscv(rows, blocks=UNIT_BLOCKS), 'unsupported', 'AT_LEAST_TWO_OBSERVATIONS')
    assert_failure(white_reality_check(rows, blocks=UNIT_BLOCKS, resamples=1, seed=0, stationary=True),
                   'unsupported', 'AT_LEAST_TWO_OBSERVATIONS')
