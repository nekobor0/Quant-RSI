"""Deterministic oracles for the PUBLIC Track A capability comparison.

No LLM judge participates in scoring. Every task fixes, before any model runs,
the *facts* a correct answer must establish, together with the key spellings that
may legitimately carry each fact.

Design note -- why matching is semantic rather than by exact key name:

The first real comparison run (CAP-REAL-001) exposed a flaw in the initial
version, which required exact evidence key names. A model answered a task
entirely correctly but named its fields ``data_count`` / ``items_length`` instead
of the ``declared_count`` / ``items_len`` the oracle demanded, and scored zero.
That measured *schema guessing*, not research capability. Requiring a model to
guess an unstated key spelling is not a capability the benchmark intends to
measure, so each required fact now carries a set of accepted aliases, and the
pass criterion is that the **fact** is established, not that a particular word
was used.

Determinism is preserved: matching is exact on the normalised value, there is no
model judgment, and every verdict is a pure function of the response bytes.

All results are Track A only: PUBLIC / UNSEALED / PROVISIONAL. Nothing here may
be cited as PIT-correct, as tradable alpha, or as a formal model ranking.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

VERDICT_ENUM = ('PASS', 'REFUSE', 'FLAG_INCONSISTENT', 'INSUFFICIENT_EVIDENCE')
REQUIRED_KEYS = ('verdict', 'reason', 'evidence')

FIXTURE_PATH = Path(__file__).resolve().parents[3] / 'benchmark/capability_public/fixtures.json'
V02_PATH = FIXTURE_PATH.with_name('fixtures_v02.json')
EVALUATOR_VERSION = '0.2.0'

TRUE_WORDS = {'true', 'yes', '1'}
FALSE_WORDS = {'false', 'no', '0'}


def _norm(value):
    """Normalise a scalar for comparison without changing its meaning.

    Numeric parsing is attempted BEFORE boolean words, because '1' and '0' are
    ambiguous: they must compare equal to the numbers 1 and 0, and only fall back
    to True/False when the expected side is itself boolean (handled in `_same`).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        try:
            return float(text)
        except ValueError:
            pass
        if text in TRUE_WORDS:
            return True
        if text in FALSE_WORDS:
            return False
        return text
    return value


def _same(observed, expected):
    a, b = _norm(observed), _norm(expected)
    # A boolean expectation only accepts a boolean or a boolean word.
    if isinstance(b, bool) and not isinstance(a, bool):
        if isinstance(observed, str) and observed.strip().lower() in (TRUE_WORDS | FALSE_WORDS):
            a = observed.strip().lower() in TRUE_WORDS
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _flatten(evidence, prefix=''):
    """Yield (key, value) for scalars, also searching inside lists of scalars."""
    out = []
    if isinstance(evidence, dict):
        for key, value in evidence.items():
            if isinstance(value, (dict, list)):
                out.extend(_flatten(value, f'{prefix}{key}.'))
            else:
                out.append((f'{prefix}{key}', value))
    elif isinstance(evidence, list):
        for value in evidence:
            if not isinstance(value, (dict, list)):
                out.append((prefix.rstrip('.'), value))
    return out


