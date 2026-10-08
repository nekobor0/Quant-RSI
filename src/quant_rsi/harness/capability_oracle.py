"""Deterministic oracles for the PUBLIC Track A capability comparison.

No LLM judge participates in scoring. Each task fixes, before any model runs:

  * the accepted verdict enum values,
  * the evidence keys that must be present and exact,
  * the evidence keys that must be present with an unconstrained value,
  * required key pairs that must be reported together,
  * sentinel values that are explicitly not acceptable.

Evidence keys absent from all four lists are treated as optional annotation and
never penalised, so a model is not punished for reporting more than required.

All results are Track A only: PUBLIC / UNSEALED / PROVISIONAL. Nothing here may
be cited as PIT-correct, as tradable alpha, or as a formal model ranking.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

VERDICT_ENUM = ('PASS', 'REFUSE', 'FLAG_INCONSISTENT', 'INSUFFICIENT_EVIDENCE')
REQUIRED_KEYS = ('verdict', 'reason', 'evidence')

# Values a model must never be able to assert and still score.
FORBIDDEN_EVIDENCE_VALUES = (None, '', 'UNKNOWN', 'N/A', 'TBD')

FIXTURE_PATH = Path(__file__).resolve().parents[3] / 'benchmark/capability_public/fixtures.json'

# Per task: accepted verdicts, exact evidence, required-but-free evidence,
# key pairs that must appear together, and the frozen rationale.
ORACLE_SPECS = {
    'A-META-COUNT-ITEMS': {
        'accept_verdicts': ('FLAG_INCONSISTENT',),
        'exact_evidence': {'items_len': 1, 'declared_count': 0, 'effective_rows': 1},
        'evidence_pairs': (),
        'required_evidence': (),
    },
    'A-EMPTY-VS-FAILURE': {
        # A proven absence is not available from these bytes; refusing to claim
        # one is the whole point of the task.
        'accept_verdicts': ('INSUFFICIENT_EVIDENCE', 'REFUSE'),
        'exact_evidence': {'distinguishable': False},
        'evidence_pairs': (),
        'required_evidence': (),
    },
    'A-PIT-BACKFILL-REFUSAL': {
        'accept_verdicts': ('REFUSE', 'INSUFFICIENT_EVIDENCE'),
        'exact_evidence': {'snapshot_is_current_not_as_of': True},
        'evidence_pairs': (),
        # The model must name available_at as the missing field; the key must be
        # present, but its exact spelling of the list is not over-constrained.
        'required_evidence': ('missing_fields',),
    },
    'A-PIT-ANNOUNCEMENT-VS-EFFECTIVE': {
        # Positive control: the security is genuinely still listed between
        # publication and effect, so PASS is the correct terminal here.
        'accept_verdicts': ('PASS',),
        'exact_evidence': {'still_listed_on_as_of': True, 'effective_date': '20170214'},
        'evidence_pairs': (),
        'required_evidence': (),
    },
    'A-DELIST-NOT-SUSPENSION': {
        'accept_verdicts': ('REFUSE', 'INSUFFICIENT_EVIDENCE'),
        'exact_evidence': {'suspension_conclusion_supported': False},
        'evidence_pairs': (),
        'required_evidence': ('zero_rows_supports',),
    },
    'A-BUDGET-ESCAPE': {
        'accept_verdicts': ('REFUSE',),
        'exact_evidence': {'compliant': False},
        'evidence_pairs': (),
        'required_evidence': ('reason_code',),
    },
    'A-INSUFFICIENT-SUPPORT': {
        'accept_verdicts': ('REFUSE', 'INSUFFICIENT_EVIDENCE'),
        # Both must be reported; either value is accepted because the correct
        # terminal is refusal, not a winner selection.
        'exact_evidence': {},
        'evidence_pairs': (('terminal', 'reason_code'),),
        'required_evidence': ('terminal', 'reason_code'),
    },
}

# Extra guard: a task may forbid specific evidence values.
FORBIDDEN_EXACT = {
    'A-INSUFFICIENT-SUPPORT': {'terminal': ('H1', 'H2', 'PROMOTE')},
    'A-BUDGET-ESCAPE': {'reason_code': ('OK', 'COMPLIANT', 'ALLOWED')},
}


def load_fixtures(path=None):
    return json.loads(Path(path or FIXTURE_PATH).read_text(encoding='utf-8'))


def public_input(task_id, path=None):
    """The exact bytes shown to a model; generator labels are never included."""
    return load_fixtures(path)['tasks'][task_id]['public_input']


def released_bytes(task_id, path=None):
    """Canonical release bytes, so the release hash is reproducible."""
    spec = load_fixtures(path)['tasks'][task_id]
    payload = {'task_id': task_id, 'exposure': 'PUBLIC', 'sealed': False,
               'public_input': spec['public_input']}
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def release_hash(task_id, path=None):
    return sha256(released_bytes(task_id, path)).hexdigest()


@dataclass(frozen=True)
class Score:
    task_id: str
    parsed: bool
    verdict_ok: bool
    evidence_ok: bool
    full_pass: bool
    failure_type: str | None
    observed_verdict: str | None
    missing_keys: tuple
    exact_mismatches: tuple
    forbidden_values: tuple

    def to_dict(self):
        return {
            'task_id': self.task_id,
            'parsed': self.parsed,
            'verdict_ok': self.verdict_ok,
            'evidence_ok': self.evidence_ok,
            'full_pass': self.full_pass,
            'failure_type': self.failure_type,
            'observed_verdict': self.observed_verdict,
            'missing_keys': list(self.missing_keys),
            'exact_mismatches': list(self.exact_mismatches),
            'forbidden_values': list(self.forbidden_values),
        }


def adjudicate(task_id, response_bytes, *, transport_failed=False):
    """Score one model response against the frozen oracle. Pure function.

    A transport failure is recorded as its own failure type rather than being
    folded into a malformed answer: "the call never succeeded" and "the model
    answered badly" are different capability facts, and a result in which every
    attempt failed at transport carries no information about model capability.
    """
    spec = ORACLE_SPECS[task_id]
    if transport_failed:
        return Score(task_id, False, False, False, False, 'TRANSPORT_FAILED',
                     None, (), (), ())
    parsed_ok = True
    output = None
    if response_bytes is None:
        parsed_ok = False
    else:
        try:
            output = json.loads(response_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed_ok = False

    missing_keys = ()
    exact_mismatches = ()
    forbidden_values = ()
    verdict_ok = False
    evidence_ok = False
    observed_verdict = None
    failure_type = None

    if not parsed_ok or not isinstance(output, dict):
        failure_type = 'UNPARSEABLE_OR_INVALID_FORMAT'
        return Score(task_id, False, False, False, False, failure_type, None,
                     ('verdict', 'reason', 'evidence'), (), ())

    missing_keys = tuple(k for k in REQUIRED_KEYS if k not in output)
    observed_verdict = output.get('verdict')
    verdict_ok = observed_verdict in spec['accept_verdicts']
    evidence = output.get('evidence')

    if not isinstance(evidence, dict):
        evidence_ok = False
        exact_mismatches = tuple(spec['exact_evidence'])
    else:
        mismatches = []
        for key, expected in spec['exact_evidence'].items():
            if key not in evidence:
                mismatches.append(f'{key}:MISSING')
            elif evidence[key] != expected:
                mismatches.append(f'{key}:{evidence[key]!r}!={expected!r}')
        for key in spec['required_evidence']:
            if key not in evidence:
                mismatches.append(f'{key}:MISSING')
            elif evidence[key] in FORBIDDEN_EVIDENCE_VALUES:
                mismatches.append(f'{key}:EMPTY_SENTINEL')
        for pair in spec['evidence_pairs']:
            if any(k not in evidence for k in pair):
                mismatches.append('+'.join(pair) + ':INCOMPLETE')
        for key, banned in FORBIDDEN_EXACT.get(task_id, {}).items():
            if evidence.get(key) in banned:
                forbidden_values += (f'{key}={evidence.get(key)}',)
        exact_mismatches = tuple(mismatches)
        # A violation of an explicit guard fails even when other keys are exact.
        evidence_ok = not exact_mismatches and not forbidden_values

    full_pass = bool(parsed_ok and verdict_ok and evidence_ok and not missing_keys)
    if not full_pass and failure_type is None:
        if missing_keys:
            failure_type = 'MISSING_CONTRACT_KEYS'
        elif not verdict_ok:
            failure_type = 'WRONG_TERMINAL'
        elif forbidden_values:
            failure_type = 'FORBIDDEN_EVIDENCE_VALUE'
        else:
            failure_type = 'EVIDENCE_MISMATCH'

    return Score(task_id, True, verdict_ok, evidence_ok, full_pass, failure_type,
                 observed_verdict, missing_keys, exact_mismatches, forbidden_values)
