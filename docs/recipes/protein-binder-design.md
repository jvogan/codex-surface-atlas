# Protein-binder design

Generate protein-binder candidates for a selected extracellular interface and
compare their predicted complexes. Start with the target construct, chain,
site residues, residue map, binder format, candidate count, and compute budget.

```text
Use the NVIDIA BioNeMo Agent Toolkit skill $protein-binder-design to generate
[COUNT] binder candidates for [TARGET CONSTRUCT] at [SITE OR EPITOPE] within
[BUDGET]. Use $codex-binder-lane to prepare the campaign plan and controls,
then import the sequences, structures, and evaluations returned by the design
workflow. Compare the candidates at the selected site and add their results
to my Surface Atlas.
```

BioNeMo Protein Binder Design composes backbone generation, sequence design,
co-folding, scoring, and candidate filtering. Codex Binder Lane records the
campaign plan, target construct, selected site, controls, candidate sequences,
predicted complexes, and evaluations.

Use Biohub ESM's `$biohub-esm` skill for sequence analysis, structure prediction,
or ESM Atlas searches that support the chosen design workflow. To compare
another design method, retain the same target construct, site, and controls.
[BioSymphony Structure Factory](https://github.com/BioSymphony/structure-factory)
can coordinate selected design, folding, scoring, and rendering stages across
local or cloud tools.

Record the target and site selection in `opportunities.json`. Keep the binder
request, candidate sequences, predicted complexes, route settings, controls,
scores, and run identifiers attached to that target and site. Compare the
returned candidate evidence before choosing any experimental follow-up.

Use [Experiments and report](experiments-and-report.md) to prepare an experiment
for selected candidates and add the measurements to the atlas.