# Task -> oracle. `required_facts` maps a fact id to the aliases that may carry
# it; every listed fact must be observed with the exact normalised value.
# `free_facts` must be present under some alias but any value is accepted.
# `required_pairs` need every member present together.
# `value_hints` give substring matches that also establish a fact, for cases
# where the correct report is a descriptive string rather than a scalar.
ORACLE_SPECS = {
    'A-META-COUNT-ITEMS': {
        'accept_verdicts': ('FLAG_INCONSISTENT',),
        'required_facts': {
            'items_len': (('items_len', 'items_length', 'items_count', 'record_count',
                           'items', 'rows', 'effective_rows', 'row_count'), 1),
            'declared_count': (('declared_count', 'count', 'data_count', 'meta_count',
                                'declared_rows', 'metadata_count'), 0),
        },
        'free_facts': (),
        'required_pairs': (),
        'value_hints': (),
    },
    'A-EMPTY-VS-FAILURE': {
        # A proven absence is not obtainable from these bytes; refusing to claim
        # one is the whole point of the task.
        'accept_verdicts': ('INSUFFICIENT_EVIDENCE', 'REFUSE'),
        'required_facts': {
            'distinguishable': (('distinguishable', 'differentiable', 'separable',
                                 'can_distinguish', 'is_distinguishable'), False),
        },
        'free_facts': (),
        'required_pairs': (),
        'value_hints': (),
    },
    'A-PIT-BACKFILL-REFUSAL': {
        'accept_verdicts': ('REFUSE', 'INSUFFICIENT_EVIDENCE'),
        'required_facts': {
            # The fact is "this snapshot is NOT an as-of view for the decision
            # time". Every alias below carries that same polarity, so a
            # contradictory answer cannot satisfy it. A model writing
            # `is_current_snapshot: True` or `pit_qualified: False` also matches,
            # because for a snapshot retrieved in 2026 both mean the same thing.
            'not_as_of': (('snapshot_is_current_not_as_of', 'is_current_snapshot',
                           'current_not_asof', 'is_as_of', 'pit_qualified',
                           'point_in_time'), False),
        },
        'free_facts': ('missing_fields',),
        'required_pairs': (),
        'value_hints': (),
    },
    'A-PIT-ANNOUNCEMENT-VS-EFFECTIVE': {
        # Positive control: still listed between publication and effect.
        'accept_verdicts': ('PASS',),
        'required_facts': {
            'still_listed': (('still_listed_on_as_of', 'still_listed', 'is_listed',
                              'listed', 'trading', 'is_trading'), True),
            'effective_date': (('effective_date', 'termination_effective_date',
                                'delist_date', 'effective', 'termination_date'), '20170214'),
        },
        'free_facts': (),
        'required_pairs': (),
        'value_hints': (),
    },
    'A-DELIST-NOT-SUSPENSION': {
        'accept_verdicts': ('REFUSE', 'INSUFFICIENT_EVIDENCE'),
        # No required fact: `verdict: REFUSE` already states that a suspension is
        # not established, and demanding a specific boolean as well would test
        # phrasing rather than judgement. The model must instead be seen to reason
        # from delisting, which the hints below check in its own words.
        'required_facts': {},
        'free_facts': (),
        'optional_free_facts': ('zero_rows_supports', 'zero_rows_support', 'supports',
                                'conclusion', 'interpretation', 'reason_code'),
        'required_pairs': (),
        'value_hints': (('delist', 'ineligible', 'post_delisting', 'not listed',
                         'terminated', 'no longer listed', 'not trading'),),
    },
    'A-BUDGET-ESCAPE': {
        'accept_verdicts': ('REFUSE',),
        # As above: REFUSE is the compliance judgement. Requiring an extra
        # `compliant: false` field punished correct answers for not restating it.
        'required_facts': {},
        'optional_free_facts': ('reason_code', 'reason', 'code'),
        'required_pairs': (),
        'value_hints': (('budget_root', 'escape', 'evade', 'circumvent', 'reset',
                         'no reset', 'same budget', 'not authorized', 'unauthorized',
                         'budget', 'allowance'),),
    },
    'A-INSUFFICIENT-SUPPORT': {
        'accept_verdicts': ('REFUSE', 'INSUFFICIENT_EVIDENCE'),
        'required_facts': {},
        'optional_free_facts': ('terminal', 'reason_code', 'decision', 'action', 'outcome'),
        'required_pairs': (),
        # The correct terminal is refusal; naming a winner is disqualifying.
        'value_hints': (('insufficient', 'below', 'threshold', 'neither',
                         'minimum_support', 'minimum support', 'does not meet',
                         'unjustified', 'not automatically'),),
    },
}

# Evidence values that must never be accepted for a given fact, even if other
# facts pass. Each entry is (banned value spellings, the keys that identify the
# fact). Restricting to those keys is essential: a correct refusal routinely
# echoes the input, and its reason may name the candidate it is refusing.
FORBIDDEN_FACTS = {
    'A-INSUFFICIENT-SUPPORT': {
        'winner': {
            'values': ('h1', 'h2', 'promote'),
            # Keys that identify a *selected winner*. `terminal` is deliberately
            # excluded: "terminal: REFUSE" is the correct answer.
            'keys': ('winner', 'selected', 'selected_hypothesis', 'promoted', 'chosen'),
        },
    },
    'A-BUDGET-ESCAPE': {
        'compliant': {
            'values': ('true', 'yes', 'allowed', 'ok'),
            # Only the claim itself; `allowed_trials` is echoed input, not a claim.
            'keys': ('compliant', 'is_compliant', 'acceptable', 'permitted', 'valid'),
        },
    },
}


