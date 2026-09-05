#!/usr/bin/env python3
"""Exercise a built wheel or validate report-local links."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import stat
import tempfile
from urllib.parse import unquote, urlsplit
import venv
from zipfile import ZipFile


class DistributionCheckError(AssertionError):
    """Raised when a distribution or report fails a release check."""


def _require(condition: bool, message: str) -> None:
    """Keep release checks active under ``python -O``."""

    if not condition:
        raise DistributionCheckError(message)


class Page(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.links: list[str] = []
        self.base_hrefs: list[str] = []
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag.casefold() == "base" and values.get("href"):
            self.base_hrefs.append(values["href"])
        for key in ("href", "src"):
            if values.get(key):
                self.links.append(values[key])
        if tag.casefold() == "video" and values.get("poster"):
            self.links.append(values["poster"])


def check_report(directory: Path, *, synthetic: bool = False) -> int:
    """Check report-local HTML links, fragments, and duplicate IDs.

    The wheel smoke check passes ``synthetic=True`` to retain its stronger
    synthetic-report expectations. Standalone checks accept any non-empty
    report directory and recurse through nested HTML pages.
    """

    source = Path(directory)
    _require(not source.is_symlink(), "report directory must not be a symlink")
    root = source.resolve()
    _require(root.is_dir(), "report directory does not exist")

    def report_walk_error(error: OSError) -> None:
        raise DistributionCheckError("could not inspect report directory") from error

    page_paths: list[Path] = []
    for current, directories, files in os.walk(root, followlinks=False, onerror=report_walk_error):
        current_path = Path(current)
        for name in (*directories, *files):
            candidate = current_path / name
            _require(not candidate.is_symlink(),
                     f"report contains a symlink: {candidate.relative_to(root)}")
        page_paths.extend(
            current_path / name
            for name in files
            if Path(name).suffix.casefold() in {".html", ".htm"}
        )
    pages: dict[Path, tuple[Page, str]] = {}
    for path in page_paths:
        resolved = path.resolve()
        _require(resolved.is_relative_to(root),
                 f"report page leaves the report directory: {path.name}")
        try:
            _require(stat.S_ISREG(path.stat().st_mode),
                     f"report page is not a regular file: {path.relative_to(root)}")
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DistributionCheckError(
                f"could not read report page {path.relative_to(root)}"
            ) from exc
        pages[resolved] = (Page(text), text)
    _require(pages, "report contains no HTML pages")
    if synthetic:
        _require(len(pages) >= 10, "report sections are missing")
    for path, (page, text) in pages.items():
        _require(len(page.ids) == len(set(page.ids)), f"duplicate HTML ID in {path.name}")
        _require(not page.base_hrefs, "report must not contain a <base href>")
        if synthetic:
            _require("Synthetic example." in text, path.name)
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                _require(url.scheme in {"http", "https", "mailto"}, "unsupported report link scheme")
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            _require(target.is_relative_to(root), "report link leaves the report directory")
            _require(target.is_file(), f"missing local report link in {path.name}")
            if url.fragment and target in pages:
                _require(unquote(url.fragment) in pages[target][0].ids,
                         f"missing anchor in {path.name}")
    return len(pages)


def check_portable_example(directory: Path) -> Path:
    """Require an example whose artifacts travel with the source directory."""
    source = Path(directory)
    root = source.resolve()
    _require(not source.is_symlink() and root.is_dir(),
             "example must be a regular directory")
    _require(not (root / ".surface-atlas-local.json").exists(),
             "portable examples must bundle their artifacts without local artifact-root settings")
    for path in root.rglob("*"):
        _require(not path.is_symlink(), "example contains a symlink")
        _require(path.is_dir() or stat.S_ISREG(path.stat().st_mode),
                 "example contains a special file")
    checked_artifacts: dict[Path, tuple[str, int]] = {}

    def check_value(value: object, document: str) -> None:
        if isinstance(value, dict):
            _require(value.get("storage") != "external-artifact-root",
                     f"external artifact reference in {document}")
            if isinstance(value.get("path"), str) and "sha256" in value:
                relative = Path(value["path"])
                _require(not relative.is_absolute() and ".." not in relative.parts,
                         f"artifact path leaves example in {document}")
                artifact = root / relative
                _require(artifact.resolve().is_relative_to(root) and artifact.is_file(),
                         f"missing bundled artifact in {document}")
                if artifact not in checked_artifacts:
                    content = artifact.read_bytes()
                    checked_artifacts[artifact] = (hashlib.sha256(content).hexdigest(), len(content))
                digest, length = checked_artifacts[artifact]
                _require(value["sha256"] == digest, f"artifact hash mismatch in {document}")
                if "bytes" in value:
                    _require(type(value["bytes"]) is int and value["bytes"] == length,
                             f"artifact byte count mismatch in {document}")
            for item in value.values():
                check_value(item, document)
        elif isinstance(value, list):
            for item in value:
                check_value(item, document)

    for path in root.rglob("*.json"):
        check_value(json.loads(path.read_text(encoding="utf-8")), path.relative_to(root).as_posix())
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", type=Path, help="wheel to install and exercise")
    parser.add_argument("--report", type=Path, metavar="DIRECTORY",
                        help="check an existing report directory without installing a wheel")
    parser.add_argument("--example", type=Path, metavar="DIRECTORY",
                        help="also copy and exercise a research example with the installed wheel")
    args = parser.parse_args()
    if args.wheel is None and args.report is None:
        parser.error("provide a wheel path or --report DIRECTORY")
    if args.wheel is not None and args.report is not None:
        parser.error("choose a wheel path or --report DIRECTORY, not both")
    if args.example is not None and args.wheel is None:
        parser.error("--example requires a wheel path")
    if args.report is not None:
        try:
            pages = check_report(args.report)
        except DistributionCheckError as exc:
            parser.exit(1, f"report check failed: {exc}\n")
        print(f"Report check passed: {pages} HTML pages.")
        return

    wheel = args.wheel.resolve()
    example = check_portable_example(args.example) if args.example is not None else None
    research_pages = 0
    with ZipFile(wheel) as bundle:
        names = bundle.namelist()
        for required in ("surface_atlas/skill/SKILL.md", "surface_atlas/skill/agents/openai.yaml",
                         "surface_atlas/assets/report/presentation.js",
                         "surface_atlas/assets/report/diagrams.css", "surface_atlas/report_diagrams.py",
                         "surface_atlas/diagram_routes.py",
                         "surface_atlas/assets/synthetic-atlas/atlas-plan.json"):
            _require(required in names, f"missing wheel resource: {required}")
        for schema in ("atlas-plan", "collection", "search-ledger"):
            _require(any(name.endswith(f"/schemas/v0.1/{schema}.schema.json") for name in names), schema)
        _require(any(name.endswith("/licenses/LICENSE") for name in names), "license missing from wheel")

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="surface-atlas-distribution-") as temporary:
        root = Path(temporary).resolve()
        venv.EnvBuilder(with_pip=True).create(root / "venv")
        binary = root / "venv" / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        cli = binary / ("surface-atlas.exe" if os.name == "nt" else "surface-atlas")

        def run(*command: str) -> str:
            result = subprocess.run(command, cwd=root, env=environment, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError(f"distribution check failed: {command[0]}\n{result.stderr}")
            return result.stdout

        run(str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", str(wheel))
        run(str(cli), "--version")
        run(str(cli), "init", "installation-check", "empty-atlas", "--disease", "Example research question", "--json")
        _require(json.loads(run(str(cli), "validate", "empty-atlas", "--json"))["valid"],
                 "empty atlas validation failed")
        run(str(cli), "example", "example", "--json")
        _require(json.loads(run(str(cli), "validate", "example", "--json"))["valid"],
                 "synthetic example validation failed")
        (root / "supplied.csv").write_text(
            "id,name,smiles\nM-SUPPLIED,Supplied example compound,C\n", encoding="utf-8"
        )
        (root / "supplied.fasta").write_text(
            ">P-SUPPLIED\nACDEFG\n", encoding="utf-8"
        )
        registration = {
            "schema_version": "surface-atlas-supplied-library-registration/v1",
            "atlas_id": "synthetic-surface-atlas",
            "library_id": "supplied-example",
            "inputs": [
                {"input_library_id": "compound-input", "format": "csv",
                 "molecular_class": "small-molecule", "path": "supplied.csv",
                 "id_column": "id", "name_column": "name", "smiles_column": "smiles"},
                {"input_library_id": "sequence-input", "format": "fasta",
                 "molecular_class": "peptide", "path": "supplied.fasta"},
            ],
        }
        (root / "registration.json").write_text(json.dumps(registration), encoding="utf-8")
        run(str(cli), "register-library", "registration.json", "--output", "supplied-library", "--json")
        library_bytes = (root / "supplied-library/molecular-library.json").read_bytes()
        library = json.loads(library_bytes)
        _require(library["record_count"] == 2, "supplied library records are missing")
        (root / "example/molecular-library.json").write_bytes(library_bytes)
        (root / "example/.surface-atlas-local.json").write_text(
            json.dumps({"artifact_root": str(root / "supplied-library")}), encoding="utf-8"
        )
        _require(json.loads(run(str(cli), "validate", "example", "--json"))["valid"],
                 "registered library does not validate in an atlas")
        for name in ("a", "b"):
            screen = {
                "schema_version": "codex-surface-screening-result-collection/v0.1",
                "atlas_id": "synthetic-surface-atlas",
                "claim_ceiling": "computational-screening-hypothesis",
                "source_run": {"run_id": f"run-{name}"},
                "summary": {"execution_complete": False},
                "confirmation_context": {"requested": True, "completed": False},
                "records": [{"screening_result_id": f"result-{name}", "run_id": f"run-{name}",
                             "target_id": "T-EMBER", "execution_state": "planned", "pose_score": None}],
            }
            (root / f"screen-{name}.json").write_text(json.dumps(screen), encoding="utf-8")
        run(str(cli), "merge-screens", "screen-a.json", "screen-b.json", "--output", "merged.json", "--json")
        merged = json.loads((root / "merged.json").read_text(encoding="utf-8"))
        _require(len(merged["source_runs"]) == 2 and len(merged["confirmation_contexts"]) == 2,
                 "screening provenance was not retained")
        _require(all(record["pose_score"] is None for record in merged["records"]),
                 "planned screening records gained scores")
        (root / "example/screening-results.json").write_text(json.dumps(merged), encoding="utf-8")
        report = json.loads(run(str(cli), "report", "example", "--output-root", "reports", "--run-id", "check", "--json"))
        _require(report["provider_calls"] is False and report["external_urls_fetched"] is False,
                 "report performed external work")
        pages = check_report(root / report["run_directory"], synthetic=True)
        screening_export = root / report["run_directory"] / "data/screening-results.json"
        _require(json.loads(screening_export.read_text(encoding="utf-8")) == merged,
                 "report changed screening provenance")

        # The synthetic report is reviewed test data. Exercise every report file
        # through the same exact-path export checks used for example bundles.
        report_root = root / report["run_directory"]
        report_files = sorted(path for path in report_root.rglob("*") if path.is_file())
        _require(any(path.suffix == ".fasta" for path in report_files),
                 "report omitted the registered sequence source")
        report_kinds = {".html": "html", ".json": "json", ".csv": "csv",
                        ".css": "css", ".js": "javascript", ".fasta": "molecular-text",
                        ".fa": "molecular-text", ".sdf": "molecular-text",
                        ".smi": "molecular-text", ".smiles": "molecular-text",
                        ".pdb": "molecular-text", ".cif": "molecular-text",
                        ".txt": "text", ".md": "text", ".svg": "svg"}
        report_policy = {
            "version": 1,
            "limits": {"max_files": len(report_files),
                       "max_file_bytes": max(path.stat().st_size for path in report_files),
                       "max_total_bytes": sum(path.stat().st_size for path in report_files)},
            "deny_terms": [],
            "files": [{"path": path.relative_to(report_root).as_posix(),
                       "kind": report_kinds[path.suffix],
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in report_files],
        }
        (root / "report-policy.json").write_text(json.dumps(report_policy), encoding="utf-8")
        checked_report = json.loads(run(str(cli), "check", str(report_root),
                                        "--policy", "report-policy.json", "--json"))
        _require(checked_report["ok"] and checked_report["file_count"] == len(report_files),
                 "report export policy check failed")
        run(str(cli), "export", str(report_root), "exported-report",
            "--policy", "report-policy.json", "--json")
        _require(check_report(root / "exported-report", synthetic=True) == pages,
                 "exported report page count changed")
        report_manifest = json.loads((root / "exported-report/surface-atlas-export.json").read_text())
        _require(all(not entry.get("review_exceptions") for entry in report_manifest["files"]),
                 "report export requires review exceptions")
        _require(json.loads(run(str(cli), "install-skill", "--destination", "skill", "--json"))["installed"],
                 "skill installation failed")
        _require((root / "skill/SKILL.md").is_file(), "installed skill is incomplete")
        _require(json.loads(run(str(cli), "uninstall-skill", "--destination", "skill", "--json"))["removed"],
                 "skill uninstall failed")
        _require(not (root / "skill").exists(), "skill installation remains after uninstall")

        source = root / "approved"
        source.mkdir()
        payload = b'{"example": "synthetic"}\n'
        (source / "example.json").write_bytes(payload)
        policy = {"version": 1, "limits": {"max_files": 1, "max_file_bytes": 1024, "max_total_bytes": 1024},
                  "deny_terms": [], "files": [{"path": "example.json", "kind": "json",
                  "sha256": hashlib.sha256(payload).hexdigest()}]}
        (root / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        run(str(cli), "check", "approved", "--policy", "policy.json", "--json")
        run(str(cli), "export", "approved", "exported", "--policy", "policy.json", "--json")
        _require((root / "exported/example.json").read_bytes() == payload,
                 "exported file changed")
        _require((root / "exported/surface-atlas-export.json").is_file(),
                 "export manifest is missing")
        if example is not None:
            copied = root / "research-example"
            shutil.copytree(example, copied, symlinks=True)
            check_portable_example(copied)
            _require(json.loads(run(str(cli), "validate", str(copied), "--json"))["valid"],
                     "relocated research example validation failed")
            research = json.loads(run(str(cli), "report", str(copied),
                                      "--output-root", "research-reports", "--run-id", "check", "--json"))
            _require(research["provider_calls"] is False and research["external_urls_fetched"] is False,
                     "research report performed external work")
            research_pages = check_report(root / research["run_directory"])
    print(f"Wheel installation passed: CLI, schemas, skill lifecycle, library registration, screening merge, {pages} report pages, and complete report export.")
    if example is not None:
        print(f"Relocated research example passed: validation and {research_pages} report pages.")


if __name__ == "__main__":
    main()
