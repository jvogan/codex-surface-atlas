# Report presentation

Open each page with its recorded finding and a useful action. Use
[reader workflow](reader-workflow.md) to choose comparisons, linked molecular
views, and follow-up analyses for the project. Keep source measurements and
scientific files accessible from the findings they support.

Build the report from normalized atlas records after local validation:

```bash
surface-atlas validate ATLAS_DIRECTORY --json
surface-atlas report ATLAS_DIRECTORY \
  --output-root REPORT_ROOT --run-id RUN_ID --json
```

The report builder runs locally. It creates static HTML pages,
local JSON and CSV exports, copied artifacts whose relative paths and hashes
match their records, and a run manifest. For an empty or plan-only atlas,
display missing evidence and planned work with their recorded status.

## Linked records and evidence labels

Keep the overview, target explorer, target pages, intervention view,
molecule and screening view, structure view, design and sources view, and study
coverage view linked to the same normalized records. Every visible score or
tier should expose its contributing fields. Every structure image or artifact
should link to its local copy and coordinate source when recorded.

Keep these claim levels visible:

- source observation and source-linked evidence;
- derived normalization or prioritization;
- inferred interpretation;
- computational screening or design hypothesis;
- experimental result.

Do not turn a report page into a treatment recommendation. Preserve null
measurements, contradictory evidence, failed controls, and partial source
coverage. A report snapshot says what was recorded and validated at its build
time; it does not imply that a provider, model, or experiment ran merely
because a route is named in a plan.

For new output formats, use relative artifact paths and SHA-256 records. Keep
large raw pages, private data, credentials, provider payloads, and run caches
outside the portable report. Review [visual delivery](visual-delivery.md) for
offline and accessibility requirements.
