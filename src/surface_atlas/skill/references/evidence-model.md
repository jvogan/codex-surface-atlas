# Evidence and target-record model

Use a normalized record per surface entity. Protein and non-protein targets share disease and intervention evidence but have different structural and design fields.

## Evidence states

- `observed`: directly stated or measured by the cited source;
- `derived`: deterministic transformation of observed data;
- `inferred`: reasoned interpretation with assumptions;
- `proposed`: therapeutic or experimental hypothesis;
- `not-measured`: searched or relevant but unavailable;
- `not-applicable`: does not apply to this entity or modality.

An empty value is not evidence. Store an unknown numeric or categorical fact as null with `not-measured`, never zero or false.

## Target identity

Every record needs:

- stable atlas target ID;
- entity kind: protein, protein complex, glycan, glycolipid, lipid, metabolite display, or other;
- canonical name, symbols/aliases, species and stable database identifiers;
- exact isoform, disease variant or chemical composition when resolved;
- disease, subtype, cell type, specimen state and treatment context;
- inclusion source and explicit exclusion reason when excluded.

## Surface evidence

Preserve the assay and context behind surface status:

- surface proteomics or cell-surface capture;
- flow or mass cytometry;
- immunohistochemistry or spatial proteomics;
- microscopy;
- topology or curated localization annotation;
- transcript abundance as indirect support only;
- predicted signal peptide, transmembrane helix or GPI anchor as indirect support only.

Record extracellular domains, topology orientation, cleavage, soluble/shedding behavior, internalization/recycling, glycans/PTMs, oligomeric state and membrane microenvironment where known.

## Disease and risk evidence

Keep separate dimensions for:

- disease association and functional role;
- disease versus matched-normal surface abundance;
- patient and subtype coverage;
- intratumoral, interpatient, site and longitudinal heterogeneity;
- treatment-induced gain or loss;
- normal-tissue and immune-cell exposure;
- essential normal function;
- soluble antigen or decoy burden;
- genetic or expression escape mechanisms;
- contradictions and cohort limitations.

Do not describe a target as tumor-specific unless the cited evidence supports that exact claim and context.

## Intervention records

Every intervention record includes a stable ID, direct target, molecular entity, format, intended action, binding site/epitope when known, payload if any, disease context, development state, regulator or trial reference when relevant, evidence date, source, and structure links. Allowed development states should distinguish:

- approved for the scoped disease;
- approved for another indication;
- clinical;
- preclinical;
- research tool;
- computational hypothesis;
- discontinued or withdrawn.

## Prioritization

Keep the measurements and criteria used to compare molecule formats. A composite
score is allowed only when the plan specifies its inputs, missing-data handling,
weights, direction, and sensitivity analysis. Show the components beside the score.

Hard exclusions and deferrals remain in the atlas with reason codes such as:

- surface identity unresolved;
- extracellular accessibility unsupported;
- catastrophic normal-tissue concern unresolved;
- disease evidence insufficient;
- structure or site not actionable for the chosen modality;
- redundant with a better-supported target;
- outside the resource envelope;
- route unavailable or authorization blocked.

## Label hypotheses

Use `candidate target`, `prioritized opportunity`, or `computational design` rather than `treatment` or `drug candidate` for unvalidated hypotheses. The atlas can support research prioritization; it does not establish clinical efficacy, safety, manufacturability, or therapeutic benefit.
