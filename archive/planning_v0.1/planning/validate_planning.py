"""Offline planning checks only. This is not a Harness runtime evaluator."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INPUTS = [
    "00_START_HERE.md", "01_LITERATURE_TO_HARNESS_TAKEAWAYS.md",
    "02_ASTRA_MASTER_TASKBOOK.md", "03_HARNESS_DESIGN_PRINCIPLES.yaml",
    "04_ASTRA_EXECUTION_PLAN.yaml", "05_SOURCE_INDEX.yaml", "06_DECISION_REGISTER.md",
]


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
    return yaml.load((ROOT / name).read_text(encoding="utf-8"), Loader=UniqueLoader)


def digest(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


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
    blocks = re.findall(r"```yaml\n(.*?)\n```", (ROOT / "06_WORK_BREAKDOWN.md").read_text(encoding="utf-8"), re.S)
    check("one_machine_readable_work_item_store", len(blocks) == 1)
    items = yaml.load(blocks[0], Loader=UniqueLoader)["work_items"]
    by_id = {item["id"]: item for item in items}
    check("unique_work_item_ids", len(by_id) == len(items))
    check("work_item_count", report["work_item_count"] == len(items), str(len(items)))
    check("authorized_inputs_only", report["inspected_paths"] == INPUTS)
    check("nine_requested_outputs", report["first_round_outputs"] == plan["first_round_outputs"])
    for path in plan["first_round_outputs"]:
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
        check(f"not_dispatched:{identity}", item["status"] == "NOT_STARTED" and item["dispatch_authorization"] == "NOT_GRANTED_THIS_ROUND")
    order = report["implementation_order"]
    check("order_exactly_all_items", len(order) == len(items) and set(order) == set(by_id))
    positions = {identity: index for index, identity in enumerate(order)}
    check("dependency_DAG_topological_order", all(positions.get(d, len(items)) < positions[item["id"]] for item in items for d in item["dependencies"]))
    all_paths = [p for item in items for p in item["files_allowed_to_modify"]]
    check("no_overlapping_write_ownership", len(all_paths) == len(set(all_paths)))
    decision_ids = {x["id"] for x in report["decisions"]}
    check("decision_dependencies_resolve", all(set(x["decision_dependencies"]) <= decision_ids for x in items))
    check("seed_decisions_preserved", {f"D{i:02}" for i in range(1, 11)} <= decision_ids)
    check("pending_decisions_not_silently_approved", set(report["assumptions_needing_human_decision"]) == {d["id"] for d in report["decisions"] if d["status"] == "USER_DECISION_PENDING"})
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
    check("no_round_one_dispatch", agents["dispatch_authorized_this_round"] is False)
    check("runtime_not_claimed", report["completion_claim"]["harness_implementation"] == "NOT_STARTED" and report["completion_claim"]["production_ready"] is False)
    hashes = {p: digest(p) for p in INPUTS}
    baseline_path = ROOT / "planning" / "input_baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    check("inputs_unchanged_since_planning_baseline", hashes == baseline["sha256"])
    artifacts = plan["first_round_outputs"] + ["planning/validate_planning.py", "planning/input_baseline.json"]
    result = {
        "status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "planning_structure_only_NOT_runtime_or_independent_review",
        "checks_passed": sum(c["status"] == "PASS" for c in checks),
        "checks_total": len(checks), "work_items": len(items), "gaps": len(gaps),
        "input_sha256": hashes, "artifact_sha256": {p: digest(p) for p in artifacts},
        "checks": checks,
    }
    (ROOT / "planning_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "checks_passed", "checks_total", "work_items", "gaps")}, ensure_ascii=False))
    for c in checks:
        if c["status"] != "PASS":
            print(c)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
