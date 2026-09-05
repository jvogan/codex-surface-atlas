# Supplied libraries and screening

Compare known ligands with your molecule library, then inspect predicted poses
at a selected extracellular site.

Start with the library files, a stable target identifier, a structure or
construct, and the site you want to investigate. Register the files with
[`surface-atlas register-library`](../supplied-libraries.md) before screening.

```text
Use the Life Sciences Databases skills $pubchem-pug-skill, $chembl-skill, and
$bindingdb-skill to resolve the identities in my supplied library and retrieve
source-backed target or ligand evidence for [TARGET]. Use the NVIDIA BioNeMo
Agent Toolkit skill $diffdock-nim to dock [SELECTED SMALL MOLECULES] against
[STRUCTURE OR CONSTRUCT]. Compare the returned poses with [EXTRACELLULAR SITE]
and the reference ligands. Record known interactions and computed poses with
their respective sources, inputs, settings, controls, and scores in this atlas.
```

PubChem supplies compound properties, descriptions, assays, and substance
metadata. ChEMBL supplies activity, molecule, target, and mechanism records;
BindingDB supports ligand-target lookups by PDB, UniProt, or similarity.
DiffDock predicts ranked poses by blind docking against the supplied structure.
Use the selected site's residues and known ligand contacts to evaluate those
poses. The plugin supports a hosted NVIDIA NIM or a local Docker NIM.

Keep file hashes, parent and prepared identities, and preparation state in
`molecular-library.json`. Add source-supported intervention or interaction
records to `interventions.json`. Keep planned and computed target-site-molecule
results, controls, score units, and returned artifacts in
`screening-results.json`.

## Generate molecules around a selected scaffold

NVIDIA BioNeMo Agent Toolkit also includes GenMol for scaffold decoration and
fragment-based generation, and MolMIM for generation or optimization around a
seed SMILES. Ask Codex to add the generated molecules to the library with their
parent identities and generation settings:

```text
Use $genmol-nim to generate [COUNT] molecules around [SCAFFOLD], preserving
[FRAGMENTS]. Prepare the SAFE representation required by GenMol. Alternatively,
use $molmim-nim to sample molecules around [SEED SMILES]. Save each generated
SMILES with its parent, model settings, and requested properties, then add
the selected molecules to the next screening run in my Surface Atlas.
```

Local chemistry tools can prepare conformers and charge states. Choose the
hosted or local model route and candidate count for the run; keep generated
molecules linked to their preparation and screening results.

For a protein or peptide binder instead of a small molecule, use
[Protein-binder design](protein-binder-design.md).
