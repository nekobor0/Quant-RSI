"""W10A computation only: no inference policy, calibration or gate decisions.

All arrays are finite real numbers; matrices are time rows x candidate columns.
Returns supplied to Sharpe routines are already excess returns, in one common
period (no risk-free subtraction or annualization here). 'ok' means a numerical
computation succeeded, never that statistical assumptions have been verified.
Assumption flags are caller assertions, not diagnostics inferred from data.
Results are local dictionaries, not shared contracts. Failure has no value.
Only stdlib is required. No input is mutated and no global RNG is used.
"""
from functools import wraps
from itertools import combinations
import math
from random import Random
from statistics import NormalDist


class _Invalid(ValueError):
    pass


class _Unsupported(ValueError):
    pass


def _primitive(function):
    @wraps(function)
    def compute(*args, **kwargs):
        try:
            return dict(status='ok', **function(*args, **kwargs))
        except _Invalid as exc:
            return {'status': 'invalid', 'reason': str(exc)}
        except _Unsupported as exc:
            return {'status': 'unsupported', 'reason': str(exc)}
        except ArithmeticError:
            return {'status': 'unsupported', 'reason': 'NUMERIC_RANGE'}
    return compute


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid('FINITE_REAL_REQUIRED')
    value = float(value)
    if not math.isfinite(value):
        raise _Invalid('NONFINITE_INPUT')
    return value


def _integer(value, minimum):
    if type(value) is not int or value < minimum:
        raise _Invalid('INTEGER_OUT_OF_RANGE')
    return value


def _sequence(values):
    if not isinstance(values, (list, tuple)):
        raise _Invalid('LIST_OR_TUPLE_REQUIRED')
    return tuple(values)


def _vector(values):
    return tuple(_number(value) for value in _sequence(values))


def _finite(value):
    if not math.isfinite(value):
        raise _Unsupported('NUMERIC_RANGE')
    return value


def _mean(values):
    # Sum before division to preserve representable subnormal means.
    # Overflow is explicitly unsupported through the primitive wrapper.
    return _finite(math.fsum(values) / len(values))


def _moments(returns):
    values = _vector(returns)
    n = len(values)
    if n < 2:
        raise _Unsupported('AT_LEAST_TWO_OBSERVATIONS')
    if min(values) == max(values):
        raise _Unsupported('ZERO_VARIANCE')
    scale = max(abs(value) for value in values)
    scaled = tuple(value / scale for value in values)
    mean = _mean(scaled)
    centered = tuple(value - mean for value in scaled)
    m2 = _mean(tuple(value * value for value in centered))
    if m2 <= 0:
        raise _Unsupported('NUMERIC_RANGE')
    sd = math.sqrt(m2)
    z = tuple(value / sd for value in centered)
    return {'n_obs': n,
            'sharpe': _finite((mean / sd) * math.sqrt((n - 1) / n)),
            'skewness': _mean(tuple(value ** 3 for value in z)),
            'kurtosis': _mean(tuple(value ** 4 for value in z))}


def _psr(moments, reference):
    sr = moments['sharpe']
    # Population standardized central moments; kurtosis is NOT excess kurtosis.
    variance_factor = _finite(1 - moments['skewness'] * sr
                             + (moments['kurtosis'] - 1) * sr * sr / 4)
    if variance_factor <= 0:
        raise _Unsupported('NONPOSITIVE_PSR_VARIANCE')
    z = _finite((sr - reference) * math.sqrt(moments['n_obs'] - 1)
                / math.sqrt(variance_factor))
    return dict(moments, reference_sharpe=reference, variance_factor=variance_factor,
                z=z, probability=NormalDist().cdf(z))


@_primitive
def sharpe_moments(returns):
    """SR=mean/s_(n-1); skew=m3/m2^1.5; kurt=m4/m2^2, mk=sum((x-mean)^k)/n.

    n>=2 is algebraic support only, not a sample-size adequacy rule. Constants
    have undefined Sharpe. Scaling before moments avoids raw-power overflow.
    """
    return _moments(returns)


@_primitive
def psr(returns, *, reference_sharpe, iid):
    """Phi((SR-reference)*sqrt(n-1)/sqrt(1-skew*SR+(kurt-1)*SR^2/4)).

    IID observations and finite population fourth moment must be asserted via
    iid=True; this is an asymptotic plug-in approximation, not an exact small-n
    probability. Unknown/dependent sampling is unsupported, with no HAC fallback.
    Empirical finite moments cannot establish population moment existence.
    """
    reference = _number(reference_sharpe)
    moments = _moments(returns)
    if iid is not True:
        raise _Unsupported('IID_FINITE_FOURTH_MOMENT_REQUIRED')
    return _psr(moments, reference)


