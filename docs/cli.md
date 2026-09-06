# CLI reference

The `surface-atlas` command requires Python 3.10 or later and works entirely
on local files. It creates and validates atlas workspaces, builds offline
reports, and checks or exports reviewed files. Use an agent task and its
available tools when the research needs evidence retrieval, structure viewing,
or companion computation. Use `--json` when another tool needs the result as
structured output.

## Create and validate an atlas

```bash
surface-atlas init ATLAS_ID OUTPUT_DIRECTORY --disease "DISEASE" \
  --profile standard --evidence-cutoff YYYY-MM-DD --json
surface-atlas validate ATLAS_DIRECTORY --json
```

`--profile` accepts `showcase`, `standard`, or `broad`. The initializer refuses an output path that already exists.

## Register a supplied library

```bash
surface-atlas register-library MANIFEST --output DIRECTORY \
  [--base-library FILE] [--json]
```

Register SDF, SMILES, CSV, or FASTA inputs in a new local output directory.
The output contains `molecular-library.json`, `registration.json`, and copied
source files. It never replaces an existing directory. See [Supplied
libraries](supplied-libraries.md) for the manifest template and atlas handoff.

`--base-library` extends a previous import. Its referenced files must be available
below that collection's directory and match their recorded hashes and sizes.

## Create a report

```bash
surface-atlas report ATLAS_DIRECTORY \
  --output-root REPORT_DIRECTORY --run-id RUN_ID --json
```

The report is written beneath `REPORT_DIRECTORY/ATLAS_ID/RUN_ID`. Each run ID must be new; reports do not replace an earlier run.

## Merge screening runs

```bash
surface-atlas merge-screens INPUT INPUT [INPUT ...] \
  --output NEW_FILE --json
```

Merge at least two independent `screening-results.json` collections for the
same atlas. Each input declares its source run or runs, scopes every screening
record and confirmation context to a run, and retains unique run and result
IDs. The command writes a new JSON file with input provenance and preserves
records in input order. It does not aggregate scores or replace an existing
file. See [Multiple runs in one atlas](multi-run-research.md).

## Synthetic example

```bash
surface-atlas example OUTPUT_DIRECTORY --json
```

The synthetic example contains invented records only. Use it to check the workspace, validation, and report workflow.

## Complete offline tutorial

```bash
surface-atlas tutorial NEW_DIRECTORY --json
```

Creates a deterministic, explicitly synthetic workspace containing source
snapshots, a reconciled census, action evidence, mapped sequence sites, binder
runs, and an assay return. See [the replay tutorial](tutorial.md) for the expected
results. No retrieval, model, or laboratory service runs.

## Evidence intake and reconciliation

```bash
surface-atlas ingest-evidence SNAPSHOT [SNAPSHOT ...] \
  --atlas BASE_ATLAS --output NEW_ATLAS_DIRECTORY --json
surface-atlas reconcile-evidence ATLAS_DIRECTORY --json
surface-atlas reconcile-evidence ATLAS_DIRECTORY --output NEW_LEDGER_JSON --json
```

Intake creates a new portable atlas from explicitly reviewed source snapshots.
It preserves raw source bytes and reconciles stable identities and dispositions.
Reconciliation reports stale ledger counts, verifies source projections, and
optionally writes a new ledger file. It never edits an existing atlas in place.
See [evidence intake](evidence-intake.md) for the input contract and limitations.

## Binder runs and assay returns

```bash
surface-atlas import-binder-runs RUN_JSON [RUN_JSON ...] \
  --atlas ATLAS_DIRECTORY --output NEW_BUNDLE_DIRECTORY --json
surface-atlas import-assays ASSAY_JSON \
  --atlas ATLAS_DIRECTORY --output NEW_BUNDLE_DIRECTORY --json
```

Omit `--output` to validate only. Each output bundles its collection and verified
source artifacts. Add the complete bundle to a copy of the atlas, then validate
and report that copy. Assay candidate/run identities and both constructs must
match registered binder runs. The importer preserves measurements and controls;
it does not promote a candidate. See [research intake](research-intake.md).

## Skill lifecycle

```bash
surface-atlas install-skill \
  --destination .agents/skills/codex-surface-targets --json
surface-atlas uninstall-skill \
  --destination .agents/skills/codex-surface-targets --json
```

The destination is the skill directory itself. For a user-wide Codex installation, use `~/.codex/skills/codex-surface-targets` instead. Start a new task after installation and invoke `$codex-surface-targets`. Install refuses an unrecognized existing directory; uninstall removes only a verified, package-managed skill directory. A custom destination can be useful in an automated test, but Codex will not discover it until it is placed in a configured skill directory.

## Reviewed export

```bash
surface-atlas check SOURCE --policy POLICY \
  --include PATH --include PATH --max-total-bytes N --json
surface-atlas export SOURCE OUTPUT --policy POLICY \
  --include PATH --include PATH --max-total-bytes N --json
```

Each `--include` value is one exact approved relative path. `export` requires a new output directory and writes a checksum manifest unless `--no-manifest` is supplied. See [Export reference](export-reference.md).
