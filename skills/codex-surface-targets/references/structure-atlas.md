# Structure records and site review

For each structure, record the target construct, binding partners, source,
and residue map. Use those records to identify the displayed site and assess
whether it supports the intended action.

## Structure classes

Label each record as one of:

- experimental apo or unbound target;
- experimental natural-ligand complex;
- experimental drug/small-molecule complex;
- experimental antibody, peptide or other binder complex;
- experimental disease-variant structure;
- predicted target model;
- predicted target–intervention complex;
- predicted target–library-member pose or complex;
- homolog or surrogate structure;
- no suitable structure found.

Never display predicted, homologous or truncated constructs as equivalent to a disease-relevant experimental complex.

## Required structure record

Preserve:

- stable atlas, target and structure IDs;
- source database, accession, source revision and retrieval date;
- evidence class and experimental method/resolution where applicable;
- exact construct sequence, species, isoform, variants, engineered mutations and missing residues;
- label/auth chain mapping, entity mapping and selected biological assembly;
- author numbering to canonical sequence numbering map;
- membrane orientation, extracellular side and transmembrane boundaries when relevant;
- ligand, natural partner, antibody/binder and cofactor identities;
- ligand SDF/SMILES or stable chemical identifiers when available;
- molecular-library ID and preparation state for prospective poses;
- glycan, lipid, PTM and cleavage representation plus material omissions;
- coordinate path, lowercase SHA-256 and byte count;
- site or pocket residues and how they were selected;
- limitations that affect the intended action or modality.

Use mmCIF as the canonical file when practical. Provide PDB only as a compatibility representation and do not lose chain or residue identity during conversion.

## Target structure set

For Structure A targets, search for and retain useful representatives of:

- full or most complete target architecture;
- disease-relevant or active/inactive state where applicable;
- natural-ligand or signaling complex;
- every materially distinct approved or high-value research-intervention site;
- extracellular antibody/binder epitopes;
- alternate conformations or assemblies that change accessibility;
- important resistance or escape variants;
- a predicted model only for material gaps left by experimental coverage.

For Structure B, retain representative structures that show sites relevant to
the intended action and molecule format. For Structure C, record the best
available accession and any missing structural information.

## Site cards

A site card contains the exact target construct, chains, residue numbering, spatial context, extracellular-accessibility evidence, glycans/PTMs, known binders, desired action, forbidden or uncertain regions, and structure hashes. Distinguish:

- established therapeutic epitope or pocket;
- natural-ligand interface;
- experimental reference-binder interface;
- inferred accessible surface patch;
- computationally proposed site.

The category limits the claim. An accessible patch is not evidence of functional modulation.

## Viewer use

When Molecular Structure Viewer is callable:

1. Open the exact retained structure once and keep its session ID.
2. Confirm construct, chains, assembly and extracellular orientation.
3. Select the relevant site using the recorded numbering map.
4. Keep the complete target context visible while showing the site and partner.
5. Run requested measurements and those needed to select or assess the site.
6. Save a named scene and export an image or scene file with its source and rendering settings when permitted.
7. Re-read live state before reporting completion.

Use consistent visual semantics: neutral target, stable target-family color, distinct partner/modality colors, bright site highlight, white background, and the same camera convention across comparisons.

## Structure Library view

The report gallery shows standardized panels with badges for evidence class, source, assembly, bound partner, and limitations. Every panel links the raw coordinates, numbering map, structure record, and render recipe. `No deposited complex found` remains visible in the gallery. Predicted screening poses carry their own visual evidence label and link to the receptor, molecule and execution receipts that produced them.
