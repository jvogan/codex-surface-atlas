# Disease and surface census

Find cell-surface targets associated with a disease and collect the studies,
protein annotations, and tissue measurements that support their inclusion.

Start with a disease or subtype, organism, cell population, and evidence
cutoff. Add any known target names or source accessions when available.

Include receptors, enzymes, transporters, adhesion proteins, immune regulators,
and protein complexes. Record isoforms, glycoforms, and other surface
determinants when the source data distinguish them.

```text
Use the Life Sciences Databases skills $opentargets-skill, $uniprot-skill,
$human-protein-atlas-skill, and $cellxgene-skill with the Life Sciences
Literature skills $ncbi-entrez-skill and $ncbi-pmc-skill to build a
surface-target census for [DISEASE] in [CELL POPULATION]. Record disease and
surface evidence, normal-tissue context, source links, retrieval dates,
excluded entities, and unresolved identities in this Surface Atlas workspace.
```

Open Targets provides target–disease associations. UniProt describes protein
identity and topology. Human Protein Atlas and CELLxGENE provide tissue and
cell-population data; the literature plugins retrieve supporting studies.

Extend the search with cBioPortal for cancer-study data, CIViC or ClinVar for
variant evidence, PRIDE or ProteomeXchange for proteomics studies, and Reactome
or STRING for pathways and interactions. The [source map](../integrations.md#sources-to-combine)
lists further choices.

Record each query and source result in `search-ledger.json`. Put normalized
entities in `discovered-entities.json`, then retain, exclude, or leave them
unresolved in the target collections. Carry disease evidence, surface evidence,
normal-tissue signals, source identifiers, and evidence labels into the target
records.

Add [cell-population comparison](cell-populations.md) when the census needs a
specific RNA contrast. Add [structure and site review](sequences-structures-sites.md)
for targets selected for molecular work.
