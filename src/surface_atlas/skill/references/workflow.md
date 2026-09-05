# Staged Surface Atlas workflow

Use these stages to track the search, target review, and selected computation.
Record each stage's inputs, outputs, status, and missing requirements. Revisit
earlier stages when new evidence changes a target or site selection.

## Stage graph

| Stage | Work | Required output | Completion check |
| --- | --- | --- | --- |
| G0 | Record the disease and search scope | Disease/subtype, clinical context, population, evidence cutoff, inclusion rules, data restrictions, and budget | Scope is recorded; private fields are separated; external work is authorized or blocked |
| G1 | Register queries and sources | Synonyms, query families, stopping rules, source classes and resumable ledger | The complete search plan is visible before retrieval |
| G2 | Retrieve literature, preprints and data | Raw records, source metadata and request receipts | Pagination and date windows are exhausted or a gap is recorded |
| G3 | Build the disease-entity ledger | Uncapped normalized genes, proteins, complexes, epitopes, non-protein entities and hypotheses | Every retrieved entity is normalized, unresolved or excluded with a reason |
| G4 | Confirm surface accessibility and context | Uncapped surface universe plus topology, cell owner, disease state, normal exposure and contradictions | Surface inclusion and exclusion are traceable |
| G5 | Map interventions and molecule libraries | Natural ligands, drugs, natural products, metabolites, antibodies, conjugates, cell therapies, trials, failures, research binders and supplied libraries | Known target relationships are source-backed; untargeted library entries remain unassigned |
| G6 | Reconcile and save the census | Deduplicated target census, exclusions, unresolved records, coverage report and content hash | Planned searches are complete or have documented gaps; no target-count cap was applied |
| G7 | Assign structure resources | Level 0 index for every target plus selected structure-work tiers | Every target remains visible; selection criteria and resource effects are inspectable |
| G8 | Assemble the structure atlas | Apo, complex, ligand and model records with portable files and hashes | Identity, construct, chains, assembly, numbering, evidence class and limitations validate |
| G9 | Select actions, molecule formats, sites, and screens | Target and site selections, with molecule formats and libraries to evaluate | Mechanism, accessible site or pocket, principal risk, input library, controls, missing evidence and proposed analysis are recorded |
| G10 | Prepare or run binder design | Validated companion request and, when authorized, external run records and outputs | Route, data policy, biller-specific ceiling, reserve and stop rules were set before execution |
| G11 | Build the report and downloads | Offline report, data library, viewer exports, citations, manifests and browser checks | Search coverage, computational status, and delivered files are reported separately |

## Operating modes

### Plan only

Record the stages, available tools, search strategy, structure-review tiers,
budget, and requested files. Mark searches and computation as planned. This
mode makes no provider calls.

### Public evidence atlas

Retrieve and normalize public evidence. Network reads are permitted within the user's research request. External paid compute and mutations remain blocked.

### Frozen demo replay

Use a dated, hash-bound public dataset and precomputed structures or campaign outputs. Label the replay prominently. Do not imply that model inference happened during the presentation.

### Live extension

Refresh selected sources or run user-authorized computational companions. Record what changed relative to the frozen snapshot and preserve the earlier artifact.

## Structure-review profiles

| Profile | Deep targets | Focused targets | Survey targets | Default live-design scope |
| --- | ---: | ---: | ---: | ---: |
| showcase | 6 | 12 | 20 | 1 |
| standard | 10 | 20 | 20 | 1–3 |
| broad | 15 | 35 | 50 | 1–5 |

The research census has no target-count limit. Resource profiles control structure retrieval, detailed site analysis, prediction and design. Targets outside a structure tier remain in the evidence atlas. The plan may increase any tier after it records the resource consequence.

## Ranking scenarios

Prioritization is conditional on an intended intervention. Useful scenarios include:

- blocking or antagonism;
- agonism, partial agonism or conditional activation;
- immune-cell engagement;
- internalizing payload delivery;
- radioligand or imaging-agent delivery;
- occupancy-only binder or diagnostic;
- small-molecule orthosteric, allosteric or covalent modulation;
- soluble ligand or receptor trapping.

Keep the underlying evidence unchanged when comparing molecule formats.
Explain which criteria caused each change in target rank.

## Existing-molecule and binder libraries

Accept user or curated inputs as SDF, SMILES/CSV, InChIKey lists, FASTA, PDB/mmCIF, or stable database identifiers. Normalize identity and preparation before target assignment. Run two lanes:

1. **Known-interaction retrieval.** Query BindingDB, ChEMBL, PubChem BioAssay, ChEBI, RCSB and primary literature for measured binding, functional interaction, endogenous partnership and deposited complexes.
2. **Prospective site screening.** Screen a declared library against a specific extracellular pocket or interface only after receptor construct, membrane orientation, site accessibility and controls are fixed. Use DiffDock for small-molecule poses and an appropriate co-fold or binder workflow for peptides and proteins. Use Boltz-2 affinity or complex confidence on a bounded shortlist, not as the sole high-throughput screen.

Blind docking may locate hypotheses across a prepared extracellular construct. It does not establish binding, functional action, selectivity or therapeutic usefulness. Keep known, literature-proposed and computed relationships in separate fields and report sections.

## Stop conditions

Stop or narrow a stage when its planned search coverage is complete, its budget
or runtime limit is reached, a required safety or identity check fails, no
suitable tool is available, source records are missing, authorization is
exhausted, or further work cannot affect target or candidate selection.
