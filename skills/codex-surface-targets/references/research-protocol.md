# Evidence and curation protocol

Record searches and retrieved evidence so the atlas can be resumed and checked.
Keep every entity found within the search scope, including exclusions and
unresolved identities.

## Disease and search scope

Before retrieval, record:

- disease, subtype, organism, population, and evidence cutoff;
- the cell populations and disease states to compare;
- the inclusion definition for accessible cell-surface and extracellular entities;
- the normal-tissue comparison set;
- intended actions such as blocking, agonism, immune engagement,
  internalizing delivery, imaging, occupancy, or molecular glues;
- which data may be sent to which external services.

Label synthetic records and distinguish planned searches from retrieved evidence.

## Source registry and capability record

Start from `assets/source-registry.template.json`. The registry separates:

1. a source role, such as disease association, surface evidence, intervention
   evidence, or structures;
2. the companion skill expected to support that role;
3. the source fields retrieved by that role; and
4. additional sources to consider for the project's coverage.

`discovery-required` marks a suggested capability whose availability must be
checked in the current task. Record `visible-skill` when its skill package is
installed. A capability record becomes
`bound` only after the live capability, source terms, authentication, data
policy, and cost are checked. A matrix or other large download needs a
separate analysis record.

## Deterministic query plan

Register every query before retrieval. The plan records canonical disease
terms, sorted context terms, a query family, source identifier, request
parameters, page-state seed, raw-artifact location, and the next stage that
consumes the records. Query IDs should be deterministic so an unchanged plan
can be reproduced byte for byte.

## Retrieve without a record cap

Retrieve pages until the source's documented pagination rules indicate the
end, or access prevents further retrieval. Record any limit that leaves the
search incomplete. Store large raw pages and request records in a separate
artifact directory. Every request record includes the source, query ID, request time, source
version when supplied, status, page ordinal, cursor state, returned count,
relative raw path, byte count, and SHA-256.

Use `planned`, `in-progress`, `complete_within_recorded_scope`, `partial`, or
`blocked` for each lane. A partial or blocked lane retains its pages and
writes a concrete limitation in the coverage report.

## Normalize and reconcile

Create one discovery record for every normalized disease-linked entity. Keep
proteins, complexes, extracellular domains, ligands, proteoforms, splice
products, glycans, glycolipids, antigens, and intervention targets distinct.
Preserve stable identity, aliases, source links, disease context, and null
measurements. Reconcile the discovery ledger into retained, affirmatively
excluded, and unresolved sets without dropping rows. The accounting identity
is:

```text
discovered entities = retained targets + exclusions + unresolved entities
```

Surface inclusion, disease relevance, safety context, modality fit, and
structure priority remain independent outputs. A source absence is not an
affirmative biological exclusion.

## Validate the atlas and report

Validate the normalized workspace, rebuild the offline report, and inspect
the generated manifest. Report search coverage, computational run status, and
delivered files separately. Every visible score or tier should link to
its contributing records, and every artifact should have a relative path and
checksum. The resulting atlas is a research record; it does not establish
efficacy, safety, or a clinical recommendation.
