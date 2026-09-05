# Publish a report as a ChatGPT Site

Host a completed Surface Atlas report so readers can browse target pages,
inspect structures, and download the supporting files. Start with the report
directory containing `index.html` and specify who should have access.

For a Site tailored to the project, follow
[Compare results and choose the next analysis](compare-and-continue.md).
Lead with findings and useful actions. Add linked sequence, binding-site,
and structure views when the source records support them. Preserve selected
records in downloads and copied Rosalind plugin requests.

```text
Publish this Surface Atlas report as a ChatGPT Site for [AUDIENCE]. Use the
installed Sites building and hosting skills to host the complete static
report. Preserve its target pages, interactive structure previews, downloads,
and Copy Codex request buttons. Check the Site's access policy and test the
deployed pages, direct target links, structures, downloads, and clipboard
behavior in the browser. Return the working URL and its audience.
```

## Package the report

The agent responsible for the Site uses `$sites-building` and `$sites-hosting`
with the installed lifecycle tools. Read those skills for setup, packaging,
source versioning, and deployment requirements. Reuse the selected Site when
updating an existing report.

1. Validate the atlas and generate a report using the [report commands](../cli.md#create-a-report).
2. Copy the complete report directory into the Site's static output directory,
   such as `out/`. Include every HTML page, `assets/`, `data/`, figures, and
   downloadable file. Preserve relative paths.
3. Set `static.directory` to that output directory in `.openai/hosting.json`.
   Use `static.not_found_handling: "none"` for the report's separate HTML
   pages, so missing files return an error. Keep the project ID assigned to
   this Site. Copy only reviewed report files; exclude credentials, private
   machine paths, conversations, and another Site's configuration.
4. Check the copied report's links from the Surface Atlas source checkout:

   ```bash
   python scripts/check_distribution.py --report SITE_DIRECTORY/out
   ```

5. Use the installed Sites packaging helper. Inspect the archive's file count,
   paths, and checksums against the prepared output. Check the connector's
   size limit using expanded bytes as well as compressed archive size.

For large downloads, use separate download assets or gzip files that readers
explicitly download. Preserve each original file's hash, verify decompression,
and update download links and manifests. Keep coordinates and data fetched by
the page in formats its JavaScript can load. After changing scripts or styles,
version their URLs and verify that the deployed browser loads the new files.

## Publish and verify access

Use the user's requested audience and inspect the Site's access policy before
deployment. A new owner-only Site is visible only to its owner. Sharing a URL
requires the corresponding reader access. Follow the installed hosting
workflow for access changes, approvals, version saving, and deployment; wait
for a successful deployment status before reporting publication.

Open the deployed URL and check:

- Overview navigation, target pages opened directly, and links with fragments.
- **View in 3D**, including coordinate loading, chain controls, and rotation.
- Representative JSON, CSV, coordinate, and sequence downloads against their recorded hashes.
- **Copy Codex request**, including manual selection when clipboard access is unavailable.
- Added sequence and comparison controls: change filters, follow a residue into
  3D, return to its sequence, and verify the selected protein and partner.
- Selected-range downloads and copied requests against the accession, isoform,
  chain, residue numbering, and source files shown in the page.
- Access for the intended audience, using an authorized reader session when available.

**Copy Codex request** names report-relative files; copying the prompt does
not transfer them. Give the receiving task the downloaded report bundle, or
the Site URL with an explicit request to retrieve the matching files. Verify
their recorded hashes before opening them in Molecular Structure Viewer.

Report any reader-access check that remains untested, then return the URL and
verified audience. The hosted report contains the generated snapshot; rebuild
and publish another version to update its evidence.

## When to use Data Analytics publishing

`surface-atlas report` produces standalone static HTML. Use the Sites static
workflow for that output. Data Analytics' `$publish-artifact-to-sites` expects
a validated canonical report or dashboard payload and bounded snapshot; it
exports the Data Analytics reader into a worker-starter project. Use that
route when the deliverable was created in Data Analytics' canonical format.
Surface Atlas HTML is not an input to its artifact exporter.
