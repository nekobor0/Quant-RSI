# Benchmark v0.1 versioning — design proposal

Comparison key (all required before an official run):

`(benchmark_version, task_version, data_snapshot_version, oracle_version,
hidden_pack_version, scoring_version, statistical_protocol_version,
BenchmarkCondition.condition_hash)`.

The suite catalog owns `benchmark_version`; TaskContract owns its executable
`task_version` but has **no public-prompt field**. A proposed
BenchmarkReleaseManifest owns the public prompt reference and digest;
SnapshotManifest/DataSpec own data identity, while a proposed
BenchmarkPartitionManifest owns explicit split handles;
the independent custodian owns the oracle and hidden-pack versions; the
evaluator owns scoring and statistical-protocol versions. Hashes of the public
prompt, data snapshot, oracle implementation, scoring rules and hidden-pack
manifest accompany version labels. Labels without content digests do not
establish identity. The hidden pack uses a nonrevealing custodian handle in
public metadata; its content hash is held by the custodian.

`BenchmarkCondition.condition_hash` currently hashes only TaskContract; it
does not bind prompt, oracle, scoring or hidden pack. Before an official run,
the release custodian and independent hidden custodian must jointly sign a
BenchmarkComparisonManifest joining the condition hash to release/partition,
oracle, hidden-pack, scoring and statistical-protocol digests. The public
release tuple and prompt digest are committed **before model/prompt
registration**. Hidden-pack/oracle digests are privately committed and
attested by the custodian before the first submission. Each result carries
that signed tuple; any digest or signer mismatch is rejected and logged,
not repaired by relabeling. This manifest and verification are future work,
not current runtime behavior.

A material change to the benchmark public prompt, task definition, hidden
case, data, score rule or statistical protocol increments the corresponding
version and creates a new condition/cohort. A task prompt change changes
the release version/digest and requires a new TaskContract version or cohort
binding. An Agent's own prompt change is a separate
`AgentBenchmarkRun.prompt_hash`/budgeted prompt revision, not a suite version
change. Cosmetic wording can remain the same version only after an independent
semantic-equivalence record; no outcome-informed reclassification.

Each result retains the complete version tuple, code/runtime/dependency hashes,
exposure state, Task/Run/ScientificSearchFamily IDs and original timestamp.
Results with different material version tuples are shown in separate strata;
the interface must not silently merge, average or rank them. A bridge study
would require new preregistered matched tasks and independent authorization.
Failed attempts remain in the original tuple's lineage. A contaminated
hidden pack cannot be restored by a new label, and no released hidden outcome
can be reused as independent OOS evidence.

This is a versioning protocol draft only. No actual hidden pack, benchmark
condition or model result has been issued by Stage C0.
