# Budget & Gate Policy v1 — risk-tiered execution authority

Status: **ACTIVE** (supersedes the uniform single-shot authorization regime)
Authority: direct user instruction, 2026-10-08 — "授权直接执行"; adopted from the
independent audit review that identified goal displacement.

## Why this exists

The project reached a state where the governance machinery built to protect
benchmark credibility had become the main body of work. Evidence at the
2026-10-08 cutoff:

- ~2,300 files under `artifacts/`, of which **870** sat in a single
  `cal05_preparation/` directory, against **8** files in the actual execution
  directory for that same query.
- One full acceptance report per single-row API response.
- **22** forced authorization prompts, **>=6** user-granted budget overrides for
  exhausted frozen budgets, **>=11** hard quota cut-offs mid-task.
- Five consecutive qualification rounds (QV3–QV7) to make one *offline synthetic*
  suite pass; the user personally terminated the loop.
- After the user's 2026-10-08 reform, **four real pilots completed in one day**.
  Capability was never the binding constraint. Process was.

The fix is **not** to lower scientific standards. It is to stop applying
publication-grade gates to ordinary software engineering.

## 1. Three separate ledgers

A single uniform budget regime is the root defect. Retrying a unit test and
publishing a statistically significant strategy claim are not the same class of
act and must not share one authorization path.

| Ledger | Governs | Authority model | Counting |
|---|---|---|---|
| **Engineering Budget** | building, refactoring, fixing, re-running tests and offline suites within one frozen task version | **self-service inside declared caps** — no per-run human authorization | `retries` counted in trace; `candidate_trials` stays 0 |
| **Data Acquisition Budget** | real vendor/network calls against already-authorized endpoints and scopes | **one authorization per batch**, with per-request caps and a hard ceiling enforced by code | `validation_queries` counted; never refunded |
| **Scientific Search Budget** | any factor/parameter/hypothesis variant whose result could enter a scientific claim | **strict**: pre-registered, individually counted, append-only, no reset via rename or restart | `candidate_trials`, `factor_variants`, `parameter_trials`, `hypotheses_seen` counted |

Rules:

1. **Engineering retries never increment scientific counters.** An engineering
   retry is `retry_of` with `candidate_trials = 0` and no
   `scientific_variant_id`. The existing `SearchBudget.reserve()` already
   enforces exactly this; this policy states that such retries need no new human
   authorization while inside the declared engineering cap.
2. **A batch authorization replaces per-call authorization.** One approval may
   cover N declared requests against frozen endpoints, parameters and storage
   ceilings. The runner enforces N and stops.
3. **A failed engineering step is an engineering event, not an audit event.**
   Record it, fix it, re-run it. Do not open a round of forensics to explain it
   unless the failure is on the scientific critical path *and* unexplained.
4. **Budget exhaustion always produces a denial event.** Never widen a cap
   silently; never refund a search counter.
5. **Engineering Budget never widens scientific authority.** Clearing the
   engineering ledger grants no scientific claim and does not move D11/D12/D04B.

## 2. Risk tiers — match the gate to the risk, not to the ceremony

| # | Act | Required gate |
|---|---|---|
| R0 | edit a fixture, refactor code, re-run a unit/offline suite | automated tests + trace; **no human authorization** |
| R1 | real vendor call inside an already-authorized endpoint, scope and batch | batch authorization + credential protection + request log + integrity check; **no per-call approval** |
| R2 | obtain data from a **new** source, or extend scope/params/rows | explicit human authorization for that source and scope |
| R3 | publish a scientific claim (PIT-correct, backtest-credible, tradable alpha, model ranking) | full PIT + statistical protocol + multiple-testing control + independent evaluation + sealed OOS |

R3 is **unchanged** from the original frozen design. Nothing in this policy
relaxes it. The original `empirical.requires_frozen: [D04B, D11, D12]` remains
in force for R3 claims.

## 3. Dual-track qualification (replaces "lower D11")

D11 is **not** lowered to unblock development. It is **split by purpose**.

**Track A — Agent Capability Evaluation.** Measures a Research Agent's research
process: tool use, data handling, anomaly detection, evidence organization,
refusal quality. May use synthetic fixtures, frozen snapshots and public
instances with deterministic oracles. Real model comparison is allowed here.

> Every Track A result MUST be labelled `PUBLIC` / `UNSEALED` / `PROVISIONAL`.
> Track A may **never** be cited as PIT-correct, as tradable alpha, as a strategy
> validity result, or as a formal model ranking.

**Track B — Empirical Scientific Qualification.** Keeps the original D11, D12,
D04B and sealed requirements, for claims that bear on strategy economics or
historical tradability.

**Data qualification levels** (a level is a declared scope, *not* a renamed pass):

| Level | Data requirement | Permitted use |
|---|---|---|
| L0 | synthetic, deterministic ground truth | tool/agent logic, anomaly detection, early model comparison |
| L1 | frozen vendor snapshot, documented field semantics, declared `available_at` limits | Agent capability comparison, explicitly non-PIT |
| L2 | partial independent Oracle, event timing, known revision risk | scoped historical research and diagnostics |
| L3 | PIT, versioned, statistical and cost requirements met for the task | formal empirical evaluation |

L1 is **not** "D11 PASS". Promotion from L1 to L3 requires a versioned decision,
not a relabelling.

## 4. Standing priority rule

> Apart from credential safety, data compliance and irreversible risk, every new
> governance or infrastructure work item must name the **specific Agent
> evaluation task it blocks**. Work that cannot name one does not enter the near
> critical path.

This rule exists to prevent recurrence of the observed pattern, and is why the
next deliverable is a running comparison rather than another data-source pilot.

## 5. Independence — name which kind

"Independent review" is currently ambiguous and multiplies cost without clearly
multiplying independence. Three distinct properties must be labelled separately:

- **Identity independence** — different model/account instance (D08).
- **Evidence independence** — review of raw receipts, not of a summary report.
- **Outcome independence** — reviewer did not produce the artefact.

A verdict may claim only the properties it actually holds. A pre-written verdict
pasted in by a third party is evidence-independent at most.

## 6. Evidence retention — discard vs. non-admission

Retaining and admitting are different acts.

- A response that cannot be verified is **not admitted** to any qualified
  dataset, and must be labelled non-admitted.
- Its **failure metadata and any retainable raw bytes are preserved** under the
  append-only rule, unless retention is barred by credential, licence or
  confidentiality limits.
- Deleting obtainable raw evidence is not a virtue; declining to promote it is.

## 7. Version control

Git now versions source, contracts, tests, policy and curated docs
(`.gitignore` in the repo root). **Excluded**: credentials, restricted vendor
raw data, run caches, bulk historical run evidence.

Git does **not** replace raw-evidence SHA-256 receipts, DACL protection, or the
append-only trace. Git history is rewritable; protected branches and immutable
external archives carry the durability guarantee.

## 8. What is explicitly unchanged

- D06: hard gates + score vector, **no single total score**.
- D08: independent critic context; no self-review.
- D10: no live automatic orders, ever.
- D13: fully independent project.
- Correctly refusing a bad strategy can score highly as Agent capability and
  still grants the strategy **no** economic validity.
- Synthetic or mock isolation is never benchmark-grade sealed evaluation.
