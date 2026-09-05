from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "check_distribution.py"
SPEC = importlib.util.spec_from_file_location("surface_atlas_distribution_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_portable_example_rejects_original_external_artifact_root(tmp_path: Path) -> None:
    original_artifacts = tmp_path / "original-artifacts"
    original_artifacts.mkdir()
    (original_artifacts / "sequence.fasta").write_text(">example\nACDEFG\n")
    example = tmp_path / "example"
    example.mkdir()
    (example / ".surface-atlas-local.json").write_text(
        json.dumps({"artifact_root": str(original_artifacts)}), encoding="utf-8"
    )
    with pytest.raises(MODULE.DistributionCheckError, match="bundle their artifacts"):
        MODULE.check_portable_example(example)


def test_portable_example_accepts_contained_files(tmp_path: Path) -> None:
    example = tmp_path / "example"
    (example / "artifacts").mkdir(parents=True)
    (example / "artifacts/sequence.fasta").write_text(">example\nACDEFG\n")
    assert MODULE.check_portable_example(example) == example.resolve()


@pytest.mark.parametrize("external", [True, False])
def test_portable_example_checks_nested_artifact_metadata(tmp_path: Path, external: bool) -> None:
    example = tmp_path / "example"
    example.mkdir()
    artifact = {"path": "missing.fasta", "sha256": "0" * 64, "bytes": 10}
    if external:
        artifact["storage"] = "external-artifact-root"
    (example / "results.json").write_text(
        json.dumps({"confirmation": {"per_seed": [{"pose_artifact": artifact}]}}), encoding="utf-8"
    )
    with pytest.raises(MODULE.DistributionCheckError, match="external artifact|missing bundled artifact"):
        MODULE.check_portable_example(example)


def _report(tmp_path: Path, *, link: str = "pages/target.HTM#target") -> Path:
    report = tmp_path / "report"
    (report / "pages").mkdir(parents=True)
    (report / "assets").mkdir()
    (report / "index.html").write_text(
        f'<html><body><a href="{link}">target</a></body></html>',
        encoding="utf-8",
    )
    (report / "pages" / "target.HTM").write_text(
        '<html><body><script src="../assets/app.js"></script>'
        '<h1 id="target">Target</h1></body></html>',
        encoding="utf-8",
    )
    (report / "assets" / "app.js").write_text("console.log('local');\n", encoding="utf-8")
    return report


def test_report_checker_accepts_nested_non_synthetic_pages_and_optimized_cli(tmp_path: Path) -> None:
    report = _report(tmp_path)

    assert MODULE.check_report(report) == 2
    result = subprocess.run(
        [sys.executable, "-O", str(SCRIPT), "--report", str(report)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Report check passed: 2 HTML pages." in result.stdout


@pytest.mark.parametrize(
    ("poster", "create_poster", "message"),
    [
        ("../assets/poster.png", True, None),
        ("../assets/missing-poster.png", False, "missing local report link"),
        ("../../outside-poster.png", False, "report link leaves the report directory"),
    ],
)
def test_report_checker_validates_video_posters(
    tmp_path: Path, poster: str, create_poster: bool, message: str | None
) -> None:
    report = _report(tmp_path)
    (report / "pages" / "target.HTM").write_text(
        f'<html><body><video poster="{poster}"></video>'
        '<h1 id="target">Target</h1></body></html>',
        encoding="utf-8",
    )
    if create_poster:
        (report / "assets" / "poster.png").write_bytes(b"poster")

    if message is None:
        assert MODULE.check_report(report) == 2
    else:
        with pytest.raises(MODULE.DistributionCheckError, match=message):
            MODULE.check_report(report)


def test_report_checker_rejects_base_href(tmp_path: Path) -> None:
    report = _report(tmp_path)
    (report / "data.json").write_text("{}\n", encoding="utf-8")
    (report / "index.html").write_text(
        '<base href="https://example.test/remote/"><a href="data.json">data</a>',
        encoding="utf-8",
    )

    with pytest.raises(MODULE.DistributionCheckError, match="base href"):
        MODULE.check_report(report)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO test requires POSIX")
def test_report_checker_rejects_non_regular_html_file(tmp_path: Path) -> None:
    report = _report(tmp_path)
    fifo = report / "pages" / "stream.html"
    try:
        fifo.touch()
        fifo.unlink()
        os.mkfifo(fifo)
    except OSError:
        pytest.skip("FIFO creation is unavailable")

    with pytest.raises(MODULE.DistributionCheckError, match="not a regular file"):
        MODULE.check_report(report)


@pytest.mark.parametrize(
    ("link", "message"),
    [
        ("assets/missing.js", "missing local report link"),
        ("pages/target.HTM#missing", "missing anchor"),
        ("../outside.html", "report link leaves the report directory"),
    ],
)
def test_report_checker_rejects_missing_assets_anchors_and_path_escape(
    tmp_path: Path, link: str, message: str
) -> None:
    report = _report(tmp_path, link=link)

    with pytest.raises(MODULE.DistributionCheckError, match=message):
        MODULE.check_report(report)


def test_standalone_report_cli_reports_invalid_links_under_optimized_python(tmp_path: Path) -> None:
    report = _report(tmp_path, link="assets/missing.js")

    result = subprocess.run(
        [sys.executable, "-O", str(SCRIPT), "--report", str(report)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "report check failed: missing local report link" in result.stderr
    assert "Traceback" not in result.stderr


def test_synthetic_constraints_remain_opt_in_for_wheel_smoke(tmp_path: Path) -> None:
    report = _report(tmp_path)

    with pytest.raises(MODULE.DistributionCheckError, match="report sections are missing"):
        MODULE.check_report(report, synthetic=True)


@pytest.mark.parametrize("entry_kind", ["file", "directory"])
def test_report_checker_rejects_symlink_entries(tmp_path: Path, entry_kind: str) -> None:
    report = _report(tmp_path)
    outside = tmp_path / "outside"
    if entry_kind == "file":
        outside.write_text("outside", encoding="utf-8")
        link = report / "assets" / "outside.js"
        target_is_directory = False
    else:
        outside.mkdir()
        link = report / "outside-assets"
        target_is_directory = True
    try:
        link.symlink_to(outside, target_is_directory=target_is_directory)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(MODULE.DistributionCheckError, match="report contains a symlink"):
        MODULE.check_report(report)
