# Binder run intake

`binder-runs.json` records independent computational runs under
`codex-surface-binder-run-collection/v0.1`. Intake is local, uses the Python
standard library, and never invokes generators, predicts structures, runs
experiments, or changes a recorded promotion decision.

The collection declares `atlas_id`, `data_status` (`research` or explicitly
`synthetic`), and a nonempty `records` array. Each run retains its `run_id`,
`campaign_id`, exact `target_id`, source-backed `target_construct`, generator
name/version/seed, evaluation protocol ID/version, stages, controls status,
and candidates. A generator seed may be null only with a `seed_gap`. Evaluation
observations preserve integer seeds individually. Failed observations and
unrun stages remain present. Metrics are finite numbers or null; failed and
unrun observations have empty metric objects.

Each candidate carries a run-local `candidate_id`, role (`candidate`,
`positive-control`, `negative-control`), stable construct ID, complete uppercase
amino-acid sequence and its SHA-256, description, nonsequence modifications,
source, lineage, observations, and source-backed promotion decision/rationale.
The hash is over the exact uppercase ASCII sequence without FASTA headers or
whitespace. Tags and protein fusions belong in the sequence; nonsequence
modifications belong in `modifications`. Unknown/ambiguous amino acids remain
literal X/B/Z/U/O and are not imputed. This contract rejects missing sequences.

Lineage contains parent run ID, candidate ID, sequence hash and source. Known
parents must match; cycles fail validation. External parents remain referenced
source records, not inferred resolved candidates. A reused construct ID cannot
change its sequence or modifications. Candidate identity is scoped to its run;
the same display ID in two runs is never used to combine observations.

Control records include an acceptance rule and acceptance status. A failed
control forces the run's `controls_status` to `failed`. A run cannot report
passed controls without explicit passed control records. Promotion requires
passed controls and scored observations, but those conditions never trigger
automatic promotion. Intake preserves the supplied decision. It does not
evaluate whether acceptance rules are scientifically adequate.

## Portable import

```python
from surface_atlas.research_intake import import_binder_runs

collection = import_binder_runs(
    ["run-a/binder-runs.json", "run-b/binder-runs.json"],
    atlas_directory="atlas",
    output="new-binder-bundle",
)
```

The atlas supplies `atlas-plan.json` and `targets.json`. Each input's artifacts
resolve relative to that input file's directory. Output must be a new directory.
The importer validates bytes and SHA-256, copies supporting artifacts into
`research-artifacts/<sha256>/<filename>`, rewrites references, validates the
portable result, then publishes `binder-runs.json` and its artifacts together.
It rejects duplicate run IDs and mixed synthetic/research collections. It does
not average scores, rank across protocols, collapse controls, or infer missing
seeds/stages.

Copy the resulting collection and `research-artifacts` tree together into an
atlas when ready to incorporate them. Preserve any existing collection until
you have explicitly combined all desired runs; do not replace it with a partial
import. An import bundle is not itself a complete atlas. Existing supporting
artifacts are content addressed; validate the destination atlas after copying.
`output=None` performs validation and returns a collection without writing;
its artifact references still belong to the separate input roots and it must
not be saved as a portable bundle.

`validate_optional_research(root, atlas_id, targets=None)` returns a list of
validation errors. `validate_binder_runs(collection, artifact_root, atlas_id,
target_ids)` raises `IntakeError` on invalid strict data.
`render_campaigns(collection)` returns an escaped HTML fragment that keeps runs
separate and exposes full source details. Synthetic collections receive a
prominent test-data banner.

## Legacy collections

The optional historical `binders.json`, `binder-controls.json`,
`designed-binders.json`, and `binder-results.json` collection identifiers are
checked along with target IDs, sequence hashes, declared files and observation
identity joins. The reviewed bundled research example remains readable.
This conservative compatibility path does not manufacture generator metadata,
construct identity, unrecorded seeds, or controls. Legacy records are not
silently upgraded into strict runs and cannot serve as the identity registry
for assay intake. Convert them only from their original, source-backed records.
The loader's additional `designs.json` and JSON files beneath `binders/` or
`designs/` must also be registered collections. Raw singleton candidates,
malformed JSON and broken or escaping symlinks fail validation instead of
silently disappearing. Nested top-level control arrays receive the same
sequence, target and artifact checks as candidates.

The [JSON Schema](../schemas/v0.1/binder-runs.schema.json) describes shape.
Runtime validation additionally checks identities, joins, controls, finite
metrics, paths and actual file integrity. Source locators are retained verbatim;
their presence and artifact integrity do not prove source interpretation or
scientific validity.
