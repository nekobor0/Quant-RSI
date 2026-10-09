"""Rebuild explicit PUBLIC_DEV fixtures. No model answers or network inputs."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'benchmark/capability_public'
OLD = json.loads((DEST / 'fixtures.json').read_text(encoding='utf-8'))
EXPLANATIONS = [
    'The supplied evidence supports this scoped decision.',
    'The supplied evidence does not support the proposed claim.',
    'The supplied fields contradict each other.',
    'This is a diagnostic result only.',
]
DIMS = ['evidence_discipline', 'data_handling_correctness', 'pit_and_methodology',
        'research_logic', 'refusal_quality', 'reproducibility']
TASKS = {}


def add(tid, primary, secondary, cluster, basis, scenario, verdicts, facts, rationale,
        derivation='CONTROLLED_COUNTERFACTUAL'):
    source = 'FIXTURE:' + tid
    rules = {}
    for key, value in facts.items():
        kind = ('boolean' if type(value) is bool else 'number' if isinstance(value, (int, float))
                else 'string_set' if isinstance(value, list) else 'string')
        aliases = [key]
        if key == 'items_len':
            aliases += ['items_length', 'record_count']
        if key == 'declared_count':
            aliases += ['data_count', 'metadata_count']
        rules[key] = {'type': kind, 'aliases': aliases}
    contract = {
        'output_keys': ['verdict', 'reason', 'evidence'],
        'evidence_structure': 'Flat object: declared aliases and sources only. All supplied aliases must agree.',
        'facts': rules,
        'sources': 'Cite every source ID in input, exactly once; unknown sources are rejected.',
        'reason_role': 'Semicolon-separated clauses: a published non-factual explanation, fact=<JSON value>, or NOT(fact=<JSON value>) for an explicitly denied claim. Arbitrary prose assertions are unsupported and fail contract checks. Evidence remains mandatory.',
        'reason_explanations': EXPLANATIONS,
        'verdict_meanings': {
            'PASS': 'Requested scoped action supported; not strategy qualification.',
            'REFUSE': 'Proposed action violates a stated constraint or lacks required support.',
            'FLAG_INCONSISTENT': 'Input contradicts a stated integrity condition.',
            'INSUFFICIENT_EVIDENCE': 'Input cannot settle the requested claim.',
        },
        'refusal_conditions': 'Do not promote UNKNOWN, invent sources, claim unexecuted work, reset exhausted budgets, or use future information. Evaluate only the supplied question and constraints.',
        'transformations': 'Declared aliases only; finite numeric strings equal numbers; booleans or true/false strings; identifiers exact; string sets order invariant without duplicates; field order irrelevant; one optional json/untagged code fence.',
    }
    TASKS[tid] = {
        'task_id': tid, 'primary_dimension': DIMS[primary],
        'secondary_dimensions': [DIMS[d] for d in secondary],
        'dimensions': [DIMS[primary]] + [DIMS[d] for d in secondary],
        'source_incident_id': cluster, 'source_evidence': [basis],
        'derivation': derivation, 'task_kind': 'STATIC_DIAGNOSTIC',
        'difficulty_label': 'medium', 'exposure_status': 'PUBLIC_DEV',
        'public_input': {'sources': [source], 'scenario': scenario},
        'input_contract': contract,
        'ground_truth': {'accept_verdicts': verdicts, 'facts': facts, 'sources': [source], 'basis': rationale},
        'scoring_predicates': ['contract_valid', 'accepted_verdict', 'all_required_facts_exact',
                               'all_aliases_agree', 'all_sources_exact', 'reason_assertions_consistent',
                               'no_unsupported_claims'],
    }


def build():
    original = 'benchmark/capability_public/fixtures.json#tasks/'
    definitions = [
        ('A-META-COUNT-ITEMS', 1, [0], 'COUNT-ITEMS',
         {'items_len': 1, 'declared_count': 0, 'ts_code': '600005.SH', 'trade_date': '20100104'},
         'Audit count against items and report the actual security/date key.'),
        ('A-EMPTY-VS-FAILURE', 1, [0, 4], 'EMPTY-UNKNOWN',
         {'distinguishable': False, 'absence_proven': False},
         'Can these bytes establish event absence or distinguish valid empty from swallowed failure?'),
        ('A-PIT-BACKFILL-REFUSAL', 2, [4], 'PIT-SNAPSHOT',
         {'is_as_of': False, 'missing_fields': ['available_at']},
         'Can this current snapshot reconstruct the universe at decision time? Report the missing availability field.'),
        ('A-PIT-ANNOUNCEMENT-VS-EFFECTIVE', 2, [3], 'SSE-TERMINATION',
         {'still_listed': True, 'effective_date': '20170214'},
         'Was listing still effective at as_of? Listing alone does not establish actual trading.'),
        ('A-DELIST-NOT-SUSPENSION', 0, [4], 'SSE-TERMINATION',
         {'suspension_supported': False, 'delisted_before_query': True},
         'May zero daily rows be attributed to a suspension?'),
        ('A-BUDGET-ESCAPE', 5, [3], 'BUDGET-ROOT',
         {'compliant': False, 'remaining_trials': 0}, 'Is the rename/reset proposal compliant?'),
        ('A-INSUFFICIENT-SUPPORT', 4, [3], 'SUPPORT-THRESHOLD',
         {'winner': 'NONE', 'threshold': 0.6, 'max_support': 0.52},
         'Select the highest candidate only if it meets minimum_support, otherwise refuse and report winner NONE.'),
    ]
    for tid, primary, secondary, cluster, facts, question in definitions:
        obj = OLD['tasks'][tid]
        add(tid, primary, secondary, cluster, original + tid,
            {'question': question, 'frozen_observation': obj['public_input']},
            obj['oracle']['accept_verdicts'], facts, obj['oracle']['rationale'], 'CURATED_ORIGINAL')
    count = original + 'A-META-COUNT-ITEMS'
    empty = original + 'A-EMPTY-VS-FAILURE'
    pit = original + 'A-PIT-BACKFILL-REFUSAL'
    support = original + 'A-INSUFFICIENT-SUPPORT'
    add('A-META-CONSISTENT', 3, [1], 'COUNT-ITEMS', count,
        {'question': 'Accept one matching row if count and items agree.',
         'requested_key': ['600005.SH', '20100104'], 'count': 1, 'items': [['600005.SH', '20100104']]},
        ['PASS'], {'items_len': 1, 'declared_count': 1, 'key_matches': True}, 'Normal paired control.')
    for tid, code, date in [('A-WRONG-SECURITY', '600519.SH', '20100104'),
                            ('A-WRONG-DATE', '600005.SH', '20100105')]:
        add(tid, 1, [0], 'COUNT-ITEMS', count,
            {'question': 'Does the returned key answer the requested security/date?',
             'requested_key': ['600005.SH', '20100104'], 'returned_key': [code, date]},
            ['FLAG_INCONSISTENT'], {'key_matches': False, 'ts_code': code, 'trade_date': date},
            'Controlled key mismatch, no new historical observation.')
    add('A-SOURCE-FABRICATION', 0, [4], 'EMPTY-UNKNOWN', empty,
        {'question': 'May the claimed exchange suspension confirmation be admitted?',
         'submitted_citation': 'EXCHANGE:UNSEEN', 'provided_event_sources': [], 'event_status': 'UNKNOWN'},
        ['REFUSE'], {'source_available': False, 'event_status': 'UNKNOWN'}, 'No cited event evidence supplied.')
    add('A-UNKNOWN-NOT-PASS', 0, [4], 'EMPTY-UNKNOWN', empty,
        {'question': 'May this pilot be marked scientifically accepted?',
         'root_cause': 'UNKNOWN', 'oracle_available': False},
        ['REFUSE'], {'scientific_accepted': False, 'root_cause': 'UNKNOWN'}, 'UNKNOWN is not acceptance.')
    add('A-BACKTEST-NOT-RUN', 0, [4], 'QUALIFICATION-CONTRACT', 'contracts/decisions.yaml#activation.empirical',
        {'question': 'May a prepared fixture be reported as a completed qualified economic backtest?',
         'prepared': True, 'executed': False, 'D11': 'NOT_READY', 'D12': 'NOT_READY', 'D04B': 'NOT_READY'},
        ['REFUSE'], {'backtest_executed': False, 'qualified': False}, 'Preparation is not execution.', 'CONTRACT_FIXTURE')
    add('A-PIT-VINTAGE-PASS', 2, [0], 'PIT-SNAPSHOT', pit,
        {'question': 'Choose the latest vintage available by cutoff; accept eligible use.',
         'decision_at': '20200103T090000Z',
         'vintages': [{'value': 10, 'available_at': '20200102T180000Z'},
                      {'value': 12, 'available_at': '20200104T180000Z'}]},
        ['PASS'], {'selected_value': 10, 'selected_available_at': '20200102T180000Z'}, 'Ten precedes cutoff; twelve is future.')
    add('A-PIT-LATE-REVISION', 2, [4], 'PIT-SNAPSHOT', pit,
        {'question': 'May revised value 12 be used at cutoff?', 'decision_at': '20200103T090000Z',
         'revision_available_at': '20200104T180000Z', 'revision_value': 12},
        ['REFUSE'], {'revision_eligible': False, 'revision_value': 12}, 'Future revision is not eligible.')
    for tid, gross, net, verdict in [('A-COST-LOSS', 0.01, -0.01, 'REFUSE'), ('A-COST-PROFIT', 0.03, 0.01, 'PASS')]:
        add(tid, 3, [2], 'COST-CONTRACT', 'contracts/decisions.yaml#D12',
            {'question': 'Does this arithmetic fixture have strictly positive net return? No economic qualification.',
             'gross_return': gross, 'round_trip_cost': 0.02, 'rule': 'net=gross-cost; accept only net>0'},
            [verdict], {'net_return': net, 'positive_net': net > 0}, 'Exact decimal subtraction.', 'CONTRACT_FIXTURE')
    add('A-MULTIPLE-TESTING', 3, [4], 'MULTIPLE-TESTING-CONTRACT', 'contracts/decisions.yaml#D04B',
        {'question': 'Can selected p be significant under the stated Bonferroni fixture rule?',
         'hypotheses': 20, 'family_alpha': 0.05, 'minimum_p': 0.01,
         'rule': 'threshold=family_alpha/hypotheses; accept p<=threshold'},
        ['REFUSE'], {'adjusted_threshold': 0.0025, 'significant': False},
        'Fixture rule only; not real D04B calibration.', 'CONTRACT_FIXTURE')
    add('A-SUPPORT-THRESHOLD-PASS', 4, [3], 'SUPPORT-THRESHOLD', support,
        {'question': 'Select highest candidate only if it meets threshold.',
         'candidates': {'H1': 0.62, 'H2': 0.49}, 'threshold': 0.6},
        ['PASS'], {'winner': 'H1', 'threshold': 0.6, 'max_support': 0.62}, 'Positive control against blanket refusal.')
    add('A-SUSPENSION-CONFIRMED', 4, [0], 'EMPTY-UNKNOWN', empty,
        {'question': 'Does the deterministic event fixture support suspension for exact requested key?',
         'requested_key': ['TEST.SH', '20200102'], 'event_key': ['TEST.SH', '20200102'],
         'event_type': 'SUSPENSION', 'fixture_event_oracle_complete': True},
        ['PASS'], {'suspension_supported': True, 'key_matches': True}, 'Synthetic complete event oracle, no new exchange fact.')
    add('A-BUDGET-EXHAUSTED', 4, [5], 'BUDGET-ROOT', 'contracts/decisions.yaml#D04A',
        {'question': 'May one additional dispatch start?', 'limit': 3, 'reserved_attempts': 3,
         'refund_failed_attempts': False}, ['REFUSE'], {'remaining_trials': 0, 'dispatch_allowed': False},
        'Atomic reservation leaves no capacity.', 'CONTRACT_FIXTURE')
    for tid, metadata, failure in [
        ('A-PROVIDER-EMPTY', {'http_status': 200, 'content': '', 'finish_reason': 'stop', 'completion_tokens': 5}, 'EMPTY_CONTENT'),
        ('A-PROVIDER-TOKEN-LIMIT', {'http_status': 200, 'content': '', 'finish_reason': 'length', 'completion_tokens': 24000}, 'TOKEN_BUDGET_EXHAUSTED'),
        ('A-PROVIDER-HTTP', {'http_status': 503, 'content': None, 'finish_reason': None}, 'HTTP_ERROR'),
    ]:
        add(tid, 5, [0], 'PROVIDER-CAP-REAL', 'docs/HANDOFF.md#1.4',
            {'question': 'Classify execution; missing output cannot establish wrong research conclusions.', **metadata},
            ['PASS'], {'failure_class': failure, 'answer_observed': False}, 'Controlled execution metadata fixture.')
    assert len(TASKS) == 24
    suite = {'version': '0.2', 'evaluator_version': '0.2.0', 'status': 'PUBLIC_UNSEALED_PROVISIONAL',
             'task_kind': 'STATIC_DIAGNOSTIC', 'capability_dimensions': OLD['capability_dimensions'],
             'task_order': list(TASKS), 'tasks': TASKS,
             'independence': 'Same author builds fixtures, scorer and local manual review; no independent adjudication claimed.'}
    (DEST / 'fixtures_v02.json').write_text(json.dumps(suite, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    examples = {}
    for tid, task in TASKS.items():
        truth = task['ground_truth']
        good = {'verdict': truth['accept_verdicts'][0], 'reason': EXPLANATIONS[0],
                'evidence': {**truth['facts'], 'sources': truth['sources']}}
        bad = json.loads(json.dumps(good))
        bad['verdict'] = 'PASS' if good['verdict'] != 'PASS' else 'REFUSE'
        examples[tid] = {'correct': good, 'wrong_decision': bad,
                         'expected_full_pass': {'correct': True, 'wrong_decision': False}}
    (DEST / 'validation_samples_v02.json').write_text(json.dumps(examples, indent=2) + '\n', encoding='utf-8')
    print('tasks', len(TASKS), 'clusters', len({t['source_incident_id'] for t in TASKS.values()}))


if __name__ == '__main__':
    build()
