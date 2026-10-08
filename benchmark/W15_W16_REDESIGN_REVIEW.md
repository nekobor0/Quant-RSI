# W15/W16 review before implementation

The original W15 list is two replication, two placebo, two leakage, one cost,
one decay and one A-share institution trap: nine public synthetic cases. This
is a useful **Harness Calibration Minimum** for format, ledger, evaluator and
basic refusal checks. It is not a complete Agent Benchmark or a basis for
model ranking. Public calibration is exposed by design, lacks sufficient
independent tasks across E0–E8, and cannot establish generalization or
statistical power. Preserve the original historical work item; a future
authorization should rename its objective `W15A Harness Calibration Minimum`
and separately scope a task-generator/oracle pilot (`W15B` proposal) before
hidden benchmark construction. Neither is authorized here.

The proposed public calibration allocation uses T1=2 leakage cases, T2=2
concept-replication cases and T3=5 cases (two distinct null/placebo fixtures,
one cost trap, one decay case, one institutional untradeable-order case).
The institutional case may contain suspension, limit-lock and T+1 subcases,
but counts as **one** W15 case. This is the nine-case Harness minimum; it
does not establish nine independent mechanisms or official model power.

The original W16 combines a hidden synthetic release workflow with claims
that require deployed custody. Proposed split:

| Future item | Deliverable | Maximum assurance without later work |
|---|---|---|
| W16A hidden-set lifecycle/protocol | Versioned opaque pack handles, exposure-ledger contract, feedback quarantine, contamination and release tests using mock data | `SYNTHETIC_MOCK`; formal G6 stays BLOCKED |
| W16B benchmark-grade custody/deployment | Independent service identity/storage/credentials, no shared mounts/network/tool/log/error/metadata leakage, protected counters, external anchoring, independent penetration tests and custodian sign-off | May support G6 only after actual deployment evidence and threat-model review |

W16A must not put concrete hidden values, seeds or labels into the public
repository. W16B requires a separately authorized host, credentials and
custodian. A local test that a hidden fixture file is absent from the repo
cannot make G6 PASS. Both scopes retain existing W09 `SYNTHETIC_MOCK`
limitations and the compromise policy from TM-01.

Suggested future dependency order for authorization review: freeze public
task/oracle specifications and the W15A calibration contract → build public
calibration cases and independently validate them → design/generate distinct
hidden templates under W15B and W16A → audit data/PIT and benchmark versions
→ deploy W16B → only then consider official model comparison/W17. D04B, D11
and D12 require separate empirical/geometry calibration before any formal
scientific or tradability claim. Stage C0 grants none of these steps.

The present B2 Harness cannot run a paired model benchmark. In
`src/quant_rsi/orchestration/runner.py`, one condition rejects a second
independent budget root, the path uses FakeProvider and a single synthetic
daily operation. `src/quant_rsi/eval/gates.py` reports score vector
`NOT_CALIBRATED`. W15A and W16A alone therefore cannot establish
comparability. Future separately authorized implementation must meet these
dependencies before any comparable pilot:

| Gap | Proposed owner (not authorized in C0) | Required conformance evidence |
|---|---|---|
| Multiple roots for the same condition | W17A paired-run orchestration | Two distinct model roots on the same frozen comparison tuple; continuation inherits only its own root; no cross-model capability penalty |
| E0 inert proposal and E1-E8 operations | W15B task adapter and oracle pilot | Invalid stimulus never dispatched as TaskContract; each task family yields valid/refusal/failure terminals and independent oracle checks |
| Trusted search and compute receipts | W17B supervised adapter/metering | Bundled variants, renamed roots/prompts and out-of-band validation are denied or counted; failed/null output retained; unknown compute makes resource comparison unavailable |
| Score vector and assigned denominators | W17C vector evaluator | Positive controls defeat always-refuse; invalid/missing output stays in assigned denominator; no total or implicit winner |
| Signed comparison tuple and exposure | W16B custody plus W17A verifier | Mismatched tuple rejected; private pack digest signed before submissions; exposure and quarantine tested under independent identity |

These W17A/B/C labels are proposals to split the historical W17 scope in a
future authorization; they are not implementation grants or completed work.
