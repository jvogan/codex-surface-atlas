# Target reconciliation and prioritization

Classify every discovered entity as a retained surface target, an exclusion
with a cited reason, or an unresolved identity. Keep the original discovery
rows and record evidence, risk, molecule-format fit, and structure-review
priority separately.

## Surface decision order

Check identity and surface evidence in this order:

1. Exclude a non-protein entity by stable identity when the contract says it is
   outside the surface-target universe.
2. Select reviewed canonical identity and retain the alias map.
3. Retain a protein when reviewed extracellular topology, plasma-membrane
   assignment, or source-backed surface evidence supports accessibility.
4. Mark a record unresolved when evidence conflicts or identity/orientation is
   not resolved.
5. Exclude a reviewed entity only when an affirmative intracellular,
   soluble-only, organelle-membrane, cytoplasmic-face, or peripheral-membrane
   assignment is recorded and no positive surface signal remains.

Absence from one database or source is not an exclusion rule.

## Independent outputs

The target record keeps four independent outputs:

- **Evidence:** disease relevance, surface accessibility, patient or subtype
  coverage, functional support, and differential abundance.
- **Risk:** normal-tissue exposure, essential biology, heterogeneity,
  shedding, isoforms, glycosylation, accessibility, and mechanism-specific
  liabilities.
- **Modality fit:** physical and biological suitability for the intended action
  and therapeutic format.
- **Structure priority:** depth of review based on available structures,
  known interventions, supporting measurements, and missing data.

Missing inputs remain `null` or `not-measured`; zero is a measured value when
the source recorded zero. A score organizes research resources and does not
establish efficacy or safety.

## Accounting and validation

After reconciliation, check:

```text
discovered entities = retained targets + exclusions + unresolved entities
```

Run the package validator before building a report:

```bash
surface-atlas validate ATLAS_DIRECTORY --json
surface-atlas report ATLAS_DIRECTORY --output-root REPORT_ROOT \
  --run-id RUN_ID --json
```

The package initializer supplies empty, versioned collections. A campaign may
populate them with source-reviewed records while preserving stable IDs,
retrieval dates, source references, and artifact hashes.
