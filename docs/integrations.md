# Rosalind Workbench integrations

Use Surface Atlas with Rosalind Workbench plugins to gather source evidence,
inspect molecular context, and carry selected results into one atlas. Start
with a recipe, then combine it with the next one your project needs.

| Recipe | Plugins to ask Codex to use | Atlas material returned |
| --- | --- | --- |
| [Disease and surface census](recipes/disease-surface-census.md) | Life Sciences Databases and Life Sciences Literature | Search records, disease evidence, surface assignments, normal-tissue context |
| [Compare cell populations](recipes/cell-populations.md) | CELLxGENE, BioStudies/ArrayExpress, NGS Analysis Workbench | Dataset records, named comparison groups, RNA measurements, analysis results |
| [Sequences, structures, and sites](recipes/sequences-structures-sites.md) | UniProt, RCSB PDB, AlphaFold Database, Biological Sequence & Alignment Viewer, Molecular Structure Viewer, Stereofold | Sequence and construct identity, structure records, chains, residue maps, site evidence |
| [Supplied libraries and screening](recipes/supplied-libraries-screening.md) | PubChem, ChEMBL, BindingDB, NVIDIA BioNeMo Agent Toolkit | Library identity, measured interaction evidence, planned or computed screening records |
| [Protein-binder design](recipes/protein-binder-design.md) | NVIDIA BioNeMo Agent Toolkit, Biohub ESM, Codex Binder Lane | Target construct, selected site, candidate sequences, predicted complexes, evaluation metrics |
| [Experiments and report](recipes/experiments-and-report.md) | Adaptyv Bio and the local Surface Atlas CLI | Experiment specification or returned measurements, updated atlas report |

The local CLI creates workspaces, validates records, and builds reports. The
plugins supply source retrieval, analysis, structure inspection, modeling, or
experiment work for the chosen route. The [recipe index](recipes/README.md)
includes copyable prompts.

## Sources to combine

Ask Life Sciences Databases and Life Sciences Literature for the sources that
answer the current part of the research. These groups extend the starting
queries in the recipes.

| Research task | Sources available through the plugins |
| --- | --- |
| Find studies and preprints | PubMed/NCBI Entrez, PubMed Central, bioRxiv, medRxiv |
| Examine disease associations and variants | Open Targets, CIViC, ClinVar, Ensembl, gnomAD, GWAS Catalog, cBioPortal |
| Find tissue, cell-population, and study data | CELLxGENE, Human Protein Atlas, Bgee, BioStudies/ArrayExpress |
| Investigate gene regulation | GTEx eQTL, ENCODE, eQTL Catalogue |
| Locate proteomics datasets | PRIDE, ProteomeXchange |
| Annotate proteins, pathways, and interactions | UniProt, QuickGO, Reactome, STRING |
| Retrieve structures and prediction metadata | RCSB PDB, AlphaFold Database |
| Resolve molecules and biochemical reactions | PubChem, ChEBI, Rhea, MetaboLights |
| Find measured ligand activities and treatment context | ChEMBL, BindingDB, ClinicalTrials.gov, PharmGKB |

Use the database plugins to identify datasets and supporting records. Use NGS
Analysis Workbench for analysis of selected sequencing data, and the viewers
for direct inspection of sequences and structures.

## Companion repositories

| Project | Use it for | Keep in the atlas |
| --- | --- | --- |
| [Codex Binder Lane](https://github.com/jvogan/codex-binder-lane) | Plan a protein-binder campaign, compare design lanes, and evaluate candidates | Target construct, selected site, candidate sequences, predicted complexes, metrics, and run records |
| [BioSymphony Structure Factory](https://github.com/BioSymphony/structure-factory) | Coordinate structural design, folding, scoring, screening, and rendering | Campaign plan, checked artifacts, figures, and result summaries tied to targets and sites |
| [Proteus](https://github.com/jvogan/proteus) | Retrieve and inspect structures, map interfaces, and prepare figures | Coordinate files, residue mappings, visualizations, and source accessions |

Choose a companion when its route fits the selected target and site. Keep its
returned files connected to the same target, site, and run identifiers used by
the atlas.
