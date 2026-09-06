"""Command line interface for the provider-free Surface Atlas package."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .export import ExportError, check_repository, export_subset
from .workspace import WorkspaceError, initialize_atlas


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="surface-atlas", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a provider-free atlas workspace")
    init.add_argument("atlas_id")
    init.add_argument("output_directory", type=Path)
    init.add_argument("--disease", required=True)
    init.add_argument("--profile", choices=("showcase", "standard", "broad"), default="standard")
    init.add_argument("--evidence-cutoff")
    init.add_argument("--json", action="store_true", dest="json_output")

    example = commands.add_parser("example", help="create a synthetic example workspace")
    example.add_argument("output_directory", type=Path)
    example.add_argument("--json", action="store_true", dest="json_output")

    tutorial = commands.add_parser("tutorial", help="create the complete reproducible offline research tutorial")
    tutorial.add_argument("output_directory", type=Path)
    tutorial.add_argument("--json", action="store_true", dest="json_output")

    evidence = commands.add_parser("ingest-evidence", help="compile reviewed local source snapshots into a new atlas")
    evidence.add_argument("inputs", nargs="+", type=Path)
    evidence.add_argument("--atlas", required=True, type=Path)
    evidence.add_argument("--output", required=True, type=Path, metavar="NEW_DIRECTORY")
    evidence.add_argument("--json", action="store_true", dest="json_output")

    reconcile = commands.add_parser("reconcile-evidence", help="check source projections and reconcile ledger counts")
    reconcile.add_argument("atlas_directory", type=Path)
    reconcile.add_argument("--output", type=Path, metavar="NEW_LEDGER_JSON")
    reconcile.add_argument("--json", action="store_true", dest="json_output")

    for command, help_text in (("import-binder-runs", "validate and bundle supplied binder runs with their artifacts"),
                               ("import-assays", "validate and bundle supplied assay returns against exact constructs")):
        intake = commands.add_parser(command, help=help_text)
        intake.add_argument("inputs", nargs="+" if command == "import-binder-runs" else None, type=Path)
        intake.add_argument("--atlas", required=True, type=Path)
        intake.add_argument("--output", type=Path, metavar="NEW_BUNDLE_DIRECTORY", help="omit for validation only")
        intake.add_argument("--json", action="store_true", dest="json_output")

    validate = commands.add_parser("validate", help="validate an atlas workspace offline")
    validate.add_argument("atlas_directory", type=Path)
    validate.add_argument("--json", action="store_true", dest="json_output")

    report = commands.add_parser("report", help="build an offline report")
    report.add_argument("atlas_directory", type=Path)
    report.add_argument("--output-root", type=Path)
    report.add_argument("--run-id")
    report.add_argument("--json", action="store_true", dest="json_output")

    merge_screens = commands.add_parser(
        "merge-screens", help="merge screening collections without combining scores"
    )
    merge_screens.add_argument("inputs", nargs="+", type=Path)
    merge_screens.add_argument("--output", required=True, type=Path)
    merge_screens.add_argument("--json", action="store_true", dest="json_output")

    register_library = commands.add_parser(
        "register-library", help="register supplied molecules and sequences with source hashes"
    )
    register_library.add_argument("manifest", type=Path)
    register_library.add_argument("--output", required=True, type=Path, metavar="DIRECTORY")
    register_library.add_argument("--base-library", type=Path)
    register_library.add_argument("--json", action="store_true", dest="json_output")

    install = commands.add_parser("install-skill", help="install the bundled Codex skill")
    install.add_argument("--destination", type=Path, required=True)
    install.add_argument("--json", action="store_true", dest="json_output")

    uninstall = commands.add_parser("uninstall-skill", help="remove a skill installed by this package")
    uninstall.add_argument("--destination", type=Path, required=True)
    uninstall.add_argument("--json", action="store_true", dest="json_output")

    check = commands.add_parser("check", help="check an exact reviewed export subset")
    check.add_argument("source", type=Path)
    check.add_argument("--policy", type=Path, required=True)
    check.add_argument("--include", action="append", metavar="PATH")
    check.add_argument("--max-total-bytes", type=int)
    check.add_argument("--json", action="store_true", dest="json_output")

    export = commands.add_parser("export", help="export a reviewed subset to a new directory")
    export.add_argument("source", type=Path)
    export.add_argument("output", type=Path)
    export.add_argument("--policy", type=Path, required=True)
    export.add_argument("--include", action="append", metavar="PATH")
    export.add_argument("--max-total-bytes", type=int)
    export.add_argument("--no-manifest", action="store_true")
    export.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _plain_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return value
    return {"result": str(value)}


def _emit(value: Any, *, json_output: bool, message: str) -> None:
    if json_output:
        print(json.dumps(_plain_value(value), indent=2))
    else:
        print(message)


def _run_init(args: argparse.Namespace) -> int:
    try:
        result = initialize_atlas(
            args.atlas_id,
            args.output_directory,
            disease=args.disease,
            profile=args.profile,
            evidence_cutoff=args.evidence_cutoff,
        )
    except WorkspaceError as exc:
        message = "output directory already exists" if "refusing to overwrite" in str(exc) else str(exc)
        print(f"surface-atlas init: {message}", file=sys.stderr)
        return 1
    except OSError:
        print(
            "surface-atlas init: could not create the workspace; choose a new output path beneath a writable directory",
            file=sys.stderr,
        )
        return 1
    _emit(result, json_output=args.json_output, message=f"Created atlas workspace: {result.workspace}")
    return 0


def _run_example(args: argparse.Namespace) -> int:
    from .example import ExampleError, create_example

    try:
        result = create_example(args.output_directory)
    except (ExampleError, WorkspaceError) as exc:
        message = "output directory already exists" if "refusing to overwrite" in str(exc) else "could not create example"
        print(f"surface-atlas example: {message}", file=sys.stderr)
        return 1
    except OSError:
        print(
            "surface-atlas example: could not create the example; choose a new output path beneath a writable directory",
            file=sys.stderr,
        )
        return 1
    value = _plain_value(result)
    workspace = (
        value.get("directory", value.get("workspace", str(args.output_directory)))
        if isinstance(value, dict)
        else str(args.output_directory)
    )
    _emit(result, json_output=args.json_output, message=f"Created synthetic example: {workspace}")
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    from .validator import main as validate_main

    argv = [str(args.atlas_directory)]
    if args.json_output:
        argv.append("--json")
    return validate_main(argv)


def _run_report(args: argparse.Namespace) -> int:
    from .report import main as report_main

    argv = [str(args.atlas_directory)]
    if args.output_root is not None:
        argv.extend(["--output-root", str(args.output_root)])
    if args.run_id is not None:
        argv.extend(["--run-id", args.run_id])
    if args.json_output:
        argv.append("--json")
    try:
        return report_main(argv)
    except OSError:
        print(
            "surface-atlas report: could not read or write report files; check that atlas files are readable and choose an output root beneath a writable directory",
            file=sys.stderr,
        )
        return 1


def _run_merge_screens(args: argparse.Namespace) -> int:
    from .screening_merge import ScreeningMergeError, merge_screening_files

    try:
        result = merge_screening_files(args.inputs, args.output)
    except ScreeningMergeError as exc:
        if args.json_output:
            print(
                json.dumps(
                    {"errors": [str(exc)], "network_or_provider_calls": False},
                    indent=2,
                )
            )
        else:
            print(f"surface-atlas merge-screens: {exc}", file=sys.stderr)
        return 1
    _emit(
        result,
        json_output=args.json_output,
        message=(
            f"Merged {result.record_count} screening records from "
            f"{result.run_count} runs: {result.output}"
        ),
    )
    return 0


def _run_register_library(args: argparse.Namespace) -> int:
    from .library_registration import LibraryRegistrationError, register_library

    try:
        result = register_library(args.manifest, args.output, base_library=args.base_library)
    except LibraryRegistrationError as exc:
        if args.json_output:
            print(json.dumps({"errors": [str(exc)], "network_or_provider_calls": False}, indent=2))
        else:
            print(f"surface-atlas register-library: {exc}", file=sys.stderr)
        return 1
    _emit(
        result,
        json_output=args.json_output,
        message=f"Registered supplied library: {args.output}",
    )
    return 0


def _run_skill(args: argparse.Namespace, *, uninstall: bool) -> int:
    from .skill_installer import SkillInstallError, install_skill, uninstall_skill

    try:
        if uninstall:
            result = uninstall_skill(args.destination)
            action = "Removed"
        else:
            result = install_skill(args.destination)
            action = "Installed"
    except SkillInstallError as exc:
        command = "uninstall-skill" if uninstall else "install-skill"
        print(f"surface-atlas {command}: {exc}", file=sys.stderr)
        return 1
    value = _plain_value(result)
    destination = value.get("destination", args.destination) if isinstance(value, dict) else args.destination
    _emit(result, json_output=args.json_output, message=f"{action} bundled skill: {destination}")
    return 0


def _run_check(args: argparse.Namespace) -> int:
    try:
        report = check_repository(
            args.source,
            args.policy,
            include=args.include,
            max_total_bytes=args.max_total_bytes,
        )
    except ExportError as exc:
        print(f"surface-atlas check: {exc}", file=sys.stderr)
        return 1
    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))
    elif report.ok:
        print(
            f"Export check passed: {len(report.files)} files, "
            f"{report.total_bytes} bytes, {report.manifest_bytes} manifest bytes"
        )
    else:
        print("Export check failed", file=sys.stderr)
        for finding in report.findings:
            print(f"{finding.code}: {finding.path}: {finding.message}", file=sys.stderr)
    return 0 if report.ok else 1


def _run_export(args: argparse.Namespace) -> int:
    try:
        report = export_subset(
            args.source,
            args.output,
            args.policy,
            include=args.include,
            write_manifest=not args.no_manifest,
            max_total_bytes=args.max_total_bytes,
        )
    except ExportError as exc:
        print(f"surface-atlas export: {exc}", file=sys.stderr)
        return 1
    _emit(
        report,
        json_output=args.json_output,
        message=f"Exported {len(report.files)} files ({report.total_bytes} bytes) to {report.output}",
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in {"tutorial", "ingest-evidence", "reconcile-evidence", "import-binder-runs", "import-assays"}:
        return _run_research(args)
    if args.command == "init":
        return _run_init(args)
    if args.command == "example":
        return _run_example(args)
    if args.command == "validate":
        return _run_validate(args)
    if args.command == "report":
        return _run_report(args)
    if args.command == "merge-screens":
        return _run_merge_screens(args)
    if args.command == "register-library":
        return _run_register_library(args)
    if args.command == "install-skill":
        return _run_skill(args, uninstall=False)
    if args.command == "uninstall-skill":
        return _run_skill(args, uninstall=True)
    if args.command == "check":
        return _run_check(args)
    if args.command == "export":
        return _run_export(args)
    raise AssertionError(f"unhandled command: {args.command}")


def _run_research(args: argparse.Namespace) -> int:
    from .evidence_intake import ingest_evidence, reconcile_evidence
    from .research_intake import import_assays, import_binder_runs
    try:
        if args.command == "tutorial":
            from .tutorial import create_tutorial
            result = create_tutorial(args.output_directory)
        elif args.command == "ingest-evidence":
            result = ingest_evidence(args.inputs, args.atlas, args.output)
        elif args.command == "reconcile-evidence":
            result = reconcile_evidence(args.atlas_directory, args.output)
        elif args.command == "import-binder-runs":
            result = import_binder_runs(args.inputs, args.atlas, args.output)
        else:
            result = import_assays(args.inputs, args.atlas, args.output)
    except (ValueError, OSError) as exc:
        if args.json_output:
            print(json.dumps({"errors": [str(exc)], "network_or_provider_calls": False}, indent=2))
        else:
            print(f"surface-atlas {args.command}: {exc}", file=sys.stderr)
        return 1
    _emit(result, json_output=args.json_output, message=json.dumps(result, indent=2))
    return 0 if result.get("consistent", True) or args.output is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
