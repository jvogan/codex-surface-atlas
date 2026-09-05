# Synthetic screen merge fixture

These two invented collections use the same target, site, and molecule IDs in
two independent planned runs. Each run has one prospective record and one
reference-control record. The records have no scores because neither run has
executed.

The merge keeps each run ID, result ID, control role, and confirmation context.
Each input summary reports `execution_complete: false`, and the merged records
keep the claim ceiling at `computational-screening-hypothesis`. A merged file
does not turn a planned record into a measured result.

Create a new merged file and inspect its report from one temporary atlas copy:

```bash
workdir="$(mktemp -d)"
surface-atlas merge-screens \
  examples/screen-merge/run-a.json \
  examples/screen-merge/run-b.json \
  --output "$workdir/screening-results.json"
# Use a new copy so the merge does not replace an existing atlas file.
surface-atlas example "$workdir/atlas"
cp "$workdir/screening-results.json" "$workdir/atlas/screening-results.json"
surface-atlas validate "$workdir/atlas"
surface-atlas report "$workdir/atlas" \
  --output-root "$workdir/reports" \
  --run-id merged-screening \
  --json
```

Open `$workdir/reports/synthetic-surface-atlas/merged-screening/screening.html`
to inspect the merged screen runs and their confirmation contexts.

The commands write only under `workdir`, so the checked-in inputs and any atlas
you already have remain unchanged.

On Windows PowerShell, run the same example with PowerShell paths:

```powershell
$workdir = Join-Path ([System.IO.Path]::GetTempPath()) ("surface-atlas-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $workdir | Out-Null
surface-atlas merge-screens `
  examples/screen-merge/run-a.json `
  examples/screen-merge/run-b.json `
  --output (Join-Path $workdir "screening-results.json")
surface-atlas example (Join-Path $workdir "atlas")
Copy-Item (Join-Path $workdir "screening-results.json") (Join-Path $workdir "atlas/screening-results.json")
surface-atlas validate (Join-Path $workdir "atlas")
surface-atlas report (Join-Path $workdir "atlas") `
  --output-root (Join-Path $workdir "reports") `
  --run-id merged-screening `
  --json
Start-Process (Join-Path $workdir "reports/synthetic-surface-atlas/merged-screening/screening.html")
```
