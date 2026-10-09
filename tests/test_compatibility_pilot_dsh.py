"""Targeted tests for the derived DS-Harness pilot entry.

These address the specific gaps the audit found, which the earlier offline
capture did not cover:

  * the authorization path must actually be enterable with a correct approval,
    not merely refusable without one;
  * a blocking failure (auth / 429 / transport / missing usage) must stop the
    REAL runner loop, not only the provider — so at most one request goes out;
  * the derived entry binding must be the thing authorization compares, and the
    derived freeze's own sha256 map must actually be enforced.

No network and no real credentials: urlopen is replaced and a syntactically
plausible placeholder is injected via monkeypatch.setenv.
"""
from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from quant_rsi.harness import compatibility_pilot as pilot           # noqa: E402
from quant_rsi.harness import compatibility_pilot_dsh as dsh          # noqa: E402
from quant_rsi.harness import providers                               # noqa: E402

PLACEHOLDER = 'test-placeholder-not-a-credential'
FROZEN_BASE_ENTRY_SHA = 'cb5cef8e17e1142a3758ece4b584e0254c2e27ad64f66b1874e52a9ba4195419'
# Captured before any _bind(), because _bind() rebinds pilot.__file__ on purpose.
FROZEN_BASE_FILE = Path(pilot.__file__)


def _valid_body(model, content=None, finish='stop'):
    return {
        'id': 'x', 'object': 'chat.completion', 'model': model,
        'choices': [{'index': 0, 'finish_reason': finish, 'message': {
            'role': 'assistant', 'content': content if content is not None else
            '{"verdict":"PASS","reason":"The supplied evidence supports this scoped decision.",'
            '"evidence":{"backtest_executed":false,"qualified":false}}',
            'reasoning_content': 'r'}}],
        'usage': {'prompt_tokens': 1200, 'completion_tokens': 300, 'total_tokens': 1500,
                  'prompt_tokens_details': {'cached_tokens': 0},
                  'completion_tokens_details': {'reasoning_tokens': 100}},
    }


class _Resp:
    def __init__(self, payload, status=200):
        self.status = status
        self._p = payload

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install(monkeypatch, behaviour):
    """Replace urlopen with `behaviour(call_index, request) -> response|raise`."""
    calls = []

    def opener(request, timeout):
        calls.append(request)
        model = json.loads(request.data)['model']
        return behaviour(len(calls), model)

    monkeypatch.setattr(providers.urllib.request, 'urlopen', opener)
    monkeypatch.setenv('DEEPSEEK_API_KEY', PLACEHOLDER)
    monkeypatch.setenv('XIAOMI_API_KEY', PLACEHOLDER)
    return calls


def _approve(monkeypatch, tmp_path, *, entry_sha, freeze_sha, caps):
    """Write an approval bound to the given SHAs and return its path."""
    p = tmp_path / 'auth.json'
    p.write_text(json.dumps({
        'approved': True, 'keys_rotated': True, 'call_cap': 12,
        'freeze_sha256': freeze_sha, 'entry_sha256': entry_sha,
        'money_caps_cny': caps}, sort_keys=True), encoding='utf-8')
    return p


@pytest.fixture
def bound():
    """Bind the derived entry, then RESTORE the frozen module's globals.

    _bind() mutates the frozen module process-wide (FREEZE, ENTRY_PATH, __file__).
    Without this teardown the mutation leaks into every later test in the same
    process, which broke two frozen pilot tests when this module ran first.

    The frozen module is pristine by design, so ENTRY_PATH may not exist on it
    at all; getattr with a sentinel keeps this fixture correct either way. On
    teardown a missing attribute is deleted rather than set, so the frozen module
    returns to exactly its original shape.
    """
    missing = object()
    saved = {name: getattr(pilot, name, missing)
             for name in ('FREEZE', 'ENTRY_PATH', '__file__')}
    dsh._bind()
    try:
        yield dsh
    finally:
        for name, value in saved.items():
            if value is missing:
                if hasattr(pilot, name):
                    delattr(pilot, name)
            else:
                setattr(pilot, name, value)


# ---------------------------------------------------------------- bindings

