# Stage A.1 contract/provenance amendment

This is a bounded correction to W01鈥揥06. It does not authorize W07鈥揥20,
Stage B1, a release self-test, real model benchmarks or statistical calibration.
The authorized request is preserved in `artifacts/stage_a1/authorized_request.txt`.

## Owners

| Fact | Canonical owner | Consumers |
| --- | --- | --- |
| Current governance permission | `contracts/decisions.yaml` | `TaskContract.authorize_dispatch`, every new reservation |
| Historical governance | Content-addressed `DECISION_SNAPSHOT` trace event | Task snapshot ref/hash/version; `verify_frozen_condition` |
| Research preregistration | `EXPERIMENT_REGISTERED` immutable ExperimentSpec | Attempt, Candidate, Evidence |
| Actual start, terminal status, usage | ResearchTrace events | Read-only projections; no writable Attempt status object |
| Attempt output attribution | `ATTEMPT_OUTPUT` event | Candidate ID/attempt/ref/hash; settlement preserves artifact hashes |
| Agent identity/code/prompt/dependencies | Immutable AgentBenchmarkRun in trace | RunManifest references run ID/digest |
| Task/data/cleaning/split/env/eval/cost/budget versions | TaskContract and its referenced DataSpec/SnapshotManifest | Manifest references canonical objects, not duplicate policy values |
| Runtime/tool identity and randomness declaration | RunManifest | Future W20; no replay execution implemented here |

The snapshot is a frozen copy of a historical registry, never a writable current
registry. Its `sha256:<digest>` reference identifies canonical JSON content.
Byte hashes and local trace anchors establish integrity, not independent custody.
Registry updates cannot substitute for a Task's historical snapshot. Conversely,
successful historical verification cannot authorize a new dispatch. A compatible
registry version upgrade does not change historical condition hashes or budget roots.

## Execution and evidence

ExperimentSpec retains `execution_started_at` only for legacy decoding. Registration
still rejects a populated field; lineage verification never uses it as proof of
execution. New artifacts use unchanged preregistrations and explicit Candidate
`attempt_id`. Existing Stage A artifacts are preserved without rewriting history.
Legacy Tasks missing snapshot metadata cannot claim verified historical provenance;
they are decodable, but no current registry is silently substituted.

`record_output` atomically binds exactly one candidate ID and artifact to an open scientific Attempt. Identical output retries are idempotent; a second distinct Candidate requires a separately counted Attempt.
Successful execution may produce negative measured results: `SCIENTIFIC_FAILURE`
is a scientific result, with execution status `SUCCEEDED`, and does not qualify
for an infrastructure retry. `FAILED`, `ABORTED`, `TIMEOUT`, `CANCELLED` and
`UNKNOWN_TERMINATION` preserve attempts and diagnostic outputs. They cannot support
measured strategy evidence. Diagnostic Candidates use `FAILURE_DIAGNOSTIC` and
Evidence uses `INFRASTRUCTURE_FAILURE`, with strategy metrics unknown/null.
Partial strategy artifacts from interrupted attempts remain in the trace but are
not admissible as successful Candidates. Unknown usage blocks dispatch as before.

This minimum contract uses one source artifact per Candidate/Evidence. Evidence
source ref/hash must match the attributed Candidate output. Multiple evidence
objects can refer to the same candidate artifact. It does not infer metric truth
from a digest or certify the contents of a result file.

## RunManifest

The manifest binds the task, condition, run, data, snapshot, candidates, evidence,
input/output byte hashes, and relevant trace-event hashes. Referenced Task and Run
objects retain canonical model and policy facts. Model/provider versions may be
unknown/null; provider returned metadata is optional immutable JSON, never guessed.
Future per-call provider receipts require append-only provenance at the adapter
boundary; no real adapter or call exists in this stage.

A draft manifest may be assembled after output and before settlement. It cannot
pass completed-run verification. After settlement a separate completed manifest
identity/digest must bind the terminal event ID and hash; the manifest stores no
status. Verification uses the full trace and compares actual resolved artifact
bytes. It does not reread today's registry to validate historical provenance.
Missing refs, mismatched hashes, and unresolved attempts fail closed.

Randomness is explicitly `fixed_seed_deterministic`,
`externally_nondeterministic`, or `provider_randomness_unknown`. A declaration
records provenance; it is not proof that a provider will replay deterministically.
Unknown/external randomness cannot acquire a fabricated fixed seed.

Stage B1 remains a proposal requiring new authorization. W20 replay execution,
W07 PIT, W08 simulation, and W09 isolation are not implemented by this amendment.
