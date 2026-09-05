# Report views and scientific files

The CLI builds local HTML pages and JSON and CSV exports. Use the selected
scientific tools to create additional images, video, viewer sessions, or
analysis results. The specifications below apply when adding those views
to a report.

Use [reader workflow](reader-workflow.md) for page openings, sequence-to-site
interactions, comparisons, and copied plugin requests. Select views that help
readers inspect the project's findings or continue a specific analysis.

## View specifications

### Cell-Surface Map

Position targets by disease cell context and topology. Shape encodes entity class, fill or pattern encodes surface-evidence class, and a small outline label identifies Structure A, B, C, or Evidence only.

### Target Evidence Plot

Plot disease evidence against normal-tissue risk. Bubble size may encode supported patient coverage and color may encode selected modality, but every encoding must identify its source and missing-data behavior.

### Modality Matrix

Display target x action x modality fit. When the reader changes the intended action, reorder targets and list the factors that changed. Label the active scenario beside every displayed rank.

### Structure Library

Use a consistent white-background view and camera across target and complex structures. Distinguish experimental apo, natural-ligand, drug-bound, antibody/binder-bound, predicted and missing states. Each image links to coordinates and its render recipe.

### Treatment Timeline

For each target, show natural ligand, research binder, preclinical intervention, clinical study, approval and discontinuation as dated, source-backed events. Keep development state and disease indication visible.

### Evidence Details

Link each score, tier, and candidate selection to its supporting and conflicting
evidence, retrieval dates, sources, and selection rules.

### Cell-to-Site View

Show the cell population, target topology, extracellular construct, and selected
binding site in linked images or a video. For video, verify that the exported
file decodes and plays before including it in the report.

### Opportunity Cards and Design Results

Each opportunity card names the target, intended action, molecule format,
binding site, reason for selection, leading risk, missing measurements, and
proposed analysis or experiment. Build a design gallery from actual or clearly
labeled replay results. Include candidate IDs, full sequences, structures,
site-specific metrics, parent designs, and evidence labels.

## Target page

Include target identity and isoforms, topology, disease and surface evidence,
matched-normal measurements, patient or subtype coverage, known ligands and
interventions, and molecule-format comparisons. Link structures, complexes,
glycan and modification records, candidate sites, residue maps, and sources.
Show conflicting evidence and missing measurements beside the findings they affect.

## Portable delivery

Deliver:

- `index.html` with accessible static evidence and optional progressive enhancement;
- normalized JSON and CSV tables;
- FASTA for protein sequences and alignments when relevant;
- mmCIF/PDB coordinates and residue maps;
- SDF/SMILES or stable chemical identifiers for ligands when relevant;
- rendered PNG/WebP images and exact render recipes;
- MP4/WebM only when requested and decoder-validated;
- receipts, source manifest, artifact hashes, and a delivery index.

The HTML must remain useful without network access. Remote citations may open externally, but core text, tables, images and downloadable scientific files are local.

## Replay and live-state disclosure

A shareable demonstration defaults to a frozen, dated public-evidence snapshot and precomputed outputs. Label each artifact as replayed, refreshed during the session, newly computed, or not run. A replay demonstrates the recorded workflow and does not claim live model inference.

## Completion checks

Report three independent outcomes:

- Search coverage: validate the searched scope and normalized evidence.
- Computation: verify completed outputs or record the reason a selected stage stopped.
- Delivery: check the requested report, structures, viewer exports, and video files.

Mark the work complete only after all required checks pass. Inspect the overview,
one target page, the structure gallery, and any requested video in the browser.
Save the browser-check results with the delivery record.

For added interactive views, check that filters, residue links, downloads,
and copied requests preserve the selected records. Include keyboard use and a
narrow layout. Follow the interaction assignment in
[adversarial review](adversarial-review.md).
