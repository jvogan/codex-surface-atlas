# Surface Atlas schemas v0.1

These JSON Schema documents describe the portable workspace envelopes:

- [atlas-plan.schema.json](atlas-plan.schema.json) for `atlas-plan.json`;
- [search-ledger.schema.json](search-ledger.schema.json) for `search-ledger.json`;
- [collection.schema.json](collection.schema.json) for each versioned collection file.

The optional [structure-snapshot.schema.json](structure-snapshot.schema.json)
describes a `structure_snapshot` object embedded in a structure, screening,
binder, or binder-control record. Its coordinate sources point to the record's hash-verified
artifacts; the report can expose a local 3D preview only after those files are
copied into the report. A record may use `structure_snapshots` when it has more
than one figure. The optional `sequence_artifact` is a hash-verified FASTA
reference used only to build a Codex viewer handoff.

The collection schema keeps record-specific fields open because targets, structures, interventions, molecules, and non-protein surface entities carry different evidence. Run `surface-atlas validate ATLAS_DIRECTORY` for cross-file IDs, source accounting, tier limits, artifact hashes, and other workspace-level checks.

Optional typed contracts add stricter research workflows:

- [evidence-snapshot.schema.json](evidence-snapshot.schema.json): reviewed query records for deterministic evidence intake;
- [action-evidence.schema.json](action-evidence.schema.json): source-resolved action criteria embedded on a target;
- [sequence-sites.schema.json](sequence-sites.schema.json): exact sequence, topology, PDB residue map, and partner identities;
- [binder-runs.schema.json](binder-runs.schema.json): independent design/evaluation runs, constructs, controls, lineage, and promotion;
- [assay-results.schema.json](assay-results.schema.json): returned measurements linked to exact registered constructs.

JSON Schema validates document shape. Use the CLI for checks that depend on
source bytes, residue identity, cross-file joins, or run control outcomes.
