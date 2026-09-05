# Sequences, structures, and sites

Map a selected target's extracellular domains, binding partners, and accessible
sites. Start with a protein identifier, target name, or deposited structure
accession.

```text
Use the Life Sciences Databases skills $uniprot-skill, $rcsb-pdb-skill, and
$alphafold-skill to collect the canonical sequence, topology annotations,
experimental structures, and predicted structure metadata for [TARGET]. Use
$biological-sequence-viewer and $structure-viewer to inspect extracellular regions, chains, bound partners,
residue numbering, and candidate accessible sites. Add the checked sequence,
construct, structure, and site records to this Surface Atlas workspace.
```

UniProt provides protein and FASTA records. RCSB PDB provides entry,
assembly, and FASTA records; AlphaFold Database provides prediction and
annotation metadata. The Biological Sequence & Alignment Viewer and Molecular
Structure Viewer support interactive inspection. For a stereoscopic view, ask
Codex to open the same PDB entry or coordinates with Stereofold's
`$stereo-structure` skill.

Store stable accessions, construct and chain identity, residue maps, coordinate
hashes, bound partners, and missing regions in `structures.json` and the target
record. Record the site and intended action in `opportunities.json` when a
molecule or binder route is selected.

Continue with [Supplied libraries and screening](supplied-libraries-screening.md)
for small molecules or [Protein-binder design](protein-binder-design.md) for a
protein interface.
