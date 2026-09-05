# Help readers inspect results and continue the work

Build report pages around the findings and the actions a reader can take.
Use these instructions when extending a generated report or preparing a Site.
Choose the views that fit the available records and the user's purpose.
The CLI supplies the base report; the linked sequence controls and comparison
views described here are extensions for the agent to build when useful.

## Open with the finding

Start each page with its main recorded finding and a direct link to the
supporting result. Offer an action that uses those records, such as comparing
normal-tissue measurements, inspecting a binding site, or opening a sequence.
For a page awaiting results, name the missing measurement and the next planned
analysis. Keep its planned status visible.

Use a compact diagram when it explains the page's specific relationships.
Link its targets, sites, or stages to the corresponding records. Place longer
methods and technical workflows in supporting sections. Give readers one
navigation menu for pages and one section menu for a long page.

Keep the measurement type with the finding: RNA abundance, protein abundance,
observed binding, and predicted contacts describe different results. Put
contradictory evidence and failed controls beside the conclusions they affect.
Keep run settings in methods and source details. Show findings and scientific
files in the main reading path.

## Connect sequence selections to binding sites

When sequence and coordinate records are available, connect the sequence,
annotated regions, recorded contacts, and 3D structure. Let readers select a
range, search an exact sequence pattern, inspect mapped residues, and download
the selected sequence. Keep the molecule visible while readers use its controls.

Carry the target accession, isoform, structure, chain, and numbering convention
with every selection. Use the recorded mapping between canonical sequence
positions and coordinate residues, including insertion codes. Check the amino
acids against both files. Display gaps and ambiguous mappings at the affected
positions; use verified mappings for links into 3D.

When a filter changes the selected protein, update its label, sequence, site,
structure, download, and copied request together. For a site spanning multiple
proteins, preserve the selected partner in both directions. Include the source
accession, range, and numbering convention in a downloaded FASTA header.

## Continue with the selected Rosalind plugin

Offer actions that name the work: open a sequence region, inspect contact
residues, compare structures, or prepare a selected construct for design.
Read the installed plugin's skill before composing its request. Use Biological
Sequence & Alignment Viewer for sequence inspection and Molecular Structure
Viewer for coordinates. Offer Motif or another analysis plugin when its
installed workflow fits the requested work.

A copied Codex request must contain enough information to recover the selection:

- The requested analysis and selected plugin.
- The target accession, isoform, site ID, structure, and partner identities.
- The chain, residue range or list, insertion codes, and numbering convention.
- Report-relative sequence, coordinate, and mapping files with recorded hashes.
- The report version and a way to obtain those files: an attached bundle or an
  authorized Site URL.

Copying a request does not transfer files. Have the receiving agent retrieve
the files and verify their identities before opening the selection. Use
portable file references in copied requests. Provide selectable request text
when clipboard access is unavailable.

```text
Open this report selection in [ROSALIND VIEWER]. Use [REPORT BUNDLE OR SITE URL]
to retrieve [FASTA], [COORDINATES], and [RESIDUE MAP], then verify their recorded
hashes. Select [TARGET ACCESSION AND ISOFORM], [STRUCTURE AND CHAIN], and
[RESIDUES WITH NUMBERING CONVENTION]. Inspect [REGION OR CONTACT SITE] with
[PARTNER]. Preserve this selection when preparing the next analysis.
```

## Compare the options for the intended action

State the choice the comparison helps make: which target to investigate for
payload delivery, which extracellular site to inspect, or which candidates to
advance under a specified screening protocol. Select columns that bear on
that choice. Link each measurement to its source, units, and conditions.

For comparisons across targets, include the relevant cell populations,
normal-tissue measurements, accessibility, and intended molecular effect.
For screening or design results, group compatible protocols and show their
controls. Show results from incompatible protocols in separate groups. Preserve missing
values and explain how they affect the comparison.

When a reader changes the intended action or filters, label the active choice
and explain which recorded factors changed the ordering. Preserve the selected
IDs in the exported table or copied request. Describe the reason for a
preference using the displayed measurements.

## Select the next useful measurement

For each shortlisted target or candidate, identify the unresolved measurement
most likely to change its selection for the intended action. Explain what
different outcomes would change and link the supporting evidence. Use a
recorded decision threshold when one exists; label a proposed threshold as
proposed.

Name the input files, required controls, expected output, and suitable plugin
recipe. Start with available evidence before proposing a new computation or
experiment. Choose the route that fits the missing measurement:

| Missing information | Suggested next work |
| --- | --- |
| Disease or normal-tissue context | Use Life Sciences Databases and Life Sciences Literature to retrieve the relevant measurements and studies. |
| Cell-population differences in available sequencing data | Use NGS Analysis Workbench to analyze the selected samples and compare the recorded groups. |
| Construct boundaries or residue correspondence | Use the sequence and structure viewers with the source annotations and residue map. |
| Candidate binding measurements | Use Adaptyv Bio to prepare a supported assay with the selected candidates and controls. |

Place local preparation or cloud computation within the selected recipe when
needed. Apply the existing scope and compute authorization to execution.

## Review the complete reader action

Use an independent reviewer for the interaction checks in
[adversarial review](adversarial-review.md). Give the reviewer the report,
representative source records, and an action to complete. Ask them to change
filters, follow a site into 3D, return to its sequence, download the selection,
and inspect the copied plugin request.

Check that each step preserves the same protein, partner, residues, and source
files. Test direct links, browser history, keyboard controls, narrow layouts,
and clipboard fallback. Record failures with reproduction steps and the
affected IDs. Repeat the affected actions after corrections and on the
deployed Site when hosting is requested.
