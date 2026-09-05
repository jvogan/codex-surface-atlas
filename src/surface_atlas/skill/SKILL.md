---
name: codex-surface-targets
description: Use Rosalind Workbench plugins to identify disease-associated cell-surface targets, compare binding sites and known interventions, and select targets for molecule screening or binder design. Build linked target pages with source evidence, structures, and results.
---

# Codex Surface Atlas

Use this skill to find cell-surface targets in a disease state, compare their
evidence and binding sites, and select targets for screening or binder design.
Start with a disease and cell population, a supplied molecule library, or an
existing atlas. Adapt the sources, molecule formats, and tools to the project.

Start with Rosalind Workbench plugins. Use Life Sciences Databases and Life
Sciences Literature to retrieve evidence, NGS Analysis Workbench to analyze
sequencing data, and Molecular Structure Viewer or Biological Sequence &
Alignment Viewer to inspect structures and constructs. NVIDIA BioNeMo Agent
Toolkit and Biohub ESM provide modeling workflows; Adaptyv Bio connects selected
candidates to experiments. Read [plugin recipes](references/plugin-routing.md)
for prompts and ways to combine these tools.

Select the installed plugins that fit the project and read their skills before
use. The CLI creates the atlas workspace, registers supplied libraries,
validates records, and assembles the report. Add local tools or cloud compute
where a selected recipe needs preparation, modeling, or analysis.

Public companions include [Codex Binder Lane](https://github.com/jvogan/codex-binder-lane)
for binder campaigns, [BioSymphony Structure Factory](https://github.com/BioSymphony/structure-factory)
for structural campaign planning and execution workflows, and
[Proteus](https://github.com/jvogan/proteus) for structure analysis and rendering.
Keep their returned results linked to the atlas's target, site, and run records.

The workflow is:

```text
disease evidence
  -> accessible target census
  -> known interventions
  -> structures, complexes, and accessible sites
  -> action and modality choice
  -> selected screening and design workflows
  -> evidence-linked offline report
```

## Record the disease, population, and intended use

Before gathering evidence, record the disease or subtype, organism, population
and cell context, evidence cutoff, purpose, requested molecule formats, and
compute budget. Specify which data may be sent to which external services.
Read [workflow](references/workflow.md)
and [data contracts](references/data-contracts.md) before adding records.

Locate `surface-atlas` on `PATH` first. If unavailable, check a user-supplied
executable path or the project's `.venv/bin/surface-atlas` on macOS or Linux,
or `.venv/Scripts/surface-atlas.exe` on Windows. Resolve these paths against
the project where the CLI was installed. Verify the executable with `--version`
and use it for every CLI command in this workflow. If no executable is
available, report the missing CLI and refer to the
[installation guide](https://github.com/jvogan/codex-surface-atlas/blob/main/docs/getting-started.md).
Install packages only when the user requests installation.

Create a local workspace with that executable:

```bash
surface-atlas init ATLAS_ID OUTPUT_DIRECTORY \
  --disease "DISEASE OR SUBTYPE" \
  --profile standard --json
```

The initializer refuses an existing destination and writes the versioned plan,
search ledger, and empty collections. Structure tiers set how many targets
receive each depth of review; retain the complete searched target census.

## Review consequential decisions independently

Read [adversarial review](references/adversarial-review.md) and launch bounded
independent subagent reviews at the relevant checkpoints: target census and
normal-tissue evidence, binding site and construct, screening or design with
controls, and final report claims. Use an available equivalent when native
subagents are unavailable; adapt the assignments to the user's scope and the
materials available. Run independent reviews in parallel when supported.

Give reviewers exact files, record IDs, sources, and the decision to challenge.
Request supported findings with the consequence and proposed correction.
Check findings against the evidence, correct accepted issues, rerun
affected checks, and record unresolved limitations before dependent work.
Review does not authorize additional compute or establish scientific proof.

## Find targets and record the evidence

Search every source class named in the plan. Record the query, retrieval
date, returned count, inclusion rule, exclusion reason, disease and cell
context, source identifier, and limitation. Keep every normalized discovery
row, including retained, excluded, and unresolved entities. Record an exclusion
only when a source supports the reason for excluding that entity.

For retained entities, resolve stable identity, aliases and isoforms,
extracellular topology, disease alteration, surface evidence, normal-tissue
exposure, shedding and internalization, known ligands and interventions,
structure availability, and unresolved measurements. Keep observations,
derived prioritization, inferences, and hypotheses in separate fields. Read
[the evidence model](references/evidence-model.md) and
[target reconciliation](references/target-reconciliation.md).

## Select binding sites and molecule formats

Record the molecule's target and the effect it is intended to produce. Specify
its format, binding site, supporting structure, risks, missing measurements,
and proposed analysis or experiment. Internalization may support payload
delivery while reducing surface occupancy; explain how it affects the intended
action. Use [the structure atlas](references/structure-atlas.md)
and [the molecular-library guide](references/molecular-library-screening.md)
when those views are in scope.

When independent target-site screens answer the same question, preserve each
run's source, controls, and confirmation context. Use
[multiple screening runs](references/multi-run-research.md) before merging
their local records.

Any paid compute, private-data transfer, experimental submission, provider
license acceptance, or campaign expansion requires an explicit authorization
record. Preserve route, model and version, scale, destination, price state,
spend ceiling, stop rule, controls, and expected artifacts. A predicted pose or
complex remains a computational hypothesis. Use Codex Binder Lane to coordinate
protein-binder design and evaluation. Read [structure-to-design](references/structure-design-program.md)
and [compute budget](references/compute-budget.md) first.

## Validate and deliver

Read [reader workflow](references/reader-workflow.md) when preparing the report.
Open pages with their recorded findings and useful actions. Build comparisons
around the user's intended action, and identify the next measurement that
could change a target or candidate selection. Name the corresponding Rosalind
plugin recipe and its required inputs.

When interactive exploration fits the project, connect sequence regions,
binding sites, and structures through verified residue maps. Preserve the
reader's selection and required files in copied Codex requests. Have an
independent reviewer check filters, residue links, downloads, and requests
against the source records. Choose extensions that fit the available data.

Use the package CLI for local validation and report assembly:

```bash
surface-atlas validate ATLAS_DIRECTORY --json
surface-atlas report ATLAS_DIRECTORY --output-root REPORT_ROOT \
  --run-id RUN_ID --json
```

The report is offline-capable and includes local JSON and CSV exports, source
links, target pages, structures and artifacts that passed their recorded
integrity checks, and a run manifest. Read [report presentation](references/report-presentation.md)
and [visual delivery](references/visual-delivery.md) for output and accessibility
requirements. Validate the report's files and review its claim ceiling;
the report does not establish efficacy, safety, or clinical suitability.
