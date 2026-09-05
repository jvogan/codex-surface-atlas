# Experiments and report

Prepare an experiment for selected candidates, then add the returned
measurements to their atlas records and rebuild the report.

Start with candidate sequence labels or molecule IDs, target and assay context,
the requested measurements, and any returned computational or experimental
results.

```text
Use Adaptyv Bio's $prepare-experiment skill to prepare [ASSAY] for [CANDIDATES]
and [TARGET CONSTRUCT]. Include controls, assay conditions, requested
measurements, and estimated cost. Show me the experiment specification for
review. Use $review-and-submit-experiment for submission and $track-experiment
to follow its progress. Add the returned measurements and tested candidate
IDs to my Surface Atlas, then rebuild the report.
```

Adaptyv Bio carries the experiment specification through quotation, submission,
and results retrieval. Keep candidate labels, target, assay method, measurement
units, replicate information, and result identifiers with the corresponding
target and run records.

Rebuild the atlas report after adding records:

```bash
surface-atlas validate ATLAS_DIRECTORY --json
surface-atlas report ATLAS_DIRECTORY \
  --output-root REPORT_DIRECTORY --run-id RUN_ID --json
```

The report creates linked target pages, source records, structures, screening
or binder results, and downloadable JSON and CSV files.
