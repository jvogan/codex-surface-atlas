# Surface Atlas schemas

The package keeps the versioned workspace envelopes in these JSON Schema
documents and applies cross-file identity, accounting, artifact, and tier
checks with `surface-atlas validate`. The schemas intentionally leave record
fields extensible so a disease scope can add evidence fields without changing
the collection envelope. The validator remains authoritative for relationships
between files and for safe local artifact paths.

| Document | Envelope |
| --- | --- |
| [v0.1/atlas-plan.schema.json](v0.1/atlas-plan.schema.json) | `codex-surface-atlas-plan/v0.1` |
| [v0.1/search-ledger.schema.json](v0.1/search-ledger.schema.json) | `codex-surface-search-ledger/v0.1` |
| [v0.1/collection.schema.json](v0.1/collection.schema.json) | The nine collection identifiers listed in the schema |

`v0.1` is the canonical schema directory. The wheel installs these same files
under `share/codex-surface-atlas/schemas/v0.1` in the Python environment.
