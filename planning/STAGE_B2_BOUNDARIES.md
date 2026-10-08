# Stage B2 integration boundaries

Engineering conformance can pass; formal research verdict remains BLOCKED.
All G0-G7 required; G4 D04B_NOT_FROZEN and G6
BENCHMARK_GRADE_SEALED_INFRASTRUCTURE_ABSENT cannot be disabled by callers.
No empirical tradability or statistical promotion. No real provider/market data.

Canonical contracts and SearchBudget/TraceStore remain unchanged. New EvalResult
is owned only by contracts/evaluation.py, computed by eval/gates.py. The caller
cannot supply gate results to the gate engine. Evaluator artifact is its source
digest; attestation is UNSIGNED_SYNTHETIC, never a production signature.

W12 API: immutable WorkerRequest and WorkerResponse, FakeProvider only.
invoke(request, provider, *, budget, attempt_id) requires an already recorded
ATTEMPT_STARTED, matching canonical run/model/prompt/input identity, and no
terminal event. It does not reserve or settle. Coordinator owns those calls to
the existing budget service. Worker response provenance is appended to the
existing trace. Unknown usage is None; supervisor measurements stay None unless
actually measured. No implicit retries or replacement budget roots.

W13 API: ReviewIdentity(actor_id, context_id, run_id, role), Issue, CriticReport;
review(candidate, evidence, *, author, critic, issues=()) and
admit(report, candidate, evidence, *, author, critic). Identities and exact
candidate/evidence digests bind reports. Same actor/context/run and author role
are denied. All admitted evidence must be explicitly reviewed. No hidden data
or evaluator writes; report identity is trusted-supervisor protocol, not OS auth.

W14 composes a frozen synthetic daily operation: fake response carries that
same frozen operation; W08 produces the candidate artifact; W20 reproduces it.
No Agent search. Only the existing engineering-fixture accounting exception is
used. Single-flight/idempotency is recorded in the canonical trace, not a second
state database. Terminal worker accounting must precede measured Evidence and
completed RunManifest under A1 invariants. Therefore evaluator runs after worker
settlement and a completed execution manifest; its result/dispatch completion
are appended afterward. This is an intentional topological refinement of the
user's suggested flow, not a change to Attempt or manifest ownership. Completed
manifest freezes original referenced events; later audit events never overwrite it.

Only supported frozen local code/runtime can replay. No arbitrary code execution.
G1 is independently recomputed from PIT records and order decision times; G5
checks the frozen synthetic ledger/timing/cost bridge. W10A returns computation
results only and is not an input capable of overriding G4.

Budgets retain original 3 attempts / 2 repairs / 6 test invocations per work item;
initial worker verification should use at most 2 invocations to reserve review
and final regression capacity. Every failure is retained; no budget reset.

Independent-review corrections: evaluator admission must match the single
canonical ADMISSION_GRANTED event for that attempt, including manifest,
candidate/evidence digests and the stored critic report bytes. B2 supports no
same-attempt admission supersession: a blocked report remains blocked and a new
candidate requires a new counted attempt. Caller-supplied clean reviews cannot
replace that decision. Review/admission events follow the execution manifest;
their immutable trace binding is checked separately without rewriting it.

Post-settlement persistence/evaluation failures produce DELIVERY_FAILED and a
FAILED archive with partial artifact references. Successful compute settlement
is retained. Redelivery returns the archived failure without another attempt.
Storage failure preventing trace writes remains a custodian recovery boundary.

G3 uses the canonical effective terminal projection, retaining the original
UNKNOWN failure and any USAGE_RECONCILED evidence. Reconciliation is a trusted
supervisor declaration; it never changes unknown provider-reported usage.

Authorization is checked before claiming and again after reservation immediately
before worker binding/invocation. A failed second check preserves a failed
reservation with unknown actual resources and blocks redispatch pending trusted
reconciliation. No atomic cross-process/OS-level revocation guarantee is claimed.