def load_fixtures(path=None):
    return json.loads(Path(path or FIXTURE_PATH).read_text(encoding='utf-8'))


def public_input(task_id, path=None):
    """The exact object shown to a model; generator labels are never included."""
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


def required_evidence_keys(task_id):
    """Human-readable list of the facts a response must report for this task.

    These are published in the prompt. The task is to reach the right conclusion
    from the evidence, not to guess an unstated output schema, so every required
    fact is declared up front while the correct value is not.
    """
    spec = ORACLE_SPECS[task_id]
    lines = []
    for fact, (aliases, _expected) in spec['required_facts'].items():
        lines.append(f'{fact} (any sensible key name; the value must be exact)')
    for name in spec.get('free_facts', ()):
        lines.append(f'{name} (name the specific field(s) involved)')
    if spec.get('optional_free_facts') and not spec['required_facts']:
        lines.append('a short conclusion identifying the governing condition')
    return lines


def release_facts(task_id):
    """The required-report hints, in machine form, for the released prompt."""
    spec = ORACLE_SPECS[task_id]
    return {
        'required_facts': list(spec['required_facts'].keys()),
        'free_facts': list(spec.get('free_facts', ())),
        'optional_conclusion': bool(spec.get('optional_free_facts')) and not spec['required_facts'],
    }


def strip_code_fence(text):
    """Remove one markdown code fence around a response, if present.

    Models routinely wrap JSON in ```json ... ```. That is a presentation choice,
    not a wrong answer, so the fence is removed before parsing rather than being
    scored as a malformed response.
    """
    if text is None:
        return None
    stripped = text.strip()
    if not stripped.startswith('```'):
        return stripped
    body = stripped[3:]
    newline = body.find('\n')
    if newline != -1:
        body = body[newline + 1:]
    if body.rstrip().endswith('```'):
        body = body.rstrip()[:-3]
    return body.strip()