@_primitive
def dsr(returns, *, trial_sharpes, n_trials, independent_trials, complete_trials, iid):
    """PSR against an approximate zero-null expected maximum trial Sharpe.

    Caller supplies ALL comparable trial SR estimates (including unsuccessful
    trials), declared count, and explicit completeness/independence assertions.
    Missing/failed numeric estimates cannot be dropped or imputed. Trial SRs must
    admit an IID Gaussian zero-null approximation with a common variance. This
    assertion is independent of the return IID/finite-fourth-moment assertion.
    No effective-N estimator or correlation inference is provided.

    N=1: reference=0. N>=2: reference=s_trial*((1-gamma)*Phi^-1(1-1/N)
    + gamma*Phi^-1(1-1/(N*e))), gamma=Euler's constant, s_trial uses N-1.
    This extreme-value approximation is NOT the exact Gaussian expected max.
    Zero trial spread is unsupported for N>1, including identical candidates.
    The supplied list's provenance/independence cannot be verified from scalars.
    """
    n = _integer(n_trials, 1)
    trials = _vector(trial_sharpes)
    if len(trials) != n:
        raise _Invalid('TRIAL_COUNT_MISMATCH')
    if complete_trials is not True:
        raise _Unsupported('COMPLETE_TRIAL_RESULTS_REQUIRED')
    if independent_trials is not True:
        raise _Unsupported('INDEPENDENT_GAUSSIAN_TRIALS_REQUIRED')
    moments = _moments(returns)
    if iid is not True:
        raise _Unsupported('IID_FINITE_FOURTH_MOMENT_REQUIRED')
    reference = 0.0
    trial_sd = None
    if n > 1:
        if min(trials) == max(trials):
            raise _Unsupported('ZERO_TRIAL_VARIANCE')
        scale = max(abs(value) for value in trials)
        scaled = tuple(value / scale for value in trials)
        mean = _mean(scaled)
        trial_sd = _finite(scale * math.sqrt(math.fsum(
            (value - mean) ** 2 / (n - 1) for value in scaled)))
        if trial_sd <= 0:
            raise _Unsupported('NUMERIC_RANGE')
        p1, p2 = 1 - 1 / n, 1 - 1 / (n * math.e)
        if not 0 < p1 < 1 or not 0 < p2 < 1:
            raise _Unsupported('NORMAL_QUANTILE_RANGE')
        gamma = 0.5772156649015329
        reference = _finite(trial_sd * ((1 - gamma) * NormalDist().inv_cdf(p1)
                                       + gamma * NormalDist().inv_cdf(p2)))
    return dict(_psr(moments, reference), n_trials=n, trial_sd=trial_sd)


def _blocks(n_obs, blocks):
    _integer(n_obs, 2)
    parts = tuple(_sequence(block) for block in _sequence(blocks))
    if not parts or not parts[0]:
        raise _Invalid('EMPTY_BLOCKS')
    width = len(parts[0])
    if any(len(block) != width for block in parts):
        raise _Invalid('UNEQUAL_BLOCK_LENGTH')
    flat = tuple(index for block in parts for index in block)
    if any(type(index) is not int for index in flat) or flat != tuple(range(n_obs)):
        raise _Invalid('ORDERED_CONTIGUOUS_PARTITION_REQUIRED')
    if len(parts) < 2:
        raise _Unsupported('AT_LEAST_TWO_BLOCKS')
    return parts


def _draws(n_obs, blocks, resamples, seed):
    parts = _blocks(n_obs, blocks)
    _integer(resamples, 1)
    if type(seed) is not int:
        raise _Invalid('INTEGER_SEED_REQUIRED')
    rng = Random(seed)
    return tuple(tuple(index for _ in parts for index in parts[rng.randrange(len(parts))])
                 for _ in range(resamples))


@_primitive
def block_bootstrap(n_obs, *, blocks, resamples, seed):
    """Return index draws from an explicit nonoverlapping block bootstrap.

    blocks must be an ordered, equal-length, contiguous partition of 0..n-1,
    with at least two blocks. For each resample, draw K blocks uniformly with
    replacement and concatenate, giving exactly n rows. No truncation, circular
    wrapping, inferred length or alternate method. Use the SAME index draw for
    all candidate columns to preserve cross-candidate dependence.
    """
    return {'indices': _draws(n_obs, blocks, resamples, seed)}