def test_derived_entry_binding_is_what_authorization_compares(bound):
    """The audit's claim 2: the derived entry SHA must be the compared one.

    The frozen module is pristine and has no ENTRY_PATH; _bind() redirects the
    module __file__ attribute, which is what the frozen check_authorization()
    hashes. That redirect is the whole mechanism.
    """
    assert Path(pilot.__file__) == dsh.DERIVED_ENTRY
    assert dsh.entry_sha256() != FROZEN_BASE_ENTRY_SHA
    # And the redirect is exactly what the frozen checker will hash.
    assert Path(pilot.__file__).read_bytes() == dsh.DERIVED_ENTRY.read_bytes()
    # The redirect is runtime-only: the frozen file on disk is untouched.
    assert not hasattr(pilot, 'ENTRY_PATH') or pilot.ENTRY_PATH == dsh.DERIVED_ENTRY


def test_frozen_base_entry_bytes_are_untouched():
    """The base freeze pins this file; editing it breaks the base pilot."""
    from hashlib import sha256
    actual = sha256(FROZEN_BASE_FILE.read_bytes()).hexdigest()
    assert actual == FROZEN_BASE_ENTRY_SHA


def test_derived_binding_map_is_enforced(bound):
    """The audit's claim 3: the derived sha256 map must be verified, not decorative."""
    checked = dsh.validate_derived_bindings()
    assert len(checked) >= 10
    assert 'src/quant_rsi/harness/compatibility_pilot.py' in checked
    assert 'src/quant_rsi/harness/compatibility_pilot_dsh.py' in checked


def test_tampered_derived_binding_is_refused(bound, tmp_path, monkeypatch):
    plan = json.loads(dsh.DERIVED_FREEZE.read_text(encoding='utf-8'))
    plan['sha256']['src/quant_rsi/harness/providers.py'] = '0' * 64
    bad = tmp_path / 'bad_freeze.json'
    bad.write_text(json.dumps(plan), encoding='utf-8')
    with pytest.raises(ValueError, match='derived binding changed'):
        dsh.validate_derived_bindings(json.loads(bad.read_text(encoding='utf-8')))


def test_derived_budget_is_executable(bound):
    """The audit's claim 4: caps must parse as Decimal, not be a PENDING string."""
    from decimal import Decimal
    plan = json.loads(dsh.DERIVED_FREEZE.read_text(encoding='utf-8'))
    for provider, cap in plan['money_caps_cny'].items():
        assert Decimal(cap) > 0, provider
    for provider, cfg in plan['providers'].items():
        assert Decimal(cfg['worst_cost_cny_per_call']) > 0, provider


def test_no_self_hash_in_binding_map(bound):
    """A self-hash would make the freeze digest unstable."""
    plan = json.loads(dsh.DERIVED_FREEZE.read_text(encoding='utf-8'))
    assert 'benchmark/capability_public/pilot_v02_dsh/freeze.json' not in plan['sha256']


# ------------------------------------------------- the positive auth path

def test_correct_authorization_enters_simulated_transport(monkeypatch, tmp_path, bound):
    """The audit's claim 2, positively: a correct approval must actually run."""
    calls = _install(monkeypatch, lambda i, m: _Resp(json.dumps(_valid_body(m)).encode()))
    plan = pilot.load(dsh.DERIVED_FREEZE)
    auth = _approve(monkeypatch, tmp_path,
                    entry_sha=dsh.entry_sha256(),
                    freeze_sha=dsh.freeze_sha256(),
                    caps=plan['money_caps_cny'])
    out = tmp_path / 'run'
    result = pilot.run('DERIVED_AUTH_OK_001', pilot.load(auth), output_root=out)
    assert result['status'] == 'REAL_PILOT_EXECUTED'
    assert result['calls'] == 12, 'all six tasks x two models'
    assert len(calls) == 12
    assert result['entry_sha256'] == dsh.entry_sha256()
    # Budget was executable: a numeric reservation was made every time.
    assert all(v == '1.80' or v == '1.20' for v in result['reserved_cost_cny'].values())


def test_approval_bound_to_the_base_entry_is_refused(monkeypatch, tmp_path, bound):
    """Authorizing the base entry must not authorize a derived run."""
    _install(monkeypatch, lambda i, m: _Resp(json.dumps(_valid_body(m)).encode()))
    plan = pilot.load(dsh.DERIVED_FREEZE)
    auth = _approve(monkeypatch, tmp_path,
                    entry_sha=FROZEN_BASE_ENTRY_SHA,          # wrong entry
                    freeze_sha=dsh.freeze_sha256(),
                    caps=plan['money_caps_cny'])
    with pytest.raises(ValueError, match='explicit human batch approval'):
        pilot.run('DERIVED_AUTH_BAD_ENTRY_001', pilot.load(auth),
                  output_root=tmp_path / 'run2')


# ------------------------------------- batch stop after the first blockage