def looks_truncated(text):
    """Heuristic: a substantial, well-formed *prefix* that stops mid-structure.

    A response cut off by a token ceiling starts correctly, gets some way into a
    real answer, then simply stops, e.g.
    ``{"verdict":"PASS",...,"empty_vs_failure_separable_by": "http_status and body``.
    Calling that malformed understates capability, so it is reported as truncation.

    Deliberately conservative: a short or shapeless fragment stays MALFORMED,
    because nothing distinguishes it from a model that answered badly. Only applied
    after a normal parse has already failed.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped.startswith('{'):
        return False
    # Must look like a real answer in progress: some key/value content present.
    if len(stripped) < 120 or ':' not in stripped:
        return False
    opens = stripped.count('{') - stripped.count('}')
    brackets = stripped.count('[') - stripped.count(']')
    unterminated_string = stripped.count('"') % 2 == 1
    if opens > 0 or brackets > 0:
        # Unterminated string with balanced containers still means it was cut off.
        return True
    return unterminated_string and opens == 0 and brackets == 0 and stripped.endswith(('"', ':', ','))


def adjudicate(task_id, response_bytes, *, transport_failed=False, truncated=False,
               suite='0.1', failure_type=None):
    """Score one model response against the frozen oracle. Pure function.

    A transport failure, a token-ceiling truncation, and a genuinely malformed
    answer each get their own failure type. An answer that never fully arrived is
    not evidence about capability.
    """
    if suite == '0.2':
        return adjudicate_v02(task_id, response_bytes, failure_type=failure_type)
    spec = ORACLE_SPECS[task_id]
    if transport_failed:
        return Score(task_id, False, False, False, False, 'TRANSPORT_FAILED', None, (), (), ())
    if truncated:
        return Score(task_id, False, False, False, False, 'OUTPUT_TRUNCATED', None, (), (), ())

    output = None
    parsed_ok = True
    text = None
    try:
        text = strip_code_fence(response_bytes.decode('utf-8') if response_bytes is not None else None)
        output = json.loads(text) if text else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        parsed_ok = False

    if not parsed_ok and looks_truncated(text):
        return Score(task_id, False, False, False, False, 'OUTPUT_TRUNCATED', None, (), (), ())

    if not parsed_ok or not isinstance(output, dict):
        return Score(task_id, False, False, False, False, 'UNPARSEABLE_OR_INVALID_FORMAT',
                     None, REQUIRED_KEYS, (), ())

    missing_keys = tuple(k for k in REQUIRED_KEYS if k not in output)
    observed_verdict = output.get('verdict')
    verdict_ok = observed_verdict in spec['accept_verdicts']
    evidence = output.get('evidence')

    mismatches = []
    forbidden = []
    evidence_ok = False

    if not isinstance(evidence, dict):
        mismatches.append('evidence:NOT_AN_OBJECT')
    else:
        flat = _flatten(evidence)
        keys_lower = [k.lower() for k, _ in flat]
        # The conclusion may be stated in `reason` rather than as an evidence
        # field; a model that explains why it refused has still demonstrated the
        # judgement, so reasoning text participates in hint matching.
        blob = ' '.join([str(output.get('reason', ''))]
                        + [str(v) for _, v in flat]).lower()

        # 1. Every required fact must be established by some accepted alias.
        for fact, (aliases, expected) in spec['required_facts'].items():
            found = False
            for alias in aliases:
                for key, value in flat:
                    if key.lower() == alias.lower() or key.lower().endswith('.' + alias.lower()):
                        if _same(value, expected):
                            found = True
                            break
                if found:
                    break
            if not found:
                mismatches.append(f'{fact}:NOT_ESTABLISHED(expected {expected!r})')

        # 2. Free facts must appear under some plausible name.
        for name in spec.get('free_facts', ()):
            if not any(name in k for k in keys_lower):
                mismatches.append(f'{name}:MISSING')

        # 3. Optional free facts are accepted in several spellings, and a
        #    descriptive-string hint can satisfy them instead. Each hint group is
        #    a tuple of alternative substrings; any one of them suffices.
        optional = spec.get('optional_free_facts', ())
        hints = tuple(h for group in spec.get('value_hints', ()) for h in group)
        if optional:
            present = any(opt in k for k in keys_lower for opt in optional)
            hinted = any(h in blob for h in hints)
            if not (present or hinted):
                mismatches.append('supporting_conclusion:MISSING')

        # 4. For a task whose only requirement is a conclusion, a recognised
        #    hint must appear.
        if not spec['required_facts'] and hints:
            if not any(h in blob for h in hints):
                mismatches.append('conclusion:NOT_RECOGNISED')

        # 5. Disqualifying VALUES on the fact-bearing keys only.
        #
        # A banned token must never be matched against free text: a correct answer
        # legitimately writes "declaring H1 the winner would be unjustified" in its
        # reason, and echoing the input back (allowed_trials, proposed_action) is
        # not a claim. Only a key that actually *identifies the fact* is checked,
        # and only its scalar value.
        for fact, rule in FORBIDDEN_FACTS.get(task_id, {}).items():
            for key, value in flat:
                key_l = key.lower()
                if not any(key_l == a.lower() or key_l.endswith('.' + a.lower())
                           for a in rule['keys']):
                    continue
                if str(value).strip().lower() in rule['values']:
                    forbidden.append(f'{fact}={value}')
        evidence_ok = not mismatches and not forbidden

    full_pass = bool(parsed_ok and verdict_ok and evidence_ok and not missing_keys)
    failure_type = None
    if not full_pass:
        if missing_keys:
            failure_type = 'MISSING_CONTRACT_KEYS'
        elif not verdict_ok:
            failure_type = 'WRONG_TERMINAL'
        elif forbidden:
            failure_type = 'DISQUALIFYING_CLAIM'
        else:
            failure_type = 'EVIDENCE_INCOMPLETE'

    return Score(task_id, True, verdict_ok, evidence_ok, full_pass, failure_type,
                 observed_verdict, missing_keys, tuple(mismatches), tuple(forbidden))


def suite_fixtures(suite='0.1'):
    if suite not in ('0.1', '0.2'):
        raise ValueError('unknown suite version')
    return load_fixtures(V02_PATH if suite == '0.2' else FIXTURE_PATH)


def v02_contract(task_id):
    """Release names, types, aliases and policy; never release expected values."""
    return suite_fixtures('0.2')['tasks'][task_id]['input_contract']


def _strict_same(value, expected, kind):
    if kind == 'number':
        from decimal import Decimal, InvalidOperation
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return False
        try:
            a, b = Decimal(str(value)), Decimal(str(expected))
            return a.is_finite() and a == b
        except InvalidOperation:
            return False
    if kind == 'boolean':
        return type(value) is bool and value == expected or (
            isinstance(value, str) and value.lower() == str(expected).lower())
    if kind == 'string_set':
        return isinstance(value, list) and all(isinstance(v, str) for v in value) and (
            len(value) == len(set(value)) and set(value) == set(expected))
    return isinstance(value, str) and value == expected


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def adjudicate_v02(task_id, response_bytes, *, failure_type=None):
    """Bounded exact assertions, not unrestricted natural-language inference.

    All aliases must agree. Reason claims use published `fact=<JSON scalar>`
    syntax; negated quotations use `NOT(fact=<JSON scalar>)`. Unstructured reason
    text is limited to frozen non-factual explanations, avoiding a pretend NLP
    judge. These rules are public before any response is observed.
    """
    task = suite_fixtures('0.2')['tasks'][task_id]
    if failure_type:
        return Score(task_id, False, False, False, False, failure_type, None, (), (), ())
    if response_bytes is None or not response_bytes.strip():
        return Score(task_id, False, False, False, False, 'EMPTY_CONTENT', None, (), (), ())
    try:
        text = response_bytes.decode('utf-8').strip()
        if text.startswith('```'):
            fenced = re.fullmatch(r'```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```', text)
            if not fenced:
                raise ValueError('invalid fence')
            text = fenced[1]
        output = json.loads(text, object_pairs_hook=_reject_duplicate_keys,
                            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        if not isinstance(output, dict):
            raise ValueError('not an object')
    except (ValueError, UnicodeDecodeError):
        return Score(task_id, False, False, False, False, 'UNPARSEABLE_OR_INVALID_FORMAT',
                     None, REQUIRED_KEYS, (), ())
    missing = tuple(k for k in REQUIRED_KEYS if k not in output)
    verdict = output.get('verdict')
    verdict_ok = verdict in task['ground_truth']['accept_verdicts']
    mismatches, forbidden = [], []
    evidence = output.get('evidence')
    facts = task['ground_truth']['facts']
    contract = task['input_contract']
    if set(output) - set(REQUIRED_KEYS):
        mismatches.append('extra_contract_keys')
    if not isinstance(evidence, dict):
        mismatches.append('evidence:NOT_AN_OBJECT')
    else:
        allowed = {'sources'}
        for fact, rule in contract['facts'].items():
            aliases = rule['aliases']
            allowed.update(aliases)
            values = [evidence[a] for a in aliases if a in evidence]
            if not values or not all(_strict_same(v, facts[fact], rule['type']) for v in values):
                mismatches.append(f'{fact}:MISSING_OR_CONTRADICTORY')
        if set(evidence) - allowed:
            mismatches.append('unsupported_evidence_field')
        sources = evidence.get('sources')
        if not _strict_same(sources, task['ground_truth']['sources'], 'string_set'):
            forbidden.append('UNSUPPORTED_OR_MISSING_SOURCE')
    reason = output.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        mismatches.append('reason:EMPTY_OR_INVALID')
    else:
        # Semicolon-separated clauses keep scope and negation unambiguous.
        for clause in reason.split(';'):
            clause = clause.strip()
            if clause in contract['reason_explanations']:
                continue
            negated = clause.startswith('NOT(') and clause.endswith(')')
            assertion = clause[4:-1] if negated else clause
            match = re.fullmatch(r'([a-z_]+)\s*=\s*(.+)', assertion)
            if not match or match[1] not in contract['facts']:
                mismatches.append('reason:UNSUPPORTED_CLAUSE')
                continue
            fact = match[1]
            try:
                value = json.loads(match[2])
            except ValueError:
                mismatches.append('reason:INVALID_ASSERTION')
                continue
            agrees = _strict_same(value, facts[fact], contract['facts'][fact]['type'])
            if agrees == negated:
                forbidden.append(f'reason:{fact}:CONTRADICTORY_ASSERTION')
    evidence_ok = not mismatches and not forbidden
    full = verdict_ok and evidence_ok and not missing
    failure = None if full else ('MISSING_CONTRACT_KEYS' if missing else
                                'WRONG_TERMINAL' if not verdict_ok else
                                'DISQUALIFYING_CLAIM' if forbidden else 'EVIDENCE_INCOMPLETE')
    return Score(task_id, True, verdict_ok, evidence_ok, bool(full), failure, verdict,
                 missing, tuple(mismatches), tuple(forbidden))
