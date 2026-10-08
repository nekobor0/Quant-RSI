# Quant RSI Benchmark v0.1 — proposed specification

This proposed benchmark measures **Research Agent capability** on frozen
closed-data tasks for A-share ordinary stocks at daily frequency. It is not a
return leaderboard, Execution Agent test, open-web company research, stock
picker or live-trading workflow. Open research and qualitative company
analysis require a separate track. Stage C0 does not run or freeze tasks.

## Unit and ownership

The one machine-readable design for `BenchmarkTaskSpec` is
`BENCHMARK_TASK_SCHEMA.yaml`. It describes an assigned task's capability,
release, oracle and scoring references. TaskContract remains the sole owner of
target, horizon, benchmark, universe, decision clock, execution assumptions
and executable budget limits. BenchmarkCondition fixes comparable task/data/
cleaning/env/eval versions. DataSpec and SnapshotManifest own PIT data facts.
The design spec only refers to these objects; it cannot dispatch or override
G0–G7. `planning/STAGE_C0_BOUNDARIES.md` records the ownership review.

`CAPABILITY_MATRIX.yaml` maps E0–E8 to observable behavior and independent
oracles. E9 prospective shadow is an unscored future promotion track. The
`TASK_CATALOG_DRAFT.yaml` contains 30 design templates: 10 deterministic
traps, 7 concept-replication candidates, 10 controlled-discovery settings and
3 end-to-end tasks. Deterministic traps cover future fields/revisions,
survivorship/current membership, same-close execution, cost omission, budget
escape, fabricated evidence and hidden-feedback retry. Their correct outcome
is computed from frozen contract, timestamp, trace or ledger facts, not an
LLM judge. A rejection can count as good research behavior while a proposed
strategy remains unpromoted.

E0 contract-refusal fixtures present an invalid **inert** target, horizon or
benchmark proposal inside a separate valid frozen evaluator envelope. The
invalid proposal is never dispatched as a TaskContract. A matched valid
proposal is a positive control, so indiscriminate refusal fails. T3 adds
untradeable suspension/price-limit/T+1 orders with a frozen unfilled-order
ledger and eligible-fill control, plus distinct decay and retirement cases
with stable-effect controls. Proposed hidden E5 instances include cost,
capacity and one composite untradeable-order case containing all three
market states; E7 uses conditional-state, decay and retirement cases.

Replication candidates use only IDs in the project's `05_SOURCE_INDEX.yaml`.
The paper texts, exact procedures and A-share data have not been verified;
all seven are **concept replication candidates**. P20 comes from a
cross-market time-series setting and P17 from a relative-value strategy with
short-leg constraints, so ordinary A-share daily adaptation is especially
uncertain. Selection requires independent reference construction on frozen
data and a separate licensing/data check. No paper result is claimed here.

Each selected concept requires frozen checks for formula interpretation,
PIT feature construction, formation, rebalance, benchmark alignment,
execution assumptions and diagnostic reasoning, plus a blinded timing,
membership or execution perturbation. Matching numeric arrays alone is
insufficient.

Controlled discovery tests known-null discipline, sparse signal, correlated
variants, costs, capacity, preregistered state dependence and decoy
complexity. Generator truth, seeds, labels and exact outcomes remain with the
custodian; neutral names and separate hidden mechanisms are required to avoid
template and column-name leakage. E8 tasks ask for a traceable chain from
mechanism to evidence, with independently recomputed numbers and competing
explanations. Qualitative prose itself is not a machine score.

Before hidden admission, an independent custodian signs a mechanism-lineage
and nuisance-artifact audit, canary probes and simple fingerprint-baseline
results. A mere seed change fails the independence criterion. This audit is
a prerequisite, not evidence of Research Agent generalization.

## Development and hidden boundaries

Public development examples show formats and selected synthetic expected
outputs; public calibration tasks test format/adapters and never enter official
scores. Hidden cases require an independently protected pack and no adaptive
feedback during an open comparison cohort. The prospective set is future-only.
`HIDDEN_SET_LIFECYCLE.md` defines task/model/prompt/evaluator exposure
ledgers, quarantine, compromise and release. A leaked hidden label, seed,
oracle or generator parameter contaminates the condition; a version rename
cannot restore it. Existing W09 is mock-only, so formal G6 remains BLOCKED.

## Budget and scoring

`BENCHMARK_BUDGET_SPEC.yaml` defines a method for per-family limits, with no
numeric allowance frozen. Each model receives its own AgentBenchmarkRun and
budget root under exactly the same BenchmarkCondition. Failed attempts,
retries, changed prompts, validation calls and critic repairs are counted.
The ScientificSearchFamily is separate: it pools search ancestry only when
several candidates are jointly selected for a final scientific claim. One
model's search never penalizes another's capability score. Untrusted or
unmeasured compute makes resource comparisons unavailable, not zero.
The future supervised adapter must observe each hypothesis, feature DAG,
parameter vector, model trial, prompt revision and validation call at its
boundary, including bundled variants and failed/null outputs. Unobserved
exploration or unequal public-calibration exposure makes the comparison
`NOT_COMPARABLE`; current B2 caller-supplied reservations do not enforce this.

