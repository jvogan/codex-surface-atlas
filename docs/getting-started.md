# Getting started

Install the CLI to create an atlas, check its records, and generate reports.
Add the bundled skill to use Codex for target discovery, evidence review, site
selection, and computational handoffs.

| Component | Use it for |
| --- | --- |
| Skill | Finding surface targets, comparing evidence, selecting sites and molecule formats, and calling the CLI to build the atlas and report. |
| CLI | Initializing an atlas workspace, running the synthetic example, checking records, producing local report files, and exporting reviewed files. |

Surface Atlas requires Python 3.10 or later. On macOS or Linux, create an
isolated environment and install the CLI from a source checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
surface-atlas --version
```

On Windows PowerShell, use the environment executables directly:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\surface-atlas.exe --version
```

For the remaining commands in PowerShell, replace `python` with
`.\.venv\Scripts\python.exe` and `surface-atlas` with
`.\.venv\Scripts\surface-atlas.exe`. Join commands split across lines into
one line, removing the trailing `\` characters.

Install the bundled skill in the current project's Codex discovery directory:

```bash
surface-atlas install-skill \
  --destination .agents/skills/codex-surface-targets --json
```

For a user-wide installation, use `~/.codex/skills/codex-surface-targets` as the destination. The installer records the files it manages and refuses to replace another directory.

## Choose an entry point

For a research project, give Codex the disease state, population or model,
intended use, evidence cutoff, and molecule formats to consider. Include any
limits on data handling or compute. The skill records these in the atlas plan
before gathering evidence.

For an existing atlas or automated validation, use the CLI directly.

Start a new Codex task after installation. Invoke `$codex-surface-targets`, or describe the disease-state question and the requested output.

Virtual-environment activation applies to the terminal where you ran it. If
Codex cannot find `surface-atlas`, give it the installed executable's path.
For the source-checkout installation, use `.venv/bin/surface-atlas` on macOS
or Linux, or `.venv/Scripts/surface-atlas.exe` on Windows. These paths are
relative to the checkout where you installed the CLI; when working elsewhere,
provide the path to that installation.

```text
Disease state      -> skill finds surface targets and compares their evidence
Ligand library     -> skill separates known relationships from planned screens
Atlas directory    -> CLI validates records and builds a local report
```

## Run the synthetic example

Run this first to check the installed CLI. Create the synthetic example at a
new output location, validate it, and build a local report:

```bash
surface-atlas example ./surface-atlas-synthetic --json
surface-atlas validate ./surface-atlas-synthetic --json
surface-atlas report ./surface-atlas-synthetic \
  --output-root ./surface-atlas-reports --run-id synthetic-demo --json
```

Open `./surface-atlas-reports/synthetic-surface-atlas/synthetic-demo/index.html`. The example writes only beneath the output directory you choose and refuses an existing destination.

The invented records include a target census, source references, normal-tissue
signals, molecule-format choices, and structures. Open the target pages to
inspect them.

## Start a campaign

Create a new workspace for your research:

```bash
surface-atlas init disease-surface-atlas ./disease-surface-atlas \
  --disease "DISEASE STATE" --profile standard \
  --evidence-cutoff YYYY-MM-DD --json
```

The initializer writes `atlas-plan.json`, `search-ledger.json`, and empty
required collections, including `opportunities.json`. Add the disease brief,
source coverage, target decisions, and evidence records to this new directory.

## Upgrade the CLI and skill

Remove a managed skill with the package build that installed it, then upgrade
the CLI and reinstall the skill at the same destination:

```bash
surface-atlas uninstall-skill \
  --destination .agents/skills/codex-surface-targets --json
python -m pip install --upgrade .
surface-atlas install-skill \
  --destination .agents/skills/codex-surface-targets --json
```

If the CLI was upgraded first, create an isolated environment containing the
original package build, use that environment's `surface-atlas uninstall-skill`
command with the original destination, then reinstall from the current build.
This preserves the installer manifest and file-integrity checks.

## Remove the bundled skill

Remove the skill at its exact installation destination:

```bash
surface-atlas uninstall-skill \
  --destination .agents/skills/codex-surface-targets --json
```

Use the same destination selected at installation. For a user-wide installation, that is `~/.codex/skills/codex-surface-targets`.

Remove the CLI when it is no longer needed:

```bash
python -m pip uninstall codex-surface-atlas
```

Removing the skill leaves the CLI available for existing workspaces. Removing the CLI means the skill's local workspace commands are unavailable until the package is installed again.

See [Workflow](workflow.md), [Evidence and decisions](evidence-and-decisions.md), and the [CLI reference](cli.md).
