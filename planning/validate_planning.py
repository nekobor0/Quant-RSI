"""Offline planning checks only. This is not a Harness runtime evaluator."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INPUT_NAMES = [
    "00_START_HERE.md", "01_LITERATURE_TO_HARNESS_TAKEAWAYS.md",
    "02_ASTRA_MASTER_TASKBOOK.md", "03_HARNESS_DESIGN_PRINCIPLES.yaml",
    "04_ASTRA_EXECUTION_PLAN.yaml", "05_SOURCE_INDEX.yaml", "06_DECISION_REGISTER.md",
]
INPUTS = ['docs/inputs/' + name for name in INPUT_NAMES]


def locate(name):
    candidates = [ROOT / name, ROOT / 'docs/inputs' / name, ROOT / 'planning/v0.2' / name]
    return next((p for p in candidates if p.is_file()), candidates[0])


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_yaml(name):
    return yaml.load(locate(name).read_text(encoding="utf-8"), Loader=UniqueLoader)


def digest(name):
    return hashlib.sha256(locate(name).read_bytes()).hexdigest()


def main():
    checks = []

    def check(name, condition, detail=""):
        checks.append({"check": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    plan = read_yaml("04_ASTRA_EXECUTION_PLAN.yaml")
    principles = read_yaml("03_HARNESS_DESIGN_PRINCIPLES.yaml")
    sources = read_yaml("05_SOURCE_INDEX.yaml")["sources"]
    report = read_yaml("planning_report.yaml")["planning_report"]
    gaps = read_yaml("01_GAP_MATRIX.yaml")["capabilities"]
    env = read_yaml("03_ENV_SPEC_DRAFT.yaml")
    evaluation = read_yaml("04_EVAL_SPEC_DRAFT.yaml")
    agents = read_yaml("05_AGENT_ORCHESTRATION_DRAFT.yaml")
    decisions = read_yaml("contracts/decisions.yaml")
    blocks = re.findall(r"```yaml\n(.*?)\n```", locate("06_WORK_BREAKDOWN.md").read_text(encoding="utf-8"), re.S)
    check("one_machine_readable_work_item_store", len(blocks) == 1)
    items = yaml.load(blocks[0], Loader=UniqueLoader)["work_items"]
    by_id = {item["id"]: item for item in items}
    check("unique_work_item_ids", len(by_id) == len(items))
    check("work_item_count", report["work_item_count"] == len(items), str(len(items)))
    check("authorized_inputs_only", report["inspected_paths"] == INPUTS)
    check("nine_requested_outputs", [Path(p).name for p in report["first_round_outputs"]] == plan["first_round_outputs"])
    for path in report["first_round_outputs"]:
        check(f"output_exists:{path}", (ROOT / path).is_file() and (ROOT / path).stat().st_size > 0)
    check("source_ids_P01_P30", [x["id"] for x in sources] == [f"P{i:02}" for i in range(1, 31)])
    source_ids = {x["id"] for x in sources}
    check("principle_source_refs", all(set(x["sources"]) <= source_ids for x in principles["principles"]))
    required = set(plan["work_item_schema"])
    for item in items:
        identity = item["id"]
        check(f"required_fields:{identity}", required <= set(item))
        for field in ("inputs", "forbidden_inputs", "files_allowed_to_modify", "deliverables", "tests", "acceptance_criteria"):
            check(f"nonempty:{identity}:{field}", isinstance(item[field], list) and bool(item[field]))
        paths = item["files_allowed_to_modify"]
        check(f"bounded_relative_whitelist:{identity}", all(
            ":" not in p and ".." not in Path(p).parts and not Path(p).is_absolute()
            and not any(c in p for c in "*?") and p not in INPUTS for p in paths))
        check(f"dependencies_exist:{identity}", set(item["dependencies"]) <= set(by_id) and identity not in item["dependencies"])
        budget = item["search_budget"]
        check(f"retry_budget:{identity}", item["max_retries"] == 2 and budget["engineering_attempts"] == 3)
        counters = [v for v in budget.values() if isinstance(v, (int, float))]
        check(f"finite_nonnegative_budget:{identity}", all(0 <= v < float("inf") for v in counters))
        check(f"no_scientific_search:{identity}", budget["scientific_candidate_trials"] == 0 and budget["sealed_submissions"] == 0)
        check(f"bounded_test_compute:{identity}", all(budget[x] > 0 for x in ("max_test_invocations", "max_total_tokens", "max_wall_seconds", "max_cpu_seconds", "max_memory_mb")))
        if identity in {f"W{i:02}" for i in range(1, 7)}:
            check(f"authorized_scope:{identity}", item["dispatch_authorization"] == "AUTHORIZED_STAGE_A")
        else:
            check(f"not_dispatched:{identity}", item["status"] == "NOT_STARTED" and item["dispatch_authorization"] == "NOT_GRANTED_THIS_ROUND")
    order = report["implementation_order"]
    check("order_exactly_all_items", len(order) == len(items) and set(order) == set(by_id))
    positions = {identity: index for index, identity in enumerate(order)}
    check("dependency_DAG_topological_order", all(positions.get(d, len(items)) < positions[item["id"]] for item in items for d in item["dependencies"]))
    all_paths = [p for item in items for p in item["files_allowed_to_modify"]]
    check("no_overlapping_write_ownership", len(all_paths) == len(set(all_paths)))
    decision_ids = set(decisions["decisions"])
    check("decision_dependencies_resolve", all(set(x["decision_dependencies"]) <= decision_ids for x in items))
    check("decision_scope_D01_D13_with_split", decision_ids == ({f"D{i:02}" for i in range(1, 14)} - {"D04"}) | {"D04A", "D04B"})
    check("single_registry", "decisions" not in report and report["decision_registry_ref"] == "contracts/decisions.yaml")
    check("pending_decisions_not_silently_approved", set(report["assumptions_needing_human_decision"]) == {k for k,d in decisions["decisions"].items() if d["status"] == "DEFERRED"})
    check("calibration_numbers_still_null", all(decisions["decisions"]["D04B"]["value"][k] is None for k in ("alpha", "sample_minimum", "bootstrap_block_length", "resamples", "CSCV_blocks", "effect_threshold")))
    check("capability_not_cross_model_penalized", evaluation["agent_capability_accounting"]["other_model_search_penalty"] is False)
    check("sealed_mock_not_benchmark_grade", env["environments"]["sealed"]["mock_is_benchmark_grade"] is False and (ROOT / "planning/SEALED_THREAT_MODEL.md").is_file())
    check("threat_model_before_W09", "TM-01 independent custodian review before W09 starts" in by_id["W09"]["prerequisite_artifacts"])
    for gap in gaps:
        check(f"gap_contract:{gap['id']}", gap["current_state"] in {"PRESENT", "PARTIAL", "ABSENT", "CONFLICT"} and gap["proposed_action"] in {"REUSE", "EXTEND", "ADAPTER", "NEW"} and bool(gap["canonical_owner"]) and bool(gap["evidence_paths"]))
        check(f"gap_work_links:{gap['id']}", bool(gap["work_items"]) and set(gap["work_items"]) <= set(by_id))
        check(f"gap_authorized_evidence:{gap['id']}", all(p.split("#")[0] in INPUTS for p in gap["evidence_paths"]))
    check("principles_H01_H15_covered", {p["id"] for p in principles["principles"]} <= {p for g in gaps if g["id"] != "C17" for p in g["principle_ids"]})
    check("gates_G0_G7_exact", [g["id"] for g in evaluation["hard_gates"]] == [g["id"] for g in principles["hard_gates"]])
    check("gates_actionable", all(all(g.get(k) for k in ("inputs", "pass", "test", "owner")) for g in evaluation["hard_gates"]))
    check("families_E0_E9_exact", [x["id"] for x in evaluation["task_families"]] == [f"E{i}" for i in range(10)])
    minimum = next(x["minimum_tasks"] for x in plan["phases"] if x["id"] == "P7")
    check("calibration_minimum_preserved", all(evaluation["calibration_minimum"][k] == v for k, v in minimum.items()) and sum(minimum.values()) == 9)
    check("nine_concrete_public_calibration_designs", len(evaluation["public_calibration_designs"]) == 9 and len({x["id"] for x in evaluation["public_calibration_designs"]}) == 9)
    check("task_contract_fields_present", {"target", "horizon", "benchmark_ref", "search_budget", "sealed_eval_id", "success_contract_ref"} <= set(env["task_contract_draft"]["required_fields"]))
    check("three_environment_boundaries", set(env["environments"]) == {"development", "sealed", "shadow"})
    check("independent_critic_and_deterministic_eval", agents["roles"]["critic"]["independent_context"] is True and agents["roles"]["evaluator"]["type"] == "deterministic_sealed_service")
    check("historical_stage_A_dispatch_baseline", agents["dispatch_authorized_this_round"] == [f"W{i:02}" for i in range(1, 7)] and agents["stop_after"] == "W06")
    check("not_production_or_stage_B", report["completion_claim"]["production_ready"] is False and report["implementation_authorization"]["stage_B_authorized"] is False)
    hashes = {p: digest(p) for p in INPUTS}
    baseline_path = ROOT / "planning" / "input_baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    check("inputs_unchanged_since_planning_baseline", {Path(p).name: h for p,h in hashes.items()} == baseline["sha256"])
    old_text = (ROOT / 'archive/planning_v0.1/06_WORK_BREAKDOWN.md').read_text(encoding='utf-8')
    old_items = yaml.load(re.search(r'```yaml\n(.*?)\n```', old_text, re.S)[1], Loader=UniqueLoader)['work_items']
    old_whitelists = {w['id']: w['files_allowed_to_modify'] for w in old_items}
    check('original_worker_whitelists_preserved', all(w['files_allowed_to_modify'] == old_whitelists[w['id']] for w in items))
    allowed_code = {p for w in items if w['id'] in {f'W{i:02}' for i in range(1,7)} for p in w['files_allowed_to_modify']}
    hotfix = read_yaml('planning/stage_a1_plan.yaml')
    check('A1_scoped_user_authorization', hotfix['authority'] == 'artifacts/stage_a1/authorized_request.txt'
          and hotfix['W07_W20_authorized'] is False and hotfix['release_self_test_added'] is False)
    extensions = {'src/quant_rsi/contracts/manifest.py', 'tests/ledger/test_provenance.py'}
    check('A1_runtime_extension_bounded', set(hotfix['runtime_files_allowed']) - allowed_code == extensions)
    check('A1_no_architecture_redesign_declared', hotfix['architecture_redesign'] is False)
    allowed_code |= extensions
    b1 = read_yaml('planning/stage_b1_plan.yaml')
    b1_ids = {'W07', 'W08', 'W09', 'W20'}
    check('B1_user_scope', {w['id'] for w in b1['work_items']} == b1_ids
          and b1['order'] == ['W07', 'W08', 'W20'])
    check('B1_engineering_not_empirical', decisions['activation']['stage_B1']['authorized'] is True
          and decisions['activation']['stage_B1']['mode'] == 'SYNTHETIC_ENGINEERING_ONLY'
          and not decisions['activation']['empirical']['authorized']
          and not decisions['activation']['shadow']['authorized'])
    check('B1_deferred_decisions_preserved', all(decisions['decisions'][k]['status'] == 'DEFERRED'
                                               for k in ('D04B', 'D11', 'D12')))
    check('B1_original_worker_whitelists', all(w['files_allowed_to_modify'] == old_whitelists[w['id']]
                                             for w in b1['work_items']))
    for w in b1['work_items']:
        allowed_code.update(w['files_allowed_to_modify'])
    check('B1_only_one_integration_extension', b1['integration_file_whitelist'] == ['tests/integration/test_stage_b1.py'])
    allowed_code.update(b1['integration_file_whitelist'])
    tm_path = ROOT / 'artifacts/stage_b1/w09_tm01_custodian_review.json'
    tm = json.loads(tm_path.read_text(encoding='utf-8'))
    check('W09_independent_TM01_artifact', tm['decision'] == 'PASS_FOR_SYNTHETIC_MOCK'
          and tm['unresolved_P0_P1'] == [])
    b2 = read_yaml('planning/stage_b2_plan.yaml')
    b2_ids = {'W10A','W11','W12','W13','W14'}
    check('B2_scoped_authorization', {w['id'] for w in b2['work_items']} == b2_ids
          and decisions['activation']['stage_B2']['authorized_work_items'] == ['W10A','W11','W12','W13','W14'])
    check('B2_W10B_deferred', b2['W10_split']['W10B'] == 'NOT_AUTHORIZED_REQUIRES_D04B_FROZEN')
    check('B2_no_empirical_or_shadow', all(decisions['decisions'][k]['status']=='DEFERRED' for k in ('D04B','D09','D11','D12'))
          and not decisions['activation']['empirical']['authorized'] and not decisions['activation']['shadow']['authorized'])
    for w in b2['work_items']:
        original_id = 'W10' if w['id'] == 'W10A' else w['id']
        extension = {'src/quant_rsi/contracts/evaluation.py'} if w['id'] == 'W11' else set()
        check('B2_bounded_whitelist:' + w['id'], set(w['files_allowed_to_modify']) == set(old_whitelists[original_id]) | extension)
        check('B2_original_attempt_and_test_limits:' + w['id'], w['max_retries'] == 2
              and w['search_budget']['engineering_attempts'] == 3
              and w['search_budget']['max_test_invocations'] == 6
              and w['search_budget']['scientific_candidate_trials'] == 0
              and w['search_budget']['sealed_submissions'] == 0)
        allowed_code.update(w['files_allowed_to_modify'])
    check('B2_only_one_integration_extension', b2['integration_file_whitelist'] == ['tests/integration/test_stage_b2.py'])
    allowed_code.update(b2['integration_file_whitelist'])
    check('B2_canonical_test_entrypoint', 'testpaths = tests' in (ROOT/'pytest.ini').read_text(encoding='utf-8'))
    actual_code = {p.relative_to(ROOT).as_posix() for prefix in ('src', 'tests') for p in (ROOT/prefix).rglob('*.py')}
    check('no_unauthorized_runtime_code', actual_code <= allowed_code)
    artifacts = report['first_round_outputs'] + ['contracts/decisions.yaml', 'planning/SEALED_THREAT_MODEL.md', "planning/validate_planning.py", "planning/input_baseline.json"]
    result = {
        "status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "planning_structure_only_NOT_runtime_or_independent_review",
        "checks_passed": sum(c["status"] == "PASS" for c in checks),
        "checks_total": len(checks), "work_items": len(items), "gaps": len(gaps),
        "input_sha256": hashes, "artifact_sha256": {p: digest(p) for p in artifacts},
        "checks": checks,
    }
    (ROOT / "artifacts/stage_b2/planning_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "checks_passed", "checks_total", "work_items", "gaps")}, ensure_ascii=False))
    for c in checks:
        if c["status"] != "PASS":
            print(c)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
