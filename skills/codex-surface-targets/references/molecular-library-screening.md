# Molecular libraries and screening

Keep supplied molecules, known interactions, and prospective screening results
as separate records. Record whether each target relationship is measured,
proposed, computed, or awaiting lookup.

## Identity and preparation

For every library member, preserve a stable molecule ID, source string or
sequence, molecular class and format, stereochemistry and charge state when
known, identity evidence, parent or microstate lineage, preparation method,
and unresolved chemistry flags. Search measured or curated interactions first.
Label database co-occurrence and literature proposals by their source and
evidence type. Link measured binding claims to the reported assay.

For supplied SDF, SMILES, CSV, or FASTA files, start with
[the registration template](../assets/supplied-library-registration.template.json)
and run:

```bash
surface-atlas register-library MANIFEST --output DIRECTORY --json
```

Registration writes a new directory containing `molecular-library.json`, a
registration record, and hash-bound source copies. It preserves supplied
identities and sequences; it does not establish a target relationship or a
screening result. Copy the reviewed collection into an atlas and configure
that directory as `artifact_root` in `.surface-atlas-local.json` before
validation or reporting.

For each selected protein target, record the exact extracellular construct,
chain, sequence hash, residue numbering map, and an accessible site or pocket.
Record the coordinate source, assembly and ligands, and any excluded or
uncertain regions. A small-molecule pocket needs extracellular-location
evidence before it supports a surface-directed modality.

## Select a screening method

Choose a method for the result you need:

| Task | Method | Required evidence |
| --- | --- | --- |
| Reproduce a deposited pocket pose | Defined-box docking with the deposited ligand as positive control | site contacts, clashes, pose diversity, and control recovery |
| Explore possible binding sites | Blind docking or structure prediction | selected extracellular construct, distance or contact criteria, and limitations |
| Compare a short list with another model family | Rescoring or co-folding | receptor sequence identity, model/version, controls, and independent metrics |
| Evaluate a peptide or protein binder | Co-folding or a dedicated binder evaluation workflow | selected interface, positive and negative controls, and sequence lineage |

Preserve the route, model/version, seed and protocol settings, controls, native
artifacts, failures, and score units. A smaller pilot may reduce item count;
it must still exercise the complete receptor, controls, artifact, and
validation path. A score is a ranking signal, not an affinity measurement.

## Authorize the run and import results

Planning, identity resolution, local preparation, and validation are provider
free. Paid compute, private-data transfer, provider license acceptance,
experimental submission, or expansion requires an explicit authorization record
with price state, spend ceiling, destination, stop rule, and cleanup state.

Import screening records into `screening-results.json` with
`evidence_class: computational-screening-hypothesis`. Keep failed controls and
null measurements visible. Validate and rebuild the report after import:

```bash
surface-atlas validate ATLAS_DIRECTORY --json
surface-atlas report ATLAS_DIRECTORY --output-root REPORT_ROOT \
  --run-id RUN_ID --json
```
