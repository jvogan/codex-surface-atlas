# Exact sequence-to-site selections

Targets may carry an optional `sequence_sites` object using
`codex-surface-sequence-sites/v0.1`. The Sequence sites report page selects a
one-based inclusive canonical interval by text selection or numeric controls.
It retains partner selections separately for each target. FASTA exports retain
unresolved canonical residues; 3D selections include only verified coordinates.
The portable Codex request includes the same interval, explicit author residue
map, selected partner identities, exact sequence, source IDs, accession/isoform,
model number and SHA-256 hashes. Clipboard failure exposes selectable text.
The request includes the full `canonical_sequence` and its
`canonical_sequence_sha256`, separately from the interval's `sequence` and an
explicit `sequence_scope`. Verify the canonical hash against the full ASCII
sequence, then extract the inclusive interval; do not hash the slice as though
it were the canonical sequence.

The canonical sequence is uppercase ASCII amino acids, without whitespace or
FASTA header. `sequence_sha256` hashes precisely those ASCII bytes. `length`
must match. `accession`, nullable explicit `isoform`, and `source_id` record
identity. They are supplied source claims, not identities inferred from an
alignment. Each extracellular span has inclusive `start`, `end`, `label`, and
`source_id`; an annotation does not establish measured surface exposure.

`coordinates` is a regular relative PDB artifact with `path`, `format: "pdb"`,
`bytes`, and `sha256`. `coordinate_model` is 1 and `numbering` is `"author"`.
Each mapping contains `canonical_position`, `chain`, `author_residue_number`
(integer, including negative author numbers), and `insertion_code` (explicit
empty string when absent). Every canonical residue occurs either in one exact
mapping or in one `unresolved` inclusive span. Duplicate maps, overlaps, missing
coverage, ambiguous residue identities, amino-acid mismatches, symlinks and
unsafe artifact paths fail validation. Alternate conformers must agree on
residue identity; multiple models are rejected. The browser rechecks mapped
amino acids after verifying the coordinate file hash and selects exact atom
indices so insertion-code neighbors cannot enter the selection.
Every protein atom must also have parseable finite X, Y and Z coordinates.
Both workspace validation and the browser reject invalid atom positions.

Each optional partner records `partner_id`, `accession`, `label`, and author
`chain`. Partner chains must exist and must not overlap target chains. Identities
are explicit metadata; the validator verifies chain presence, not biological
identity independently. An empty partner array is valid.

This first contract deliberately supports PDB protein ATOM records only, one
model, single-character nonblank author chains, and standard amino acids plus
selenocysteine/pyrrolysine. It rejects ambiguous or unsupported residues rather
than matching approximately. Existing structure previews retain their mmCIF
support; mmCIF sequence mapping is not silently enabled. For mmCIF inputs,
prepare a separate PDB artifact with a trusted converter, preserving author
chain IDs, residue numbers, insertion codes and the selected model. Record and
hash both original and converted artifacts in the source records. Check the
converted author identities before writing explicit mappings. If those
identities cannot be represented losslessly in PDB, omit this optional feature.

Integration uses `validate_sequence_sites(root, targets, structures=None)` and
must stop on returned errors before rendering. Pass
`sequence_site_artifacts(targets)` through the normal artifact packager, then
call `render_sequence_sites(targets, artifact_map)` for the page body. Include
`sequence-sites.css`, `sequence-sites.js`, and the existing
`structure-preview.js` assets. No third-party runtime dependency, service,
alignment engine, external model call or compute submission is required.
