# Structure-to-design program

Find structures for retained surface targets, inspect accessible binding sites,
and prepare the inputs for protein or peptide binder design.

## Structure coverage

Give every retained target a Level 0 structure index before assigning deeper
review effort. Record stable target and isoform identity, extracellular sequence
and topology, cleavage and transmembrane boundaries, oligomeric state,
modifications, deposited structures and complexes, predicted-model availability,
extracellular coordinate coverage, numbering or assembly gaps, and an explicit
state such as `experimental-coverage`, `prediction-available`,
`homolog-only`, or `no-suitable-structure-found`.

Structure waves allocate depth after discovery; they never remove targets from
the census. A deeper review may include construct reconciliation, decision-
relevant complexes, interface maps, standardized scenes, site review, or a
portable thumbnail. Retained targets outside the allocated waves keep their
Level 0 record and an explicit deferral reason.

## Target-site handoff

For a protein or compatible peptide binder, a handoff should contain:

- atlas and target IDs, exact construct and chain, and sequence hash;
- residue map, selected site, excluded or modified regions, and uncertain
  residues;
- intended action and format, positive and negative controls, and evidence
  references;
- data-sharing restrictions, selected tools and services, spend ceiling, and required outputs;
- source coordinate hashes and the expected artifact manifest.

Use Codex Binder Lane for generation, prediction, scoring, candidate tracking,
and delivery when selected for the project. Surface Atlas records the request
and imports the resulting summary, selection decision, run records, and output
hashes. Do not create a second ranking or turn a computational candidate into
a measured binder.

## Check the inputs and returned results

Before any external job, verify identity, site, controls, route capability,
authorization, destination, price, stop rules, and cleanup state. Keep
experimental structures distinct from predicted models and computational
poses. Validate the atlas and rebuild the offline report after importing a
handoff or result. The package CLI handles these local steps:

```bash
surface-atlas validate ATLAS_DIRECTORY --json
surface-atlas report ATLAS_DIRECTORY --output-root REPORT_ROOT \
  --run-id RUN_ID --json
```
