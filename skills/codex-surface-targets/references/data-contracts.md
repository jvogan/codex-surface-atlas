# Data contracts

The workspace uses versioned JSON documents. Stable IDs connect normalized records across files. Raw source records remain immutable.

## Workspace collections

| File | Contents |
| --- | --- |
| `discovered-entities.json` | Every normalized disease-linked entity found during retrieval |
| `targets.json` | Entities retained in the surface target universe |
| `excluded-targets.json` | Discovery entities excluded from the surface universe with evidence and reason |
| `interventions.json` | Ligands, drugs, biologics, cell therapies, imaging agents, and research binders |
| `molecular-library.json` | Natural products, metabolites, drugs, fragments, peptides, proteins, antibodies, and other supplied or curated molecules available for evidence lookup or prospective screening |
| `screening-results.json` | Target x site x molecule computational poses, co-folds, scores, controls, failures, and artifact lineage |
| `structures.json` | Experimental structures, predictions, complexes, ligands, residue maps, files, and gaps |
| `opportunities.json` | Selected targets, intended actions, molecule formats, and binding sites |
| `capabilities.json` | Capability states, versions, endpoints, preflights, and artifacts |
| `binder-results.json` | Optional normalized Binder Lane candidates, controls, observations, promotion decisions, lineage, and artifact hashes |

## Discovery accounting

Every discovery entity has one `surface_disposition`:

- `pending`
- `surface-target`, with a valid `target_id`
- `excluded-from-surface-universe`, with a valid `exclusion_id`
- `unresolved`

A completed census contains no pending disposition. Exclusions and unresolved identities remain visible.

## Search coverage

Machine coverage states are `planned`, `in-progress`, `complete_within_recorded_scope`, `partial`, and `blocked`. Each source request has a stable query ID, source, query family, retrieval time, request parameters or hash, page/cursor state, counts, status, raw artifact path, hash, and limitation when incomplete.

Use `complete_within_recorded_scope` only after all registered requests are complete or carry a documented partial/blocked state. The report describes its source list, query families, cutoff date, and gaps.

## Expression context

When a source supplies expression values, a target record may include
`expression_context`. Record `population_key` and `population_label`, plus a
`cohort_name` or `cohort_code` when available. Store percentages in
`single_cell_percent_expressing.values`, keyed by population. The report uses
the recorded population key and label when it displays a value. Older records
using `cancer_surfaceome_context` remain readable as legacy context.

## Structure assignment

Every retained target receives one assignment:

- a tier declared in `atlas-plan.json`, such as `structure-a`, `structure-b`, or `structure-c`;
- `retained-unmodeled`.

Tier counts cannot exceed their declared limits. The total target count has no structure-derived maximum.

## Artifacts

Artifact references use paths relative to the atlas directory and include byte count and lowercase SHA-256. Absolute paths and parent-directory traversal fail validation.

## Molecular libraries and prospective screens

A molecular-library record identifies the input before it assigns any target. Preserve:

- `molecule_id`, input-library ID, name and aliases;
- molecular class and format: small molecule, natural product, metabolite, peptide, modified peptide, protein binder, antibody-format binder, nucleic acid, glycan, glycolipid, or other;
- stable identifiers when available: PubChem CID, ChEBI ID, ChEMBL ID, BindingDB ID, UniProt ID, DOI or supplier/catalog ID;
- canonical or source SMILES, InChIKey, SDF artifact, FASTA sequence, modifications, stereochemistry, protonation/tautomer preparation and provenance;
- source class: user-supplied, curated-known-interactor, endogenous-partner, approved drug, clinical candidate, research reagent, natural-product collection, or generated hypothesis;
- confidentiality, license, receipt, hash, duplicate group and validation state.

A known-interaction record belongs in `interventions.json` only when a source supports the target relationship. Record assay type, quantitative value and units when present, directness, action, species, construct, disease context and source. A text mention, chemical similarity, or database co-occurrence is not a binding measurement.

A prospective result belongs in `screening-results.json`. Use one record per target x site x prepared molecule and preserve every requested seed as a nested observation. Preserve the exact extracellular construct, receptor structure hash, site or blind-docking scope, molecule input hash, preparation state, route and model version, seed and parameters, returned pose or complex artifact, confidence metrics, geometric checks, controls, execution state and failure reason. Aggregate scores must retain their units and must be traceable to the seed-level native artifact. Its evidence class is `computational-screening-hypothesis`; it does not upgrade the molecule to a known intervention.

## Binder result ingestion

`binder-results.json` uses `codex-surface-binder-result-collection/v0.1`. Each candidate preserves the atlas, campaign, request, target, opportunity, parent backbone, full sequence, sequence hash, generation receipt, sequence-design receipt, cofold observations, metric-source hashes, and recorded promotion decision. Failed observations remain in the collection with null metrics.

The companion workflow writes candidate records and runs its own checks before
adding this optional collection to the atlas. It should verify the output-chain
remap against the target-sequence hash before accepting a sequence-design
result. Each scored complex should remain linked to its predicted complex,
confidence artifacts, metric source, and design pose. Keep those companion
check results with the candidate artifacts.

The report reads `binder-results.json` when it is present. The CLI validator
validates the required workspace collections; it does not validate this
optional Binder Lane collection. Keep the companion's candidate records and
validation artifacts available for review before building the report.

The collection claim ceiling is `computational-design-hypothesis`. A deposited positive control keeps its experimental structure provenance, while any generated sequence remains a computational design hypothesis.
