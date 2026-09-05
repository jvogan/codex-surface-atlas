# Adversarial review

Use independent reviewers to challenge the evidence and reasoning before a
target, binding site, computational result, or report drives the next step.
Reviewers look for unsupported conclusions, contradictory observations, and
file or identity mismatches that could change a decision.

## Review the decisions that matter

At each relevant checkpoint, launch native subagents with separate, bounded
review assignments. Use an available equivalent when native subagents are
unavailable. Run independent assignments in parallel when the environment and
the user's instructions permit it. Give each reviewer the exact file paths,
record IDs, source references, decision under review, and a stopping point.
Reviewers inspect those materials independently before reading other reviewers'
findings. They return findings; the coordinating agent makes corrections.

| Checkpoint | Files and reasoning to inspect |
| --- | --- |
| Target census and normal tissue | Reconcile the search ledger with discovered, retained, excluded, and unresolved records. Check identities, inclusion rules, missing source coverage, disease and cell-population context, and contrary normal-tissue observations. Challenge conclusions that infer protein accessibility or selectivity from transcript measurements alone. |
| Binding site and construct | Compare the selected target, isoform, sequence, structure, chain IDs, residue numbering, and proposed site. Check whether the construct represents the intended extracellular region and whether missing residues, partners, glycans, or preparation changes limit the proposed interaction. Verify that figures and downloads refer to the same coordinates. |
| Screening, design, and controls | Inspect molecule and sequence identities, input hashes, target-site assignments, preparation, controls, failed runs, scoring methods, and recorded promotion decisions. Check score comparisons for incompatible protocols. Seek a control or alternative explanation that could account for the claimed result. Keep experimental observations separate from computed poses and scores. |
| Final report and source claims | Trace consequential statements to the cited source or result record. Check coverage language, evidence labels, unresolved limitations, source attribution, artifact hashes, and report links. Compare displayed results with downloadable records and confirm that copied examples contain their required files. |
| Report interactions and plugin requests | Change filters and compare the displayed protein label with its sequence and structure. Follow a residue into 3D and back, including sites with multiple partners. Check that downloaded ranges and copied requests preserve the accession, isoform, chain, numbering, selected residues, and matching files. Test direct links, browser history, keyboard use, narrow layouts, and clipboard fallback. |

Review only checkpoints supported by the current materials. For example, a
census-only task needs evidence review, while a supplied structure task may
begin with the construct and site. Reuse completed reviews when their inputs
and decisions have not changed.

## Resolve findings

Ask reviewers to lead with issues that could change the decision. Each finding
must name the file and record or source, explain the issue and its consequence,
and propose a correction or a focused check. Include a counterexample or
reproduction when one is available. Report no findings when the assigned review
finds no supported issue; avoid filling a quota with speculative concerns.

The coordinating agent compares findings with the underlying evidence, accepts
or rejects each with a reason, and records the resolution beside the relevant
decision. For an accepted finding, correct the record or narrow the conclusion,
then repeat only the affected checks. Record unresolved issues and how they
limit the next step. Hold a decision that depends on a missing identity check,
contradictory evidence, or an unresolved control result.

Review the existing materials within the user's scope. Return proposed new
computational runs or experiments to the coordinating agent for authorization.
If independent workers are unavailable, perform a separate review pass and
identify it as a review by the same agent.

## Prompt for parallel review

```text
Use independent subagents to review this Surface Atlas workspace at the
relevant checkpoints: target census and normal tissue; binding site and
construct; screening or design with controls; final report claims; and
report interactions with plugin requests.
Run independent scopes in parallel where supported. Give each reviewer exact
files, record IDs, and the decision to challenge. Ask for supported findings
with the source, consequence, and correction, starting with those that could
change the decision. For interactive views, test filters, residue links,
downloads, and copied requests against the same source records. Check the findings against the
evidence, fix accepted issues, rerun affected checks, and record unresolved
limitations before continuing. Stay within the existing scope
and compute authorization.
```