`BENCHMARK_SCORE_VECTOR.yaml` defines per-family reliability, replication,
discovery, falsification, economic reasoning, efficiency and generalization
dimensions with explicit denominators and missingness. There is no weighted
or implicit total. Abstaining from all tasks cannot create a capability win:
null-task false-positive rate is reported with coverage, failures and correct
negative conclusions. Assigned-task denominators are frozen before outputs,
positive controls make unjustified refusal a failure, and the public oracle
pilot must test an always-refuse baseline. No vector component can yield a
headline winner; official superiority needs a later prefrozen paired-task
uncertainty and coverage protocol. Result release waits until all paired runs
close.

Scientific-claim statistics ask whether one selected strategy has evidence;
they belong to D04B/W10B and the selected family search history. Agent
comparison statistics ask whether models differ over paired identical tasks;
they need task/family-clustered uncertainty. A strategy Sharpe p-value is not
a model capability p-value. Both protocols remain uncalibrated. Formal G4 is
BLOCKED. `D04B_CALIBRATION_GEOMETRY_PROPOSAL.yaml` lists calibration inputs
with all proposed numeric values null.

## Minimum viable suite proposal

| Tier | Public development | Public calibration | Hidden task instances | Hidden distribution |
|---|---:|---:|---:|---|
| T1 deterministic traps | 3 | 2 | 14 | E0 5 (target/horizon/benchmark refusal, budget, hidden retry), E1 9; all 10 trap types represented |
| T2 concept replication | 2 | 2 | 6 | E2 6 from the 7-candidate pool |
| T3 controlled discovery | 3 | 5 | 15 | E3–E7 3 each; ten settings covered through composite cases |
| T4 end-to-end | 1 | 0 | 3 | E8 3 distinct templates |
| **Total** | **9** | **9** | **38** | E0–E8; E9 excluded |

These are proposed counts, **not built cases or independent observations**.
The three E5 hidden instances map to cost, capacity and a composite
untradeable-order instance; the three E7 instances map to conditional state,
decay and retirement. E4 and E6 settings may share a case only when their
component oracles remain separately frozen. No count proves statistical
power; shared generator/template ancestry reduces effective N. Before
official comparison, freeze task sampling, family-specific paired uncertainty
and leave-one-template/family-out sensitivity. Report strata without an
aggregate or headline winner.
Public calibration's nine slots map to the historical W15 minimum: T1 has two
distinct leakage cases (future field and future revision); T2 has two distinct
concept-replication cases; T3 has two distinct known-null placebo fixtures,
one cost trap, one signal-decay case and one composite A-share institutional
trap (suspension, limit-lock and T+1 subcases within that single case).
These are nine separate engineering cases, not nine independent mechanisms,
and must be generated separately from hidden mechanisms. The 38 hidden instances
are a bounded pilot for three or more models, each assigned the same instances
under its own run budget. One or two tasks cannot dominate an overall count,
but they can dominate a three-task family; shared templates make effective
independence lower than 38. Therefore the pilot supports per-task/family
diagnostics, not a statistically defensible ranking. Before official model
comparison, estimate paired-difference variability and within-template
correlation from an authorized pilot, then set family-specific sample sizes
and uncertainty rules. No power value is asserted now.

Expected runtime is unknown until a fixed-adapter pilot measures per-tier
attempt and oracle cost. Planning envelope only: if T1 takes 1–3 minutes,
T2 10–30, T3 10–20 and T4 30–60 per instance, 38 tasks require roughly
314–702 minutes **per model**, or 942–2,106 serial model-minutes for three;
these are hypothetical inputs, not measured performance or frozen budgets.
Custody/review overhead is additional. Reference-oracle build effort has no
measured estimate. For resourcing only, assuming a complete independent
reference, component rubric and two-person check take 2–4 hours per T1
template, 8–16 per T2, 8–20 per T3 and 12–24 per T4, the 30-template pool
would require **192–424 engineering hours**, excluding data acquisition,
pack audit, custody and revisions. These are explicit hypothetical inputs,
not observed effort or an authorization. A separate item must re-estimate
after one prototype per tier. Required sealed assets are separate feature/label storage, generator
parameters, reference outcomes, protected counters/logs, evaluator image and
keys. Current project has none of the benchmark-grade deployment evidence.

`BENCHMARK_DATA_GEOMETRY_v0.1.yaml` gives only proposed ranges and derivation
rules. D11 data existence and D12 execution assumptions remain deferred.
`W15_W16_REDESIGN_REVIEW.md` reclassifies W15 as a nine-case Harness
calibration minimum and proposes W16A mock lifecycle versus W16B real custody.
`BENCHMARK_VERSIONING.md` prevents materially different task/data/oracle/
hidden/scoring/statistical versions from being silently ranked together.

The B2 runtime cannot execute this proposed suite: its runner permits one
independent root per condition, uses FakeProvider and one synthetic operation,
and its evaluator marks the score vector `NOT_CALIBRATED`. The separate
release/partition/hidden-pack manifests and signed comparison tuple are also
unimplemented. `W15_W16_REDESIGN_REVIEW.md` maps each dependency to a future
owner and conformance test; W15/W16 alone do not close paired comparison.

## Readiness decision

This package can be reviewed as the **specification for a calibration/data
building plan** once its independent design critic closes P0/P1 findings.
It does not authorize W10B, W15/W16 runtime, a provider, empirical data,
hidden submissions or a model leaderboard. Next authorization should be
bounded to a public task/oracle prototype and data-geometry audit, with
separate custody planning. Official benchmark comparison remains later.
