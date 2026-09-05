"""Schema identifiers used by the portable Surface Atlas workspace.

The package keeps the workspace contract provider free.  These identifiers
are intentionally the same versioned values used by the research workbench so
that a workspace can move between the two without a schema translation step.
"""

from __future__ import annotations


PLAN_SCHEMA = "codex-surface-atlas-plan/v0.1"
SEARCH_LEDGER_SCHEMA = "codex-surface-search-ledger/v0.1"

COLLECTION_SCHEMAS: dict[str, str] = {
    "discovered-entities.json": "codex-surface-discovered-entity-collection/v0.1",
    "targets.json": "codex-surface-target-collection/v0.1",
    "excluded-targets.json": "codex-surface-exclusion-collection/v0.1",
    "interventions.json": "codex-surface-intervention-collection/v0.1",
    "molecular-library.json": "codex-surface-molecular-library/v0.1",
    "screening-results.json": "codex-surface-screening-result-collection/v0.1",
    "structures.json": "codex-surface-structure-collection/v0.1",
    "opportunities.json": "codex-surface-opportunity-collection/v0.1",
    "capabilities.json": "codex-surface-capability-collection/v0.1",
}

REQUIRED_WORKSPACE_SCHEMAS: dict[str, str] = {
    "atlas-plan.json": PLAN_SCHEMA,
    "search-ledger.json": SEARCH_LEDGER_SCHEMA,
    **COLLECTION_SCHEMAS,
}

REPORT_SCHEMA = "codex-surface-report-run/v0.1"
STRUCTURE_SNAPSHOT_SCHEMA = "codex-surface-structure-snapshot/v0.1"
