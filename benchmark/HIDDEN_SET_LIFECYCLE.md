# Hidden set lifecycle — design proposal

The public development set exposes schemas, examples, selected synthetic
fixtures and their expected format. It is for Harness debugging only. The
public calibration set exposes task definitions and limited format feedback;
it never contributes to the formal model comparison score. A hidden evaluation
pack holds concrete cases, seeds, labels, trap placement, generator parameters
and exact reference outcomes with an independent custodian. The prospective
set is a later forward-only promotion track; E9 is unscored in v0.1.

The proposed states are `DESIGNED → GENERATED → SEALED → ADMITTED → EVALUATED
→ COHORT_CLOSED → RELEASED/RETIRED`, with `CONTAMINATED` reachable from any
state. These are lifecycle design labels, not a deployed service. The
custodian freezes the generator, oracle, data, scoring and release policy
before any candidate access. Public and hidden packs must differ in mechanisms
and data-generation artifacts, not merely in RNG seeds. A task author must
audit column names, missingness, ordering, metadata, error strings, latency,
file sizes and sample structure for oracle clues. Template-disjoint holdouts
are preferred; seed-disjoint clones alone do not demonstrate generalization.

Before any hidden pack is admitted, an independent custodian signs a private
pack audit against a previously committed public/calibration reference. The
audit records mechanism and template lineage as opaque IDs and requires
**mechanism-disjoint** hidden cases for official generalization: changing a
seed, field label or cosmetic transform does not count as a new mechanism.
If lineage cannot be established, the pack is quarantined. The custodian
compares nuisance features across exposed and hidden packs: column order,
type, scale, missingness, timestamp granularity, file size, serialization,
error text and latency. It runs canary probes for path/log/metadata leakage
and preregistered simple template/fingerprint baselines using only permitted
public inputs. Exact balance tolerances and probe thresholds require an
authorized pack prototype and are **null in C0**. A probe leak, unexplained
fingerprint separation or shared mechanism fails release and quarantines the
pack. The signed audit stores private evidence and content digests; public
records contain only attestation ID, version tuple and pass/fail state, never
hidden labels or seeds. Passing is a prerequisite, not proof of agent
generalization.

Four append-only exposure views are required: task exposure, model exposure,
prompt exposure and evaluator exposure. A record must include condition and
pack/version IDs, actor/model/prompt hash, asset category, access channel,
timestamp, allowed/denied status, feedback bytes/class and incident link.
Custodian identity/storage, credentials and raw logs remain outside the
candidate workspace. This follows `planning/SEALED_THREAT_MODEL.md`; B2 mock
is not benchmark-grade G6 evidence.

The public calibration ledger also records each model/prompt's attempts,
feedback classes, tool calls and selection lineage. A preregistered equal
calibration allowance is required for a comparable cohort; unequal or
unobserved prompt search is disclosed and the cohort is `NOT_COMPARABLE`.

During the comparison cohort, workers receive only predeclared public inputs.
Final submission is counted against both the run's frozen quota and a global
pack exposure registry. A rejected, timed-out or malformed submission is not
free. No per-task label, score, grader exception, oracle detail, hit/miss bit,
or timing signal is returned while another model can still adapt. The
custodian releases only a fixed opaque receipt until all pre-registered
models/runs close. Aggregate vector results may then be released with
suppression rules frozen before evaluation. Full hidden details remain
restricted if the pack is to be reused.

If a candidate author or benchmarked model sees a hidden label, seed, trap
placement, generator parameter or exact oracle, mark the affected condition
`CONTAMINATED`; halt further official comparisons, retain the exposure record,
quarantine results and independently investigate scope. Renaming a version or
regenerating from the same exposed template does not restore independence.
Return to evaluation requires a genuinely unexposed pack and fresh condition,
with the old failures and exposure history linked. Custodian compromise also
requires credential rotation and boundary review.

The stage C0 artifacts contain categories and opaque handles only. There are
no hidden seeds, labels, actual packs, independent credentials or sealed runs
in this repository.
