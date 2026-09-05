# Multiple screening runs

Use `surface-atlas merge-screens` when two or more independent screening
collections belong in one atlas:

```bash
surface-atlas merge-screens RUN_A.json RUN_B.json \
  --output merged-screening-results.json --json
```

Each input needs the screening-result collection schema, the same `atlas_id`,
claim ceiling `computational-screening-hypothesis`, and a `source_run` object
or `source_runs` array. Every screening record needs a `run_id` that belongs to
its input and a unique `screening_result_id`. Keep confirmation contexts scoped
to the run that produced them.

The command writes a new file. It preserves the ordered source runs,
confirmation contexts, records, input summaries, normalization times, and
per-input hash provenance. It counts runs and records without aggregating
scores or changing execution states. Review the result before you make it the
atlas workspace's `screening-results.json`.

The output also preserves each input's non-record collection fields in
`input_metadata`. Repeated merges retain earlier input hashes, summaries,
and source notes.

The report can read legacy `screening_id`, `screen_id`, and `result_id` fields.
Before validation or merging, add `screening_result_id`; merging also requires
explicit source-run metadata. The CLI does not migrate identifiers silently.
