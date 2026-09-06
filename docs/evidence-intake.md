# Intake reviewed evidence snapshots

Evidence retrieval and evidence reconciliation are separate steps. Retrieve
records with an appropriate source tool, then prepare a reviewed local JSON
snapshot identifying the source, query, stable entity identities, and explicit
dispositions. Intake does not search databases, call models, infer identity
from similar names, or promote RNA expression to cell-surface protein evidence.

From an initialized atlas, create a new workspace with the supplied snapshots:

```bash
surface-atlas ingest-evidence source-one.json source-two.json \
  --atlas atlas-base --output atlas-reviewed --json
surface-atlas reconcile-evidence atlas-reviewed --json
surface-atlas validate atlas-reviewed --json
```

The output must be a new directory outside the base atlas. Intake copies the
base workspace, stores the exact snapshot bytes under content-addressed
`evidence/snapshots/` paths, writes the normalized collections and search ledger,
and validates the result before publishing the directory. The base is not
modified. Symlinks and special files in the base are rejected. Workspaces with
machine-local artifact roots must first be materialized into portable files.
A failed intake removes its temporary staging directory.

## Source snapshot contract

Use the [snapshot schema](../schemas/v0.1/evidence-snapshot.schema.json). The
small example below is invented software test data, not biological evidence:

```json
{
  "schema_version": "codex-surface-evidence-snapshot/v0.1",
  "data_kind": "synthetic",
  "source": {
    "source_id": "S-DEMO",
    "query_id": "Q-DEMO",
    "title": "Invented assay fixture",
    "query": "Demonstration query",
    "source_class": "synthetic-assay",
    "retrieved_at": "2026-09-01T12:00:00Z",
    "license": "Synthetic fixture",
    "status": "complete"
  },
  "records": [
    {
      "record_id": "R-DEMO",
      "entity_id": "E-DEMO",
      "preferred_name": "Invented target",
      "identifiers": {"fixture": "E-DEMO"},
      "reason": "Explicit synthetic reviewer disposition.",
      "locator": "Invented panel A",
      "disposition": "surface-target",
      "target": {
        "target_id": "T-DEMO",
        "preferred_name": "Invented target",
        "structure_tier": "retained-unmodeled",
        "surface_evidence": {
          "state": "synthetic-positive",
          "basis": "Invented intact-cell protein observation for software tests."
        }
      }
    }
  ]
}
```

`data_kind` is either `synthetic` or `public-source`. Public snapshots require
an HTTP(S) `source.url` without embedded credentials. Synthetic and public
snapshots cannot be mixed in one intake. Synthetic inputs require an explicitly
synthetic atlas plan; a synthetic plan cannot receive public-source intake.

Each source requires `source_id`, `query_id`, `title`, `query`, `source_class`,
a timezone-aware `retrieved_at`, `license`, and `status`. Status is `complete`,
`partial`, or `blocked`; the latter two require a nonempty `limitation`.
Optional source fields are `url` and `limitation`. Query IDs must be unique
across snapshots. The source ID may recur for distinct queries against the
same source. Source text, retrieval scope, and redistribution rights still
need human review; a license string alone does not establish permission.

Each record requires its unique source-local `record_id`, stable `entity_id`,
`preferred_name`, a nonempty `identifiers` map, review `reason`, source `locator`,
and `disposition`. IDs use portable letters, digits, dots, underscores, colons,
and hyphens, beginning with a letter or digit. Retained records use
`surface-target` and require a `target` projection with an exact `target_id`,
explicit structure tier, and a nonempty `surface_evidence.basis`. A structure
is not required: use `retained-unmodeled` when appropriate. Other dispositions
are `excluded-from-surface-universe` and `unresolved`; they must not include a
target projection.

The intake checks that a surface basis is explicitly supplied. It cannot
verify the scientific claim inside that text. Record the original assay and
context faithfully; do not substitute RNA observations for demonstrated
surface display. Target projections may carry other valid atlas annotations.
Extra fields outside the target projection are rejected. Duplicate JSON keys,
nonfinite numbers (including numeric overflow), malformed JSON, and snapshots
over 16 MiB fail intake.

## Identity and counts

Normalization groups only by the supplied exact `entity_id`. No fuzzy name,
gene-symbol, or isoform matching occurs. A stable namespace/identifier pair
cannot belong to multiple entities; an entity cannot carry conflicting IDs
within one namespace. Retained projections of one entity must agree, and
different entities cannot share a target ID. Resolve identity conflicts in the
reviewed inputs before intake. Conflicting dispositions for the same entity
become unresolved, preserving all source references and reasons.

The ledger reports:

- **Raw records:** every input record across supplied queries.
- **Duplicate records:** raw count minus the number of normalized entities;
  repeated observations remain preserved in source references.
- **Normalized discovered entities:** exact grouped entity count.
- **Surface targets, excluded entities, unresolved entities:** the three
  mutually exclusive dispositions of the normalized census.

All supplied queries marked complete produce
`complete_within_recorded_scope`. A partial or blocked query produces `partial`.
This is completeness within the recorded queries only, never completeness of
all biological evidence or all possible targets. The ledger retains each query,
status, limitation, and exact source artifact. `as_of` is the UTC date of the
latest recorded retrieval instant.

## Reconcile without rewriting provenance

Reconciliation verifies snapshot checksums, byte lengths, canonical artifact
paths, normalized projections, and source-derived ledger metadata. A missing
snapshot, altered source field, identity mismatch, or false coverage claim is
an error. Later annotations may be added to targets, including action evidence
or sequence/site mappings, as long as every source-derived field is preserved.
Replacing or removing an original field is not additive enrichment.

If only counts are stale, inspect the reported changes and optionally write a
new ledger file:

```bash
surface-atlas reconcile-evidence atlas-reviewed \
  --output reconciled-search-ledger.json --json
```

The original ledger is not modified and the destination must not exist. The
new ledger contains corrected counts; reconciliation does not silently rewrite
source projections or source coverage. A reported `consistent: false` describes
the input ledger, even when a corrected copy has been written.

Managed intake is recognized from its ledger marker, snapshot directory, or
snapshot references in collections. Removing one marker or source artifact
field does not downgrade verification to a legacy count-only check. This is
integrity checking against the supplied local snapshots, not authentication
against an external authority: someone able to replace all inputs and their
hashes can create a different dataset. Preserve a separately reviewed export
policy when distributing the workspace.

For older workspaces without managed snapshots, reconciliation checks available
collection counts only. It cannot independently reconstruct raw source records
or certify search completeness. Do not interpret a legacy count check as a
source-backed evidence audit.
