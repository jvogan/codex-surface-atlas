# Installed local research workflows

The installed CLI runs these workflows without provider calls. Use separately
installed source plugins, modeling companions, and experiment tools when work
requires retrieval or execution. Preserve the user's scope and authorization.

## Reproduce the complete example

```bash
surface-atlas tutorial NEW_ATLAS --json
surface-atlas validate NEW_ATLAS --json
surface-atlas report NEW_ATLAS --output-root REPORTS --run-id tutorial --json
```

This fixture is entirely synthetic. Its README and expected-results.json give
the source queries, raw and reconciled counts, exclusion and unresolved cases,
sequence and coordinate hashes, action-dependent comparisons, control failures,
and assay-return checks. Never use its invented observations as evidence.

## Compile reviewed source records

```bash
surface-atlas ingest-evidence SNAPSHOT_JSON [SNAPSHOT_JSON ...] \
  --atlas BASE_ATLAS --output NEW_ATLAS --json
surface-atlas reconcile-evidence NEW_ATLAS --json
```

Use the `codex-surface-evidence-snapshot/v0.1` contract for local query snapshots.
Record source/query identity, query text, retrieval time, redistribution terms,
status and limitations. Each discovered entity needs stable identifiers and an
explicit reviewed retained, excluded, or unresolved disposition. Retention needs
surface-evidence reasoning; RNA abundance alone is insufficient. Intake preserves
raw file hashes and joins only supplied identities. Conflicting dispositions
remain unresolved. Add later target annotations without modifying source-derived
fields. Refresh source queries into new snapshots and a new atlas.

## Use the report's built-in comparisons

Populate target `action_evidence` with cited supported, contradicted, or unknown
observations. Compare actions counts support for the selected payload-delivery,
blockade, or imaging criteria; it does not estimate clinical utility. Missing
criteria remain missing. Read the source basis and the next measurement that
would change the count and decision.

Populate `sequence_sites` with exact accession/isoform, sequence hash,
extracellular intervals, canonical-to-author residue mapping, insertion codes,
unresolved positions, partner identity, and a hashed PDB file. The validator
checks residues against the coordinates. Select an interval to preview exactly
those mapped residues, download its FASTA, or copy a portable Codex request.
Keep unmapped residues unresolved; do not guess a mapping from shared numbers.

## Register returned runs and measurements

```bash
surface-atlas import-binder-runs RUN_JSON [RUN_JSON ...] \
  --atlas ATLAS --output NEW_BUNDLE --json
surface-atlas import-assays ASSAY_JSON \
  --atlas ATLAS --output NEW_ASSAY_BUNDLE --json
```

Omit `--output` for validation only. Add a complete bundle to a copy of the atlas
and validate before reporting. Preserve independent run IDs, generator and
evaluator versions, actual seeds or explicit seed gaps, exact constructs,
lineage, observations, controls, and promotion reasons. Never pool scores across
unmatched methods. Failed or unrun stages remain visible.

Assay returns join the exact registered run, candidate, and target constructs.
Keep endpoint, units, inequalities, conditions, each replicate, missing values,
controls, and source locators. A returned observation does not promote a candidate
or establish safety or efficacy. Computational scores cannot be imported as
laboratory measurements. The tutorial's assay is a schema demonstration only.

Full contracts and examples are documented in the
[project documentation](https://github.com/jvogan/codex-surface-atlas/tree/main/docs)
and the installed versioned schemas.
