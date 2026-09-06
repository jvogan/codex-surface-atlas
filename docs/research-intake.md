# Bring campaign runs and assay returns into an atlas

Register supplied files locally, validate their exact identities, and build a
report that keeps each run's observations and controls separate. These commands
do not run models or submit experiments.

1. Follow [binder-run intake](binder-run-intake.md) to preserve generator and
   evaluator versions, seeds, constructs, lineage, observations, controls,
   failures, unrun stages, and explicit promotion decisions.
2. Follow [laboratory assay intake](laboratory-assay-intake.md) to join returned
   observations to those exact constructs, retaining units, inequalities,
   individual replicates, missing readings, and control outcomes.
3. Validate the assembled atlas and build its report. The Campaign runs and
   Assay returns pages summarize decisions and link supporting source artifacts.

The [offline tutorial](tutorial.md) demonstrates both import paths with invented
data. Its failed and unrun controls block advancement, and its censored assay
value is preserved without conversion to an affinity estimate.

Each importer writes a new bundle or validates without writing. Add the complete
bundle to an atlas copy; a collection file alone does not carry its source
artifacts. A report export includes an `artifact_map` in `data/atlas.json` that
maps workspace-relative references to its packaged `data/artifacts/` files.
Individual downloaded collection JSON files retain their source references;
keep the complete report bundle to inspect those files offline.
