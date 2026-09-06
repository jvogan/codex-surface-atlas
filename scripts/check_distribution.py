#!/usr/bin/env python3
"""Exercise a built wheel or validate report-local links."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import configparser
import csv
import io
import hashlib
import json
import os
import shutil
from email.parser import Parser
from email.policy import compat32
from email.utils import formataddr
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import subprocess
import stat
import re
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


def trusted_project_contract(policy_path: Path, reviewed: dict[str, str] | None = None) -> dict:
    """Derive generated metadata only from separately hash-reviewed project files.

    These helpers are also used by the source-archive checker. A wheel's RECORD
    and an sdist's own metadata are integrity claims, never their own authority.
    """
    if reviewed is None:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        _require(isinstance(policy, dict) and policy.get("version") == 1
                 and isinstance(policy.get("files"), list), "trusted metadata policy is invalid")
        reviewed = {}
        for entry in policy["files"]:
            _require(isinstance(entry, dict) and isinstance(entry.get("path"), str)
                     and isinstance(entry.get("sha256"), str), "invalid metadata policy entry")
            _require(entry["path"] not in reviewed, "duplicate metadata policy path")
            reviewed[entry["path"]] = entry["sha256"]
    root = policy_path.resolve().parent

    def trusted_text(name: str) -> str:
        path = PurePosixPath(name)
        _require(not path.is_absolute() and ".." not in path.parts and "\\" not in name
                 and path.as_posix() == name, "unsafe trusted metadata source path")
        source = root.joinpath(*path.parts)
        _require(name in reviewed, "review policy is missing metadata source: " + name)
        _require(not source.is_symlink() and source.is_file()
                 and source.resolve().is_relative_to(root), "metadata source is not a local regular file: " + name)
        data = source.read_bytes()
        _require(hashlib.sha256(data).hexdigest() == reviewed[name],
                 "trusted metadata source differs from review policy: " + name)
        try:
            return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeError as exc:
            raise DistributionCheckError("metadata source is not UTF-8: " + name) from exc

    try:
        import tomllib
    except ImportError:  # Python 3.10; explicitly included in the test extra.
        try:
            import tomli as tomllib
        except ImportError as exc:
            raise DistributionCheckError("Python 3.10 release checks require tomli; install the test extra") from exc
    try:
        config = tomllib.loads(trusted_text("pyproject.toml"))
    except tomllib.TOMLDecodeError as exc:
        raise DistributionCheckError("trusted pyproject.toml is invalid TOML") from exc
    project = config.get("project", {})
    _require(isinstance(project, dict), "trusted project table is missing")
    supported = {"name", "version", "description", "readme", "requires-python", "license",
                 "license-files", "authors", "maintainers", "keywords", "classifiers",
                 "dependencies", "optional-dependencies", "scripts", "gui-scripts", "entry-points", "urls"}
    _require(not set(project) - supported, "unsupported or dynamic trusted project metadata field")
    _require(project.get("name") == "codex-surface-atlas"
             and isinstance(project.get("version"), str), "unexpected trusted project identity")
    _require(config.get("build-system", {}).get("build-backend") == "setuptools.build_meta",
             "unsupported metadata build backend")
    from packaging.markers import Marker
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import Version

    version = str(Version(project["version"]))
    metadata = {"metadata-version": ["2.4"], "name": [project["name"]], "version": [version]}

    def single(field, key):
        if key in project:
            _require(isinstance(project[key], str), "unsupported project metadata: " + key)
            metadata[field] = [project[key]]
    single("summary", "description")
    single("requires-python", "requires-python")
    single("license-expression", "license")
    for plural, field in (("authors", "author"), ("maintainers", "maintainer")):
        names, emails = [], []
        for person in project.get(plural, []):
            _require(isinstance(person, dict) and not set(person) - {"name", "email"},
                     "unsupported project author/maintainer")
            if person.get("email"):
                emails.append(formataddr((person.get("name", ""), person["email"])))
            elif person.get("name"):
                names.append(person["name"])
        if names:
            metadata[field] = [", ".join(names)]
        if emails:
            metadata[field + "-email"] = [", ".join(emails)]
    if project.get("keywords"):
        metadata["keywords"] = [",".join(project["keywords"])]
    if project.get("classifiers"):
        metadata["classifier"] = project["classifiers"]
    if project.get("urls"):
        metadata["project-url"] = [f"{key}, {value}" for key, value in project["urls"].items()]
    license_files = project.get("license-files", [])
    _require(isinstance(license_files, list) and all(isinstance(name, str) and name in reviewed for name in license_files),
             "license-files must name explicitly reviewed files")
    if license_files:
        metadata["license-file"] = license_files
    description = ""
    if "readme" in project:
        readme = project["readme"]
        if isinstance(readme, str):
            content_types = {".md": "text/markdown", ".rst": "text/x-rst", ".txt": "text/plain"}
            content_type = content_types.get(Path(readme).suffix.lower())
            _require(content_type is not None, "unsupported trusted readme suffix")
        else:
            _require(isinstance(readme, dict) and set(readme) == {"file", "content-type"},
                     "trusted readme must reference a reviewed source file")
            content_type, readme = readme["content-type"], readme["file"]
        description = trusted_text(readme)
        metadata["description-content-type"] = [content_type]
    dependencies = [str(Requirement(value)) for value in project.get("dependencies", [])]
    extras = []
    for extra, requirements in project.get("optional-dependencies", {}).items():
        normalized = canonicalize_name(extra)
        _require(normalized not in extras, "duplicate normalized project extra")
        extras.append(normalized)
        for value in requirements:
            requirement = Requirement(value)
            condition = f'extra == "{normalized}"'
            if requirement.marker:
                condition = f"({requirement.marker}) and {condition}"
            requirement.marker = Marker(condition)
            dependencies.append(str(requirement))
    if extras:
        metadata["provides-extra"] = extras
    if dependencies:
        metadata["requires-dist"] = dependencies
    entry_points = dict(project.get("entry-points", {}))
    for field, group in (("scripts", "console_scripts"), ("gui-scripts", "gui_scripts")):
        if project.get(field):
            _require(group not in entry_points, "duplicate trusted entry point group")
            entry_points[group] = project[field]
    return {"metadata": metadata, "description": description, "entry_points": entry_points,
            "top_level": b"surface_atlas\n", "project": project, "name": project["name"],
            "version": version, "dist_info": "codex_surface_atlas-" + version + ".dist-info"}


def _metadata_message(payload: bytes, label: str):
    try:
        decoded = payload.decode("utf-8")
    except UnicodeError as exc:
        raise DistributionCheckError(label + " is not UTF-8") from exc
    message = Parser(policy=compat32).parsestr(decoded)
    _require(not message.defects and not message.is_multipart(), label + " is malformed")
    return message


def check_core_metadata(payload: bytes, contract: dict) -> None:
    """Verify METADATA or PKG-INFO headers and description against trusted inputs."""
    from packaging.requirements import InvalidRequirement, Requirement
    message = _metadata_message(payload, "core metadata")
    actual = {}
    for field, value in message.items():
        actual.setdefault(field.lower(), []).append(value)
    # Current setuptools may mark license-file dynamic in both sdist and wheel.
    dynamic = actual.pop("dynamic", [])
    _require(dynamic in ([], ["license-file"]), "unreviewed dynamic metadata field")
    _require(set(actual) == set(contract["metadata"]), "unreviewed or missing core metadata fields")
    for field, expected in contract["metadata"].items():
        values = actual[field]
        if field == "requires-dist":
            try:
                values = [str(Requirement(value)) for value in values]
            except InvalidRequirement as exc:
                raise DistributionCheckError("invalid metadata dependency") from exc
        _require(Counter(values) == Counter(expected), "core metadata differs from reviewed project: " + field)
    description = message.get_payload()
    _require(isinstance(description, str)
             and description.replace("\r\n", "\n") == contract["description"],
             "core metadata description differs from reviewed README")


def check_entry_points(payload: bytes, contract: dict) -> None:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    try:
        parser.read_string(payload.decode("utf-8"))
    except (UnicodeError, configparser.Error) as exc:
        raise DistributionCheckError("malformed entry_points.txt") from exc
    _require(not parser.defaults(), "entry point defaults are not allowed")
    actual = {section: dict(parser.items(section)) for section in parser.sections()}
    _require(actual == contract["entry_points"], "entry points differ from reviewed project")
    expected = "\n".join(
        f"[{group}]\n" + "".join(f"{name} = {value}\n" for name, value in sorted(entries.items()))
        for group, entries in sorted(contract["entry_points"].items())
    ).encode("utf-8")
    _require(payload.replace(b"\r\n", b"\n") == expected,
             "entry_points.txt contains unreviewed formatting or text")


def check_top_level(payload: bytes, contract: dict) -> None:
    _require(payload.replace(b"\r\n", b"\n") == contract["top_level"], "top_level.txt differs from reviewed package")


def check_wheel_metadata(payload: bytes) -> None:
    from packaging.version import Version
    message = _metadata_message(payload, "WHEEL")
    fields = {}
    for name, value in message.items():
        fields.setdefault(name.lower(), []).append(value)
    _require(set(fields) == {"wheel-version", "generator", "root-is-purelib", "tag"},
             "unreviewed or missing WHEEL fields")
    _require(fields["wheel-version"] == ["1.0"] and fields["root-is-purelib"] == ["true"]
             and fields["tag"] == ["py3-none-any"], "unexpected WHEEL install layout or compatibility tags")
    generator = re.fullmatch(r"(?:setuptools|bdist_wheel) \(([0-9]+(?:\.[0-9]+){1,3})\)",
                             fields["generator"][0]) if len(fields["generator"]) == 1 else None
    _require(generator is not None and str(Version(generator.group(1))) == generator.group(1),
             "unexpected WHEEL generator")
    _require(message.get_payload() in ("", "\n"), "unexpected WHEEL body")


def check_wheel_inventory(wheel: Path, policy_path: Path) -> int:
    """Verify every installed payload against a separately reviewed source policy."""
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    _require(isinstance(policy, dict) and policy.get("version") == 1
             and isinstance(policy.get("files"), list) and policy["files"],
             "wheel check needs a nonempty version 1 review policy")
    reviewed = {}
    for entry in policy["files"]:
        _require(isinstance(entry, dict) and isinstance(entry.get("path"), str)
                 and isinstance(entry.get("sha256"), str), "invalid review policy entry")
        name = entry["path"]
        _require(name not in reviewed, "duplicate review policy path")
        reviewed[name] = entry["sha256"]
    contract = trusted_project_contract(policy_path, reviewed)
    with ZipFile(wheel) as bundle:
        names = set()
        for member in bundle.infolist():
            name = member.filename
            parsed = PurePosixPath(name)
            mode = member.external_attr >> 16
            _require(name and not parsed.is_absolute() and ".." not in parsed.parts
                     and "\\" not in name and parsed.as_posix() == name
                     and not any(":" in part for part in parsed.parts)
                     and not member.is_dir() and not stat.S_ISLNK(mode)
                     and (not stat.S_IFMT(mode) or stat.S_ISREG(mode)),
                     "unsafe or non-regular wheel entry")
            _require(name not in names, "duplicate wheel entry")
            names.add(name)
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        _require(len(metadata) == 1, "wheel needs exactly one metadata directory")
        prefix = metadata[0].removesuffix("/METADATA")
        _require(prefix == contract["dist_info"],
                 "unexpected wheel metadata directory")
        data_prefix = prefix.removesuffix(".dist-info") + ".data/data/"
        expected = {name.removeprefix("src/"): digest for name, digest in reviewed.items()
                    if name.startswith("src/surface_atlas/")}
        # Schemas use the declared setuptools data-files installation mapping.
        expected.update({data_prefix + "share/codex-surface-atlas/" + name: digest
                             for name, digest in reviewed.items()
                             if name.startswith("schemas/v0.1/") and name.endswith(".json")})
        for name in ("LICENSE", "NOTICE.md"):
            _require(name in reviewed, "review policy is missing license material")
            expected[prefix + "/licenses/" + name] = reviewed[name]
        generated = {prefix + "/" + name for name in
                     ("METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD")}
        _require(set(expected) <= names, "reviewed wheel files are missing: "
                 + ", ".join(sorted(set(expected) - names)))
        _require(names <= set(expected) | generated, "unreviewed wheel files: "
                 + ", ".join(sorted(names - set(expected) - generated)))
        required_metadata = {prefix + "/" + name for name in ("METADATA", "WHEEL", "top_level.txt", "RECORD")}
        if contract["entry_points"]:
            required_metadata.add(prefix + "/entry_points.txt")
        _require(required_metadata <= names, "required generated wheel metadata is missing")
        check_core_metadata(bundle.read(prefix + "/METADATA"), contract)
        check_wheel_metadata(bundle.read(prefix + "/WHEEL"))
        check_top_level(bundle.read(prefix + "/top_level.txt"), contract)
        if prefix + "/entry_points.txt" in names:
            check_entry_points(bundle.read(prefix + "/entry_points.txt"), contract)
        for name, digest in expected.items():
            _require(hashlib.sha256(bundle.read(name)).hexdigest() == digest,
                     "reviewed wheel file differs: " + name)
        record_name = prefix + "/RECORD"
        _require(record_name in names, "wheel RECORD is missing")
        recorded = set()
        for row in csv.reader(io.StringIO(bundle.read(record_name).decode("utf-8"))):
            _require(len(row) == 3, "invalid wheel RECORD row")
            name, digest, size = row
            _require(name in names and name not in recorded, "invalid wheel RECORD inventory")
            recorded.add(name)
            if name == record_name:
                _require(not digest and not size, "RECORD must leave its own hash and size empty")
                continue
            payload = bundle.read(name)
            actual = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode("ascii")
            _require(digest == "sha256=" + actual and size == str(len(payload)),
                     "wheel RECORD hash or size differs: " + name)
        _require(recorded == names, "wheel RECORD inventory is incomplete")
    return len(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", type=Path, help="wheel to install and exercise")
    parser.add_argument("--report", type=Path, metavar="DIRECTORY",
                        help="check an existing report directory without installing a wheel")
    parser.add_argument("--example", type=Path, metavar="DIRECTORY",
                        help="also copy and exercise a research example with the installed wheel")
    parser.add_argument("--policy", type=Path,
                        default=Path(__file__).resolve().parents[1] / "export-policy.json",
                        help="trusted reviewed source policy for wheel inventory")
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
    check_wheel_inventory(wheel, args.policy)
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
        run(str(cli), "tutorial", "tutorial", "--json")
        _require(json.loads(run(str(cli), "validate", "tutorial", "--json"))["valid"],
                 "installed tutorial validation failed")
        reconciled = json.loads(run(str(cli), "reconcile-evidence", "tutorial", "--json"))
        _require(reconciled["consistent"] and reconciled["expected_counts"]["raw_records"] == 6
                 and reconciled["expected_counts"]["unresolved_records"] == 1,
                 "installed tutorial reconciliation failed")
        tutorial_report = json.loads(run(str(cli), "report", "tutorial", "--output-root", "reports", "--run-id", "tutorial", "--json"))
        tutorial_dir = Path(tutorial_report["run_directory"])
        tutorial_pages = check_report(tutorial_dir, synthetic=True)
        for filename in ("action-comparison.html", "sequence-sites.html", "campaigns.html", "assays.html"):
            _require((tutorial_dir / filename).is_file(), f"missing tutorial page: {filename}")
        runs = json.loads((tutorial_dir / "data/binder-runs.json").read_text(encoding="utf-8"))
        _require(len(runs["records"]) == 2 and {r["controls_status"] for r in runs["records"]} == {"failed", "not-run"},
                 "tutorial independent control outcomes changed")
        assays = json.loads((tutorial_dir / "data/assay-results.json").read_text(encoding="utf-8"))
        _require(assays["records"][0]["reading"]["relation"] == ">"
                 and assays["records"][0]["reading"]["unit"] == "nM", "tutorial censored reading changed")
        tutorial_inputs = root / "tutorial/tutorial-inputs/research"
        run(str(cli), "import-binder-runs", str(tutorial_inputs / "binder-runs.json"),
            str(tutorial_inputs / "binder-runs-two.json"), "--atlas", "tutorial", "--output", "runs-bundle", "--json")
        run(str(cli), "import-assays", str(tutorial_inputs / "assay-results.json"),
            "--atlas", "tutorial", "--output", "assay-bundle", "--json")
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
    print(f"Installed tutorial passed: evidence reconciliation, binder/assay import, and {tutorial_pages} linked report pages.")
    if example is not None:
        print(f"Relocated research example passed: validation and {research_pages} report pages.")


if __name__ == "__main__":
    main()
