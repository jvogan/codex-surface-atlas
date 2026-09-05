# Rosalind plugin recipes

Choose a starting point below and replace the bracketed inputs. Combine the
steps that fit the project; carry each target's identity and source references
into the next step.

To compare existing results and select the next measurement, use
[reader workflow](reader-workflow.md). It also describes how to carry a
sequence or binding-site selection into a plugin request with the required
files and residue numbering.

## Discover surface targets

```text
Use $codex-surface-targets with Life Sciences Databases and Life Sciences
Literature to investigate [disease] in [cell population]. Search Open Targets
for disease associations, UniProt for extracellular topology, and Human
Protein Atlas for tissue evidence. Use PubMed and PubMed Central to examine
the studies behind the findings. Record retained targets, exclusions, and
unresolved identities in the atlas with their sources.
```

Use CELLxGENE or BioStudies/ArrayExpress to find relevant datasets, then NGS
Analysis Workbench to analyze selected data. Record the sample groups, cell
labels, measurements, and analysis methods with the target records.

## Connect a target to an accessible site

```text
For [target], use Life Sciences Databases to retrieve UniProt annotations,
RCSB PDB structures, and AlphaFold coverage. Open the sequence in Biological
Sequence & Alignment Viewer and the structures in Molecular Structure Viewer.
Map the extracellular domains, construct boundaries, partner chains, and
contact residues. Add the selected site and source files to the atlas.
```

Use Proteus for additional residue mapping, structural comparisons, and PyMOL
or ChimeraX figures. Stereofold provides another way to inspect the structure.

## Screen a molecule library

```text
Use Life Sciences Databases to find known ligands and measured activities for
[target] in ChEMBL and BindingDB, and resolve compound identities with PubChem.
Register my [SDF, SMILES, CSV, or FASTA] library in the atlas. For the selected
small molecules and [extracellular pocket], use the NVIDIA BioNeMo Agent
Toolkit's docking workflow with reference ligands. Keep the inputs, scoring
method, returned poses, and controls together in each run's records.
```

Select a protein or peptide workflow for FASTA inputs. Local chemistry tools
can prepare conformers and charges before docking. Keep preparation methods
and parent-molecule IDs with the prepared inputs.

NVIDIA BioNeMo Agent Toolkit also provides `$genmol-nim` for scaffold and
fragment-based molecule generation and `$molmim-nim` for generation around seed
SMILES. Prepare SAFE notation for GenMol, and retain parent identities and model
settings with the generated molecules. For DiffDock, evaluate its blind-docking
poses against the selected site's residues and reference ligands.

## Design and evaluate protein binders

```text
For [target and extracellular site], use Codex Binder Lane and NVIDIA BioNeMo
Agent Toolkit to compare suitable protein-binder workflows. Use [construct],
[intended action], and [binder format] to select the design inputs and controls.
Use Biohub ESM where sequence or structure modeling fits the selected workflow.
Return candidate sequences, predicted complexes, and evaluations to the atlas,
linked to the target, site, and design run.
```

BioSymphony Structure Factory can coordinate selected design, folding,
screening, and rendering stages. Set the model, number of candidates, compute
budget, and completion criteria before starting a run.

## Prepare experiments

```text
Use Adaptyv Bio to prepare an experiment for [selected candidates] against
[target construct]. Carry the sequences, controls, assay conditions, and
requested measurements into the experiment specification. Show me the
specification for review, then track the experiment and connect its returned
measurements to the tested candidates in the atlas.
```

Read the chosen plugin's submission requirements and obtain the user's
authorization before submitting an experiment or starting paid compute.
Respect existing authorizations. Record the selected tools, versions, input
files, settings, and returned results so the report can show how each result
was produced.
