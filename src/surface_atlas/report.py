"""Build an offline Surface Atlas report from a local workspace."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from . import report_builder


class ReportError(RuntimeError):
    """Raised when report generation fails."""


def build_report(
    atlas_directory: str | Path,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build a self-contained report and return its machine-readable result.

    Report generation is local and provider free.  The report builder refuses
    to overwrite an existing run directory, so callers can safely rerun with
    a new run identifier while retaining previous snapshots.
    """

    argv = [str(atlas_directory)]
    if output_root is not None:
        argv.extend(["--output-root", str(output_root)])
    if run_id is not None:
        argv.extend(["--run-id", run_id])
    argv.append("--json")
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = report_builder.main(argv)
    if exit_code:
        detail = stderr.getvalue().strip() or stdout.getvalue().strip() or "report generation failed"
        raise ReportError(detail)
    try:
        result = json.loads(stdout.getvalue())
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        raise ReportError("report builder did not produce JSON") from exc
    result["exit_code"] = exit_code
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI-compatible entry point used by ``surface-atlas report``."""

    return report_builder.main(argv)

