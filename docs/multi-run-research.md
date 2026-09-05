# Multiple runs in one atlas

Use one atlas when several target-site screens, binder campaigns, or cohort
comparisons answer the same research question. Keep each run identifiable so
you can compare results without mixing controls, inputs, or measurements.

```text
Atlas
├── Screen run A: target, construct, site, library, controls, results
├── Screen run B: target, construct, site, library, controls, results
├── Binder run A: generator, arm, seeds, native scores, common metrics
└── RNA cohorts: named groups, units, transform, sample counts, overlap
```

## Screening runs

Store prospective screen records in `screening-results.json`. Give every
record a stable `screening_result_id`, then preserve the target ID, exact
construct, site, input molecule, route, model version, seeds, native artifacts,
score units, controls, and execution state. These record fields let several
screens share one atlas without replacing one another.

Each input collection needs a `source_run` object or a `source_runs` array.
Every screening record needs a `run_id` that names one source run and a unique
`screening_result_id`. Keep the positive controls, negative controls,
confirmation set, and their pass or failure status with that run. A control
result from one construct, site, or library does not confirm another run.

## Merge screening files

Use `merge-screens` to create one screening collection from two or more
independent inputs:

```bash
surface-atlas merge-screens RUN_A.json RUN_B.json \
  --output merged-screening-results.json --json
```

Each input must be a distinct, regular UTF-8 JSON file with schema
`codex-surface-screening-result-collection/v0.1`, the same `atlas_id`, and
claim ceiling `computational-screening-hypothesis`. Run IDs and screening result
IDs must be unique across the inputs. A confirmation context must reference a
run in its own input and must use that run's `screen_id` when one is recorded.

The command writes a new file and leaves every input unchanged. It preserves
source-run objects, confirmation contexts, records, source summaries, and
normalization times in input order. The output also records each input's
ordinal, SHA-256, and byte count. It counts runs and records but does not
combine scores, reinterpret execution states, or rank results. The merged
summary sets `execution_complete` to `false` when any input sets it to `false`,
to `true` when every input sets it to `true`, and omits it otherwise.

`input_metadata` retains each input's complete collection fields except
`records`, paired with its input ordinal. If you merge a previously merged
collection with another run, the earlier input hashes, source notes, and
summaries remain available in this metadata.

Review the new file before you make it the atlas workspace's
`screening-results.json`. The merger never replaces an existing workspace file.
The screening page then shows each run's source details and confirmation
contexts separately.

### Upgrade legacy screen records

The report can read legacy `screening_id`, `screen_id`, and `result_id` fields.
Before you validate or merge those records, add the canonical
`screening_result_id`. Merging also requires explicit source-run metadata and
run-scoped records. The CLI does not migrate identifiers silently.

## Binder campaigns

Have each companion workflow preserve its own candidate records before you add
them to `binder-results.json`. Keep the generator's source ID, campaign arm or
tranche, requested seed, verified used seed, native generator scores, and the
metrics from any common evaluator. Also retain the target and opportunity IDs,
construct and sequence hashes, control outcomes, prediction artifacts, and
promotion decision.

`binder-results.json` uses the documented Binder result collection ID and is
optional. The report reads it when present. The CLI validator does not validate
it and the report does not create a specialized cross-generator comparison. Use
the companion workflow's checks to verify candidate records and retain its
artifacts before adding a reviewed example bundle.

## RNA cohort comparisons

Use `expression_context` on a target record when a source provides expression
values. Preserve the population key and label, cohort name or code, and the
values in `single_cell_percent_expressing.values`. For a comparison between
RNA cohorts, also preserve each named group, measurement unit, transform,
sample count, and sample overlap as source-specific record fields. The v0.1
envelope keeps these fields but does not define a dedicated RNA importer or
comparison schema.

RNA values describe the recorded RNA measurement. Keep surface-accessibility
evidence in its own field; RNA abundance alone cannot establish surface
abundance.

## Compose a reviewed atlas

1. Initialize one atlas for the shared disease-state question.
2. Add source-linked target, structure, opportunity, and screening records with
   stable IDs.
3. Preserve each run's inputs, controls, confirmation results, artifacts, and
   source identifiers in its own records.
4. Validate the required workspace collections, then build the local report.

The compact report can link selected structures and results. Keep larger run
artifacts in the manifest so a reviewer can trace each result to its run.
