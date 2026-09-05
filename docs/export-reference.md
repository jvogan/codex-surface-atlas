# Export reference

The exporter creates a public snapshot from files that have already been reviewed. It does not redact or anonymize source material.

The repository policy lists the reviewed package files and their hashes. To prepare another snapshot, create a separate policy and add one entry for every approved file:

```json
{
  "version": 1,
  "limits": {
    "max_files": 25,
    "max_file_bytes": 1000000,
    "max_total_bytes": 5000000
  },
  "deny_terms": [],
  "files": [
    {
      "path": "examples/synthetic-atlas/targets.json",
      "sha256": "<lowercase SHA-256 from the reviewed file>",
      "kind": "json"
    }
  ]
}
```

Paths are exact POSIX relative file paths. Directory wildcards, parent traversal, absolute paths, symlinks, cache and private-data directories, duplicate entries, empty selections, and unlisted requested files are rejected. Each entry requires the hash of the reviewed bytes. A changed file must be reviewed again and receive a new policy hash.

Supported text kinds are `json`, `json-schema`, `json-template`, `csv`, `tabular`,
`molecular-text`, `text`, `python`, `javascript`, `css`, `html`, `svg`, `excalidraw`,
`config`, and `license`. Use `tabular` for TSV files and `molecular-text` for reviewed
`.cif`, `.pdb`, `.sdf`, `.smi`, `.smiles`, `.fasta`, and `.fa` files. These receive UTF-8 and sensitive-content
checks; the exporter does not validate their scientific meaning or file-format semantics.
Text files must be UTF-8 and use a matching extension or approved configuration
or license filename. Python, JSON/Excalidraw, JSON Schema, CSV/TSV, and SVG receive
syntax or format checks.

Use `"kind": "html"` for reviewed `.html` or `.htm` report pages. The checker
inspects raw markup, decoded text and attributes, and embedded JSON. Each HTML
page still needs its exact reviewed hash. Include its CSS, JavaScript, data,
and images as separate policy entries, then check links in the exported report.

A `json-template` may use uppercase `__PLACEHOLDER__` values; the checker
substitutes neutral values before parsing and applies the JSON field checks.
A `json-schema` is parsed as JSON, with property declarations treated as schema
metadata. Empty schema and template fields do not count as exported records.

Credential fields and values, absolute workstation paths, provider receipts,
message logs, and sensitive identifier fields stop the export. Review every
file before approving its hash; automated checks cover the documented formats
and detection patterns.

Add sensitive identifiers and names to `deny_terms` in a separate release policy. Terms are matched without case, but their values are not printed in findings or written to the export manifest. Do not add them to the repository's public policy.

Reviewed Python, JavaScript, or CSS files may need to contain a detector fixture that deliberately resembles a blocked value. Such an entry may add an `allow_findings` array containing the exact finding codes accepted during review. Exceptions are limited to content findings, apply only while the file hash matches, and are listed as `review_exceptions` in the manifest. Syntax errors, traversal, symlinks, missing files, size limits, and hash mismatches cannot be excepted.

An unknown or binary format is accepted only when its entry says `"kind": "binary"`, includes the reviewed SHA-256, and sets `"reviewed_binary": true`. Binary contents are hash-checked but cannot receive text-content checks. The manifest records that limit as a review exception.

Run a check before deciding where to publish a bundle. The report includes every selected file's byte count and hash, total content bytes, and the estimated JSON manifest size. `max_total_bytes` may lower the policy cap for a particular check. It may not raise the policy's per-file or file-count limits.

Export requires a destination directory that does not exist. Files are staged beside the destination, copied without following symlinks, hash-verified again, and moved into place only after every copy succeeds. A failed run removes its staging directory and leaves no partial destination. The optional `surface-atlas-export.json` records relative paths, kinds, sizes, and hashes without recording the source location.

For a future campaign example, first make a separate reviewed snapshot with only the intended files, record their exact hashes in a release policy, and run the check. Use the size report to decide whether the reviewed snapshot belongs in the package or in separate release assets. Keep the raw records outside both destinations.
