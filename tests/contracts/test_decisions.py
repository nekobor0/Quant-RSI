from pathlib import Path

import yaml


REGISTRY = Path(__file__).resolve().parents[2] / 'contracts' / 'decisions.yaml'


def load():
    return yaml.safe_load(REGISTRY.read_text(encoding='utf-8'))


def test_one_registry_and_split_decision_scope():
    registry = load()
    ids = {'D01', 'D02', 'D03', 'D04A', 'D04B', 'D05', 'D06', 'D07', 'D08', 'D09', 'D10', 'D11', 'D12', 'D13'}
    assert set(registry['decisions']) == set(registry['decision_ids']) == ids
    assert registry['supersedes'] == {'D04': ['D04A', 'D04B']}
    assert registry['canonical'] is True


def test_only_freeze_now_decisions_are_frozen():
    for decision in load()['decisions'].values():
        assert decision['category'] in {'FREEZE_NOW', 'DEFER_UNTIL_EMPIRICAL', 'DEFER_UNTIL_SHADOW'}
        assert (decision['status'] == 'FROZEN') == (decision['category'] == 'FREEZE_NOW')


def test_statistical_parameters_are_not_fabricated():
    d = load()['decisions']
    for key in ('alpha', 'sample_minimum', 'bootstrap_block_length', 'resamples', 'CSCV_blocks', 'effect_threshold'):
        assert d['D04B']['value'][key] is None
    assert d['D04B']['value']['inference_allowed'] is False
    assert all(v is None for k in ('D09', 'D11', 'D12') for v in d[k]['value'].values())


def test_benchmark_accounting_is_not_scientific_selection_accounting():
    p = load()['decisions']['D04A']['value']
    assert p['benchmark_budget_owner'] != p['scientific_claim_owner']
    assert p['cross_model_penalty_on_capability'] == 'forbidden'
    assert p['capability_denominator'] == 'own_budget_root_run_attempts_only'


def test_scope_and_later_stage_remain_closed():
    d = load()
    assert d['decisions']['D01']['value'] == 'A_SHARE_ORDINARY_STOCK_DAILY'
    assert d['decisions']['D05']['mock_is_benchmark_grade'] is False
    assert d['activation']['stage_A']['authorized_work_items'] == [f'W{i:02}' for i in range(1, 7)]
    assert d['activation']['stage_A']['stop_after'] == 'W06'
    for stage in ('stage_B', 'empirical', 'shadow'):
        assert d['activation'][stage]['authorized'] is False
