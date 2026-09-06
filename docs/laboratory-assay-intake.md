# Laboratory assay returns

`assay-results.json` uses `codex-surface-assay-result-collection/v0.1` for
source-backed results on constructs registered in strict `binder-runs.json`.
Each record identifies one experiment, candidate run, candidate, target,
construct pair and endpoint. This path imports existing files only; it does
not submit or execute an experiment, establish biological activity from a
prediction, or promote a binder.

## Identity before attribution

The importer resolves the exact `(candidate_run_id, candidate_id)` pair and
checks campaign and target identity. Both assayed constructs require the full
sequence, SHA-256, stable construct ID, description, modifications and source.
Candidate and target construct IDs, sequence hashes and modifications must
match the registered run exactly. `identity_source` records the source artifact
and locator documenting attribution. The original generation record stays
computational even when laboratory records are added.

This initial importer intentionally rejects unknown construct identity and
modified constructs. Register a distinct, source-backed construct/run with
appropriate lineage before importing a tagged, mutated or otherwise different
reagent. Never edit an existing construct's sequence just to make a laboratory
return join. The target ID is checked against `targets.json`; the actual target
construct identity is checked against the run, not inferred from a gene symbol
or a canonical sequence accession.

## Measurement semantics

The `method` records a physical laboratory assay family, exact name, version,
conditions and source. Preserve the reported buffer, temperature, concentrations,
immobilization/orientation, fitting model, cell system and endpoint definition
in conditions; state omissions explicitly. Supported families are SPR, BLI,
ITC, MST, ELISA, radioligand, cell-assay, and other-laboratory-assay. The last
requires a specific method name and conditions. The current endpoint/unit
allowlist is deliberately narrow:

| Endpoint | Accepted source units |
| --- | --- |
| KD, IC50, EC50 | M, mM, uM, µM, nM, pM, fM |
| kon | M^-1 s^-1 |
| koff | s^-1 |
| response | RU, nm, %, 1, RFU, RLU, OD |

The importer performs no unit conversion and never converts IC50/EC50 into KD.
Unsupported units or endpoints require an explicit contract extension instead
of a guessed mapping. Physical assay family labels and file hashes cannot prove
that a submitted record was experimentally measured; source review remains
necessary.

`reading.status` is `measured`, `not-measured`, `failed`, or `inconclusive`.
A measured reading contains finite numeric `value`, `unit`, and literal relation
`=`, `<`, `<=`, `>`, or `>=`. An inequality stores its reported bound; it does
not become a point estimate. Zero stays zero. A missing, failed or inconclusive
reading has explicit null value/relation and a reason. A qualitative result
without a numeric bound remains in the reason and source, with null numeric
fields. A prediction score is not an accepted endpoint.

Replicates preserve their individual reading and failure, stable replicate ID,
biological sample ID and technical replicate ID (explicit null when unknown).
Unreported replicate details use `replicates: null` plus `replicate_gap`.
Control records preserve role, description, acceptance rule, acceptance status,
source, and optional `result_record_id`. Links must resolve within the same
experiment; a control cannot link to the enclosing result itself. Missing
control details use `controls: null` plus `control_gap`, never a passed status.
A numerical reading is retained alongside any failed control.

`aggregation` is null when unreported, otherwise a source-backed description
with biological sample and technical reading counts (explicit null for unknown
counts). Intake neither recomputes aggregates nor infers independent experiments
from wells. Record reported uncertainty, exclusions and fitting details in the
aggregation description. Source locators are required and retained, but their
semantic accuracy and the reported aggregation arithmetic require source review.

## Import and display

```python
from surface_atlas.research_intake import import_assays

collection = import_assays(
    "lab-return/assay-results.json",
    atlas_directory="atlas-with-binder-runs",
    output="new-assay-bundle",
)
```

The new bundle contains `assay-results.json` and the copied, hash-verified
`research-artifacts` tree. Copy both into the intended atlas, retaining any
existing assay collection until an explicit combined collection has been
validated. Relative paths, byte counts and hashes are verified against actual
files. Absolute paths, traversal, escaping symlinks, duplicate JSON keys,
non-finite numbers and mismatched identities fail intake. Existing outputs are
never silently overwritten. Without `output`, intake validates and returns the
input collection without writing files.

`validate_assays(collection, artifact_root, atlas_id, target_ids, binder_runs)`
validates the laboratory contract after the strict binder collection has been
validated. `render_assays(collection)` returns escaped HTML, retaining endpoint,
inequality, failure, control status and full source details. Collections declare
`data_status: research` or `synthetic`; synthetic candidates cannot become
research assay evidence. Synthetic displays explicitly state that no laboratory
measurement occurred.

The [JSON Schema](../schemas/v0.1/assay-results.schema.json) checks document
shape, while runtime validation checks files, joins, finite numbers and unit
compatibility. This public companion contract is stricter than an optional
schema-only workshop placeholder and is not a promise of interchangeability
with every external laboratory export. Adapters must preserve the source and
make identity gaps explicit instead of filling them with guesses.

For a reproducible test only, `research_demo.write_synthetic_research_inputs`
creates distinctly labeled synthetic inputs with a failed control, unrun stage,
censored IC50 and missing replicate. These records test software preservation;
they are not campaign outcomes or laboratory observations.
