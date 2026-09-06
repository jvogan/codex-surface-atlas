# Prepare a release

Build the source archive and wheel, test the installed package, and select the files intended for publication.

## Test the distribution

Use Python 3.10 or later in an activated virtual environment. In the source checkout:

1. Install the test and build tools:

   ```bash
   python -m pip install '.[test]' build
   ```

2. Run the tests and build the distributions:

   ```bash
   python -m pytest
   python -m build
   ```

   The default build creates a source archive, then builds the wheel from that archive.

3. Check the complete source archive inventory and every reviewed file hash,
   including Git settings and the CI workflow:

   ```bash
   python scripts/check_source_archive.py dist/codex_surface_atlas-0.1.0.tar.gz
   ```

4. Check the wheel named in the build output:

   ```bash
   python scripts/check_distribution.py dist/codex_surface_atlas-0.1.0-py3-none-any.whl \
     --example examples/research-case
   ```

   Both archive checks use the checkout's `export-policy.json` as the trusted
   review record; use `--policy PATH` to select another reviewed policy. The
   source archive must contain that exact policy and every reviewed file.
   Extra files are rejected except the explicitly named setuptools metadata
   files. The wheel maps reviewed package sources, schemas, and license files
   to their installation paths, verifies their hashes, rejects extra payloads,
   and checks the complete wheel RECORD inventory and hashes. Generated build
   metadata is narrowly allowed; these checks do not independently establish
   the trustworthiness of the build backend. Review build inputs and metadata.

   The check installs the wheel in a temporary environment outside the checkout.
   It exercises workspace creation, validation, screening merges, reports, and
   skill installation and removal. It exports the complete synthetic report
   through an exact-file policy and checks links in the exported copy. It also
   verifies retained run provenance and packaged resources. With `--example`,
   it copies the research workspace into the temporary directory, validates
   the copy with the installed CLI, builds its report, and checks local links.
   The example must include its required files. The check rejects machine-local
   artifact configuration, symlinks, and special files.

   The installed tutorial additionally exercises evidence reconciliation,
   independent binder-run import, exact assay joins, sequence/site resources,
   action comparison, and all linked pages. Its observations are synthetic.

   To check an already exported report bundle without installing a wheel, run
   the reusable local-link checker against the directory containing its HTML
   pages:

   ```bash
   python scripts/check_distribution.py --report ../surface-atlas-release/report
   ```

   This recursively checks `.html` and `.htm` pages, local `href` and `src`
   targets, fragments, duplicate IDs, path containment, and symlink safety.
   The standalone mode does not require the synthetic example label or page
   count used by the wheel smoke check.

The Test workflow runs these checks on Linux, macOS, and Windows. Review the completed workflow results for the release revision before publishing it.

## Select release files

1. Review each file intended for publication, including figures and example downloads. Confirm that third-party material permits redistribution and retains its required attribution.
2. Record the reviewed files and their SHA-256 values in an export policy. Keep sensitive deny terms in a separate local policy. Use the [export reference](export-reference.md) for the policy format.
3. Check the selected files, then export them to a new directory:

   ```bash
   surface-atlas check . --policy release-policy.json --json
   surface-atlas export . ../surface-atlas-release --policy release-policy.json --json
   ```

4. Inspect the exported tree and manifest. Build and test the distribution from that tree. Publish the reviewed tree and distribution files after all checks pass.

The repository's `export-policy.json` pins the package files at review time. Any content change requires new hashes. A separate release policy can include that public policy file without requiring it to hash itself.

## Check the Git source tree

The remote repository must contain the files listed in `export-policy.json`,
plus that policy file. After reviewing changes, update the affected hashes
and stage the intended files. Run:

```bash
python scripts/check_repository.py
```

The check compares tracked paths with the policy, verifies staged bytes
against working files, and runs the export content checks. It rejects extra
tracked files, missing files, changed hashes, symlinks, and unresolved merge
entries. It also scans the policy's contents, which cannot include a hash of
itself. CI runs this check before the test suite. This Git check intentionally
covers tracked files only. Untracked files can still match packaging globs;
always run both archive inventory checks before publication, and build from a
clean reviewed export tree. A passing repository check alone does not approve
a distribution.

Keep private deny terms in a separate local release policy. The repository's
policy contains only the rules and paths suitable for distribution. Generated
workspaces, reports, and export inventories are excluded from Git by default.
The `.gitattributes` file preserves LF line endings for reviewed text files
across operating systems.

## Add a research example

The repository includes [a three-target research example](../examples/research-case/README.md)
under `examples/research-case`. Its artifact manifest records the files needed
to reproduce the report. Use the wheel check above to verify this example
outside the checkout.

Choose a completed example that explains a specific research question. Prepare a separate snapshot containing the disease brief, selected target records, public source citations, decisions, and results used in the report.

Record the review date and distinguish source observations, model results, and proposed work. Check source licenses and remove personal identifiers, machine paths, service logs, and credentials before selecting export files.

Keep the navigable report and small supporting files together. Place large coordinate sets or other downloads in separate release assets with their byte sizes and SHA-256 values. Include the files required by each report link, then test the example after moving it to a clean directory.

From the source checkout, check the copied report's local HTML links and anchors:

```bash
python scripts/check_distribution.py --report ../reviewed-example
```

The check includes nested HTML pages and rejects missing linked files, duplicate
HTML IDs, symlinks, and local links that leave the report directory. It does not
fetch external URLs.

## Before making a repository public

Review the full Git history and release assets separately from the current
source tree. The file policy does not inspect earlier commits or remote assets.
Confirm redistribution rights and remove any sensitive material before changing
visibility. Review `SECURITY.md` and decide whether to enable GitHub private
vulnerability reporting; verify the private reporting form after enabling it.
No release check or documentation change enables that remote feature.

For the public default branch, require the seven `test` matrix checks in the
Test workflow, require branches to be current before merging, disallow force
pushes and deletion, and require conversations to be resolved. Apply the same
checks to administrators. Choose a review requirement that matches the actual
maintainer team; do not configure an impossible sole-maintainer approval gate.
Verify the required check names against a completed workflow for that branch.

Enable private vulnerability reporting, Dependabot alerts, secret scanning,
and push protection when the repository's visibility and plan make those
features available. Verify each setting after changing visibility; a checked-in
policy or a successful CI run does not configure GitHub repository settings.

Use [the 0.1.0 release notes](release-notes-0.1.0.md) for the initial alpha.
Attach the verified wheel, source archive, and their SHA-256 checksums to a
versioned release only after its exact revision passes CI and publication is
authorized. Keep the tutorial clearly synthetic in release screenshots.