def _matrix(values):
    rows = tuple(_vector(row) for row in _sequence(values))
    if len(rows) < 2:
        raise _Unsupported('AT_LEAST_TWO_OBSERVATIONS')
    if not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise _Invalid('NONEMPTY_RECTANGULAR_MATRIX_REQUIRED')
    return rows


@_primitive
def white_reality_check(differentials, *, blocks, resamples, seed, stationary):
    """Unstudentized White RC for candidate-minus-benchmark differentials.

    T=sqrt(n)*max_j(mean_j). Each joint block draw gives
    T*=sqrt(n)*max_j(mean(draw_j-mean_j)). Return empirical fraction T*>=T,
    including ties, with no plus-one correction or clipping T at zero. This is
    a Monte Carlo bootstrap tail estimate; 0 is possible, not proof of anything.
    stationary=True asserts stationarity, weak temporal dependence and finite
    second moments suitable for the caller's fixed blocks. No adequacy check is
    inferred. Cross-candidate dependence/duplicates ARE allowed and preserved.
    This implementation excludes any constant column (degenerate bootstrap).
    """
    rows = _matrix(differentials)
    indices = _draws(len(rows), blocks, resamples, seed)
    if stationary is not True:
        raise _Unsupported('STATIONARY_WEAK_DEPENDENCE_REQUIRED')
    columns = tuple(zip(*rows))
    if any(min(column) == max(column) for column in columns):
        raise _Unsupported('ZERO_VARIANCE_COLUMN')
    means = tuple(_mean(column) for column in columns)
    centered = tuple(tuple(_finite(value - mean) for value in column)
                     for column, mean in zip(columns, means))
    root_n = math.sqrt(len(rows))
    observed = _finite(root_n * max(means))
    samples = tuple(_finite(root_n * max(_mean(tuple(column[i] for i in draw))
                                         for column in centered)) for draw in indices)
    count = sum(value >= observed for value in samples)
    return {'statistic': observed, 'bootstrap_statistics': samples,
            'tail_count': count, 'resamples': resamples, 'tail_probability': count / resamples}


@_primitive
def pbo_cscv(returns, *, blocks):
    """Exhaustive CSCV using arithmetic mean as the ONLY candidate score.

    At least two candidates and an even number S>=2 of equal contiguous blocks.
    Enumerate all C(S,S/2) training block subsets; test on each complement.
    Training-score ties split winner weight equally, never pick a column by ID.
    Test scores rank ascending (1=worst), exact ties get midranks r.
    w=r/(M+1); logit=log(w/(1-w)); PBO=average weighted 1[logit<=0].
    Thus all identical candidates give w=1/2, logit=0, PBO=1 by this explicit
    at-or-below-median convention. Ties are exact float equality, no tolerance.
    Dependent columns are allowed. This descriptive combinatorial statistic
    imposes no IID claim, purge/embargo, temporal OOS claim or inference policy.
    Constant columns are valid for this mean/rank statistic (unlike Sharpe/RC).
    """
    rows = _matrix(returns)
    parts = _blocks(len(rows), blocks)
    m = len(rows[0])
    if m < 2:
        raise _Unsupported('AT_LEAST_TWO_CANDIDATES')
    if len(parts) % 2:
        raise _Invalid('EVEN_BLOCK_COUNT_REQUIRED')
    splits = []
    contributions = []
    for train in combinations(range(len(parts)), len(parts) // 2):
        training = tuple(i for b in train for i in parts[b])
        testing = tuple(i for b in range(len(parts)) if b not in train for i in parts[b])
        train_scores = tuple(_mean(tuple(rows[i][j] for i in training)) for j in range(m))
        test_scores = tuple(_mean(tuple(rows[i][j] for i in testing)) for j in range(m))
        winners = tuple(j for j in range(m) if train_scores[j] == max(train_scores))
        ranks = tuple(1 + sum(value < test_scores[j] for value in test_scores)
                      + (sum(value == test_scores[j] for value in test_scores) - 1) / 2
                      for j in winners)
        logits = tuple(math.log(rank / (m + 1 - rank)) for rank in ranks)
        contributions.append(sum(value <= 0 for value in logits) / len(winners))
        splits.append({'train_blocks': train, 'winners': winners,
                       'winner_weight': 1 / len(winners), 'test_ranks': ranks, 'logits': logits})
    return {'pbo': _mean(contributions), 'split_count': len(splits), 'splits': tuple(splits)}
