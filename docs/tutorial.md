# Synthetic end-to-end tutorial

Generate the complete tutorial without credentials, network access, compute or
laboratory work:

```sh
surface-atlas tutorial tutorial
surface-atlas validate tutorial --json
surface-atlas report tutorial --output-root reports --run-id tutorial --json
```

The destination must be new. Generation builds and validates a staging atlas,
then publishes the directory atomically. Failure leaves no partial tutorial.
The Python equivalent is `surface_atlas.tutorial.create_tutorial("tutorial")`.
All fixture files are generated or copied from packaged synthetic assets, so
the installed wheel supports the same workflow. Repeated generation produces
identical file bytes. Every report page inherits the atlas's synthetic banner;
campaign and assay collections additionally declare synthetic data status.

The two reviewed synthetic queries in `tutorial-inputs/` contain six raw rows.
One repeated retained entity deduplicates to five unique entities: three retained
targets (T-EMBER, T-LANTERN, T-ORBIT), one exclusion and one unresolved entity.
The compilation saves exact hashed snapshots, source locators and a reconciled
ledger. “Complete” refers only to those two invented queries. Sequence and
action annotations enrich retained targets after compilation while the reviewed
source projections remain unchanged.

Inspect these checkpoints in the generated report:

1. The census shows 6 raw, 1 duplicate, 5 unique, 3 retained, 1 excluded and
   1 unresolved. Source snapshots and reviewed reasons are available locally.
2. Select Ember canonical residues 2–3 on Sequence sites. Downloaded FASTA is
   `CD`. Only C is mapped, at author chain A residue 10 insertion code A;
   canonical position 3 is unresolved. Inspect only that verified residue in
   3D. Author A10 without the insertion code must not be included. The optional
   synthetic partner occupies chain B. Change the target and return to verify
   that the original interval and partner selection persist.
3. Review or copy the Codex request: accession, canonical interval, explicit
   author map, selected partner identity, exact sequence and both source hashes
   must agree with the FASTA and scene.
4. Action comparison puts Ember first for payload delivery and Lantern first
   for blockade and imaging. This illustrates action-specific evidence coverage,
   not efficacy or safety. Missing Orbit observations do not become positive
   evidence. Existing screens and opportunities retain their original target IDs.
5. Campaigns contains two independent synthetic runs, each with one candidate
   and one negative control. Run one's control failed; run two and its controls
   were not run. Protocols and seeds remain distinct; scores are never pooled
   and neither candidate is promoted. Assays contains one
   synthetic censored `IC50 >100 nM` reading, a failed control and one missing
   replicate. Preserve the inequality, unit and null value. No advancement,
   binding, efficacy or clinical conclusion follows.

`expected-results.json` records the exact checkpoints. The atlas README contains
the same concise walkthrough. Research inputs are generated through
`write_synthetic_research_inputs`, then processed through the public binder and
assay importers with hashed source artifacts. No real experiment or model run
occurred; these records exercise provenance and decision limits only.

To inspect the deterministic compiler directly, call
`compile_snapshots([Path("tutorial/tutorial-inputs/query-one.json"),
Path("tutorial/tutorial-inputs/query-two.json")], "synthetic-surface-atlas")`.
`reconcile_evidence(Path("tutorial"))` checks the saved census against the exact
snapshots. The tutorial uses the ordinary validation and report APIs throughout.
