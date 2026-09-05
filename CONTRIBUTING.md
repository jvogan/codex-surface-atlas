# Contributing

Use an editable installation so the CLI and tests run the source you change.
Run these commands from the repository root, which contains `pyproject.toml`.
Python 3.10 or later is required. Install Node.js to run the JavaScript
behavior tests; CI requires it.

On macOS or Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]' build
surface-atlas --version
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e '.[test]' build
.\.venv\Scripts\surface-atlas.exe --version
```

For the commands that follow, use the activated environment's `python`, or
`.\.venv\Scripts\python.exe` on Windows.

## Change the source and its packaged copies

Python implementation and report assets live in `src/surface_atlas/`.
Tests live in `tests/`, and reader documentation lives in `docs/`.

Keep these copies byte-identical when changing a skill, template, or example:

| Content | Locations |
| --- | --- |
| Skill, references, and agent descriptor | `skills/codex-surface-targets/` and `src/surface_atlas/skill/` |
| Workspace templates | Both skill directories' `assets/` and `src/surface_atlas/assets/templates/` |
| Synthetic example | `examples/synthetic-atlas/` and `src/surface_atlas/assets/synthetic-atlas/` |

`tests/test_plugin_layout.py` and `tests/test_package.py` check these copies.
When changing an example's artifacts, update its recorded sizes and SHA-256
values to match the files.

## Check the change

Run the affected tests while editing. Before submitting a change, run the
suite from the repository root:

```bash
python -m pytest
```

For report changes, build an example report and inspect the affected pages,
controls, and downloads in a browser. The [report guide](docs/report.md)
explains report generation and local structure previews.

Follow the [release guide](docs/releasing.md) to update reviewed-file hashes,
check the repository contents, build distributions, and test the installed
wheel outside the checkout. Keep example additions limited to files reviewed
for redistribution.

Describe the behavior changed, the reason for the change, and the checks you
ran in the pull request. Include a reproduction when fixing a bug.
