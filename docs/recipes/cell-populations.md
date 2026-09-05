# Compare cell populations

Compare disease and normal samples by cell population, then add their
expression measurements to the target census.

Provide the disease, organism, requested cell populations, and either dataset
accessions or a short description of the comparison. Include a matrix and
sample metadata when you want an NGS analysis.

```text
Use the Life Sciences Databases skills $cellxgene-skill and
$biostudies-arrayexpress-skill to find public studies for [DISEASE] that
distinguish [GROUP A] from [GROUP B]. Use $ngs-analysis-workbench to inspect
the data, choose an analysis for this comparison, run it, and interpret the
results. Return dataset accessions, group labels, measurement units, data
transformations, sample counts, and gene-level results to my Surface Atlas.
```

CELLxGENE and BioStudies/ArrayExpress provide collection, dataset, study, and
accession context. NGS Analysis Workbench can inspect supplied matrices and
metadata, prepare a comparison plan, run an approved analysis, and interpret
its returned results. Keep the analysis route and its results beside the source
dataset records.

Put dataset searches and accessions in `search-ledger.json`. Preserve named
groups, unit and transform, sample count, overlap, and analysis method with the
expression evidence in target records or run records. Use those RNA results
with topology and protein-location evidence when comparing surface targets.

Follow with [Disease and surface census](disease-surface-census.md) for broader
evidence or [Sequences, structures, and sites](sequences-structures-sites.md)
for selected proteins.