@pytest.mark.parametrize('case,behaviour,expect_stop', [
    ('auth_401',
     lambda i, m: (_ for _ in ()).throw(urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)),
     'AUTHENTICATION_STOP'),
    ('rate_429',
     lambda i, m: (_ for _ in ()).throw(urllib.error.HTTPError('u', 429, 'Too Many', {}, None)),
     'RATE_LIMIT_STOP'),
    ('timeout',
     lambda i, m: (_ for _ in ()).throw(TimeoutError('simulated timeout')),
     None),
], ids=['auth_401', 'rate_429', 'timeout'])
def test_blocking_failure_stops_the_batch_after_one_request(
        monkeypatch, tmp_path, bound, case, behaviour, expect_stop):
    """The audit's claim 5: the RUNNER loop must stop, not just the provider.

    Every blocking failure occurs on the very first dispatch, so exactly one
    request may leave and all remaining eleven must be recorded unattempted.
    """
    calls = _install(monkeypatch, behaviour)
    plan = pilot.load(dsh.DERIVED_FREEZE)
    auth = _approve(monkeypatch, tmp_path,
                    entry_sha=dsh.entry_sha256(),
                    freeze_sha=dsh.freeze_sha256(),
                    caps=plan['money_caps_cny'])
    result = pilot.run(f'DERIVED_STOP_{case.upper()}_001', pilot.load(auth),
                       output_root=tmp_path / f'run_{case}')

    assert len(calls) == 1, f'{case}: batch continued past the first blocking failure'
    assert result['calls'] == 1
    assert len(result['unattempted']) == 11
    assert result['stop'] is not None, f'{case}: no stop reason recorded'
    if expect_stop:
        assert result['stop'] == expect_stop
    # The failure is preserved rather than rewritten.
    assert result['records'][0]['provider_failure'] or result['stop']


def test_missing_usage_stops_and_is_not_recorded_as_free(monkeypatch, tmp_path, bound):
    """Unknown usage must keep the reservation and stop, never infer zero cost."""
    def behaviour(i, m):
        body = _valid_body(m)
        body['usage'] = {}                      # usage absent
        return _Resp(json.dumps(body).encode())
    calls = _install(monkeypatch, behaviour)
    plan = pilot.load(dsh.DERIVED_FREEZE)
    auth = _approve(monkeypatch, tmp_path,
                    entry_sha=dsh.entry_sha256(),
                    freeze_sha=dsh.freeze_sha256(),
                    caps=plan['money_caps_cny'])
    result = pilot.run('DERIVED_STOP_NOUSAGE_001', pilot.load(auth),
                       output_root=tmp_path / 'run_nousage')
    assert len(calls) == 1
    assert result['stop'] == 'UNKNOWN_USAGE_RECONCILIATION_REQUIRED'
    # The full per-call ceiling stays reserved for the provider.
    assert result['reserved_cost_cny']['deepseek'] == '0.30'


def test_model_identity_mismatch_stops_the_batch(monkeypatch, tmp_path, bound):
    """A response reporting another model must stop dispatch."""
    def behaviour(i, m):
        return _Resp(json.dumps(_valid_body('some-other-model')).encode())
    calls = _install(monkeypatch, behaviour)
    plan = pilot.load(dsh.DERIVED_FREEZE)
    auth = _approve(monkeypatch, tmp_path,
                    entry_sha=dsh.entry_sha256(),
                    freeze_sha=dsh.freeze_sha256(),
                    caps=plan['money_caps_cny'])
    result = pilot.run('DERIVED_STOP_MODELMISMATCH_001', pilot.load(auth),
                       output_root=tmp_path / 'run_mismatch')
    assert len(calls) == 1
    assert result['stop'] == 'MODEL_ID_MISMATCH'


def test_ordinary_wrong_answer_does_not_stop_the_batch(monkeypatch, tmp_path, bound):
    """A merely wrong answer is retained in place and the batch continues."""
    def behaviour(i, m):
        return _Resp(json.dumps(_valid_body(m, content='{"verdict":"PASS","reason":"x","evidence":{}}')).encode())
    calls = _install(monkeypatch, behaviour)
    plan = pilot.load(dsh.DERIVED_FREEZE)
    auth = _approve(monkeypatch, tmp_path,
                    entry_sha=dsh.entry_sha256(),
                    freeze_sha=dsh.freeze_sha256(),
                    caps=plan['money_caps_cny'])
    result = pilot.run('DERIVED_CONTINUE_001', pilot.load(auth),
                       output_root=tmp_path / 'run_continue')
    assert len(calls) == 12
    assert result['calls'] == 12
    assert result['stop'] is None
