# Planning

`v0.2/` 是当前八份规划交付物；`SEALED_THREAT_MODEL.md` 是 W09 前置规范；`KERNEL_BOUNDARY.md` 说明 Stage A 实现边界。

`validate_planning.py` 检查规划一致性；`run_stage_checks.py` 捕获测试命令、退出码和产物摘要。二者均为工程验证工具，不是 W11 evaluator 或 W14 orchestrator。

Stage A.1 的限定授权见 `stage_a1_plan.yaml`；ownership 修订见 `STAGE_A1_OWNERSHIP.md`。当前 planning validator 输出到 `artifacts/stage_a1/planning_validation.json`，此前 Stage A 输出保留。

Stage B1 当前授权及状态见 `stage_b1_plan.yaml`；工程边界和 replay assurance 见 `STAGE_B1_BOUNDARIES.md`。当前 planning validator 输出 `artifacts/stage_b1/planning_validation.json`，A/A.1 历史产物不覆盖。
