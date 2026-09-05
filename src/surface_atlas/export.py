"""Fail-closed checks and transactional export for reviewed public files."""

from __future__ import annotations

import ast
import ctypes
import csv
import errno
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import unquote


class ExportError(RuntimeError):
    """Raised when an export cannot be completed safely."""


class PolicyError(ExportError):
    """Raised when an export policy is invalid or ambiguous."""


@dataclass(frozen=True)
class ApprovedFile:
    path: str
    sha256: str
    kind: str
    reviewed_binary: bool = False
    allow_findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExportPolicy:
    files: tuple[ApprovedFile, ...]
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    deny_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class CheckedFile:
    path: str
    sha256: str
    bytes: int
    kind: str
    review_exceptions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, str | int | list[str]]:
        result: dict[str, str | int | list[str]] = {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "kind": self.kind,
        }
        if self.review_exceptions:
            result["review_exceptions"] = list(self.review_exceptions)
        return result


@dataclass(frozen=True)
class CheckReport:
    files: tuple[CheckedFile, ...]
    findings: tuple[Finding, ...]
    total_bytes: int
    manifest_bytes: int

    @property
    def ok(self) -> bool:
        return not self.findings

    @property
    def errors(self) -> tuple[Finding, ...]:
        return self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "files": [item.to_dict() for item in self.files],
            "file_count": len(self.files),
            "total_bytes": self.total_bytes,
            "manifest_bytes": self.manifest_bytes,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class ExportReport:
    output: str
    files: tuple[CheckedFile, ...]
    total_bytes: int
    manifest_bytes: int
    manifest_written: bool

    @property
    def ok(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "output": self.output,
            "files": [item.to_dict() for item in self.files],
            "file_count": len(self.files),
            "total_bytes": self.total_bytes,
            "manifest_bytes": self.manifest_bytes,
            "manifest_written": self.manifest_written,
        }


_POLICY_KEYS = {"version", "files", "limits", "deny_terms"}
_FILE_KEYS = {"path", "sha256", "kind", "reviewed_binary", "allow_findings"}
_LIMIT_KEYS = {"max_files", "max_file_bytes", "max_total_bytes"}
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_KINDS = {
    "binary",
    "config",
    "css",
    "csv",
    "excalidraw",
    "html",
    "javascript",
    "json",
    "json-schema",
    "json-template",
    "license",
    "molecular-text",
    "python",
    "svg",
    "tabular",
    "text",
}
_TEXT_EXTENSIONS = {
    "json": {".json"},
    "json-schema": {".json"},
    "json-template": {".json"},
    "csv": {".csv"},
    "text": {".md", ".txt", ".toml", ".yaml", ".yml"},
    "python": {".py"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"},
    "css": {".css"},
    "svg": {".svg"},
    "excalidraw": {".excalidraw"},
    "html": {".html", ".htm"},
    "molecular-text": {".cif", ".fa", ".fasta", ".pdb", ".sdf", ".smi", ".smiles"},
    "tabular": {".tsv"},
}
_SOURCE_KINDS = {"css", "javascript", "python"}
_EXCEPTION_CODES = {
    "case_identifier",
    "credential_field",
    "credential_value",
    "internal_conversation",
    "private_path",
    "provider_receipt",
}
_FORBIDDEN_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "cache",
    "caches",
    "credential",
    "credentials",
    "private",
    "provider-receipts",
    "provider_receipts",
    "raw",
    "receipt",
    "receipts",
    "secret",
    "secrets",
    "transcript",
    "transcripts",
}
_MANIFEST_NAME = "surface-atlas-export.json"
_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}
_RECEIPT_KEYS = {
    "billing_receipt",
    "provider_receipt",
    "provider_response",
    "usage_receipt",
}
_CONVERSATION_KEYS = {
    "chat_history",
    "conversation",
    "conversation_history",
    "internal_messages",
    "messages",
    "prompt_history",
}
_CASE_ID_KEYS = {
    "campaign_id",
    "case_id",
    "customer_id",
    "matter_id",
    "patient_id",
    "subject_id",
    "ticket_id",
}
_PRIVATE_PATH_RE = re.compile(
    r"(?:/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|/Volumes/[^/\s]+/|"
    r"[A-Za-z]:\\Users\\|file:///)",
    re.IGNORECASE,
)
_CREDENTIAL_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\bAuthorization\s*:\s*Bearer\s+\S+|"
    r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[^\s'\"]{8,}|"
    r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b)",
    re.IGNORECASE,
)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_ROLE_LINE_RE = re.compile(r"(?m)^\s*(?:user|assistant|system|developer)\s*:\s*\S", re.IGNORECASE)
_URL_ATTRIBUTES = {"action", "formaction", "href", "poster", "src", "srcset"}


def _percent_decode(value: str) -> str:
    """Decode bounded nested URL quoting so attributes receive text checks."""

    decoded = value
    for _ in range(3):
        candidate = unquote(decoded)
        if candidate == decoded:
            break
        decoded = candidate
    return decoded


class _CheckedHTMLParser(HTMLParser):
    """Extract checked HTML content without treating the parser as a validator."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.searchable: list[str] = []
        self.json_blocks: list[str] = []
        self._hidden_depth = 0
        self._json_parts: list[str] | None = None
        self._pre_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        normalized_attrs = {name.casefold(): value for name, value in attrs}
        for name, value in attrs:
            self.searchable.append(unescape(name))
            if value is not None:
                decoded = unescape(value)
                self.searchable.append(decoded)
                if name.casefold() in _URL_ATTRIBUTES:
                    self.searchable.append(_percent_decode(decoded))
        if lowered in {"script", "style"}:
            self._hidden_depth += 1
        if lowered == "script" and str(normalized_attrs.get("type", "")).split(";", 1)[0].strip().casefold() == "application/json":
            if self._json_parts is not None:
                raise ValueError("nested application/json script")
            self._json_parts = []
        if lowered == "pre":
            if self._pre_parts is not None:
                raise ValueError("nested pre element")
            self._pre_parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "script" and self._json_parts is not None:
            self.json_blocks.append("".join(self._json_parts))
            self._json_parts = None
        if lowered == "pre" and self._pre_parts is not None:
            candidate = "".join(self._pre_parts).strip()
            if candidate.startswith(("{", "[")):
                self.json_blocks.append(candidate)
            self._pre_parts = None
        if lowered in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._json_parts is not None:
            self._json_parts.append(data)
        elif not self._hidden_depth:
            decoded = unescape(data)
            self.searchable.append(decoded)
            if self._pre_parts is not None:
                self._pre_parts.append(decoded)

    def handle_comment(self, data: str) -> None:
        self.searchable.append(unescape(data))

    def finish(self) -> None:
        self.close()
        if self._json_parts is not None:
            raise ValueError("unclosed application/json script")
        if self._pre_parts is not None:
            raise ValueError("unclosed pre element")
        if self._hidden_depth:
            raise ValueError("unclosed script or style element")
        if self.rawdata:
            raise ValueError("incomplete HTML token")


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PolicyError(f"{name} must be a positive integer")
    return value


def _normalize_relative_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise PolicyError("approved paths must be non-empty POSIX relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise PolicyError("approved path is not a safe relative path")
    if any(part.casefold() in _FORBIDDEN_PARTS for part in path.parts):
        raise PolicyError("approved path uses a private or generated directory")
    if value.casefold() == _MANIFEST_NAME:
        raise PolicyError("approved path conflicts with the generated manifest")
    return value


def _rename_directory_exclusive(source: Path, destination: Path) -> None:
    """Atomically rename a directory without replacing an existing path."""

    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex_np = libc.renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(os.fsencode(source), os.fsencode(destination), 0x00000004)
    elif sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            renameat2 = libc.renameat2
        except AttributeError as exc:
            raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable") from exc
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 0x00000001)
    elif os.name == "nt":
        os.rename(source, destination)
        return
    else:
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def load_policy(policy: str | os.PathLike[str] | Mapping[str, Any]) -> ExportPolicy:
    """Load and strictly validate a version 1 export policy."""

    if isinstance(policy, Mapping):
        data = dict(policy)
    else:
        try:
            policy_text = Path(policy).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PolicyError("could not read export policy") from exc
        try:
            data = json.loads(policy_text)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"export policy is invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(data, dict):
        raise PolicyError("export policy must be a JSON object")
    unknown = set(data) - _POLICY_KEYS
    if unknown:
        raise PolicyError(f"unknown policy fields: {', '.join(sorted(unknown))}")
    if data.get("version") != 1:
        raise PolicyError("export policy version must be 1")
    limits = data.get("limits")
    if not isinstance(limits, dict):
        raise PolicyError("policy limits must be an object")
    unknown_limits = set(limits) - _LIMIT_KEYS
    if unknown_limits or set(limits) != _LIMIT_KEYS:
        raise PolicyError("policy limits must define only max_files, max_file_bytes, and max_total_bytes")
    max_files = _positive_int(limits["max_files"], "max_files")
    max_file_bytes = _positive_int(limits["max_file_bytes"], "max_file_bytes")
    max_total_bytes = _positive_int(limits["max_total_bytes"], "max_total_bytes")
    raw_files = data.get("files")
    if not isinstance(raw_files, list):
        raise PolicyError("policy files must be an array")
    if len(raw_files) > max_files:
        raise PolicyError("policy contains more files than max_files")
    raw_deny_terms = data.get("deny_terms", [])
    if not isinstance(raw_deny_terms, list) or len(raw_deny_terms) > 100:
        raise PolicyError("deny_terms must be an array with at most 100 entries")
    deny_terms: list[str] = []
    for index, term in enumerate(raw_deny_terms):
        if not isinstance(term, str) or not (4 <= len(term) <= 256) or term.strip() != term:
            raise PolicyError(f"deny_terms[{index}] must be a trimmed string of 4 to 256 characters")
        if term.casefold() in {item.casefold() for item in deny_terms}:
            raise PolicyError("deny_terms must not contain duplicates")
        deny_terms.append(term)
    approved: list[ApprovedFile] = []
    seen: set[str] = set()
    seen_folded: set[str] = set()
    for index, item in enumerate(raw_files):
        if not isinstance(item, dict) or set(item) - _FILE_KEYS:
            raise PolicyError(f"files[{index}] contains unknown fields or is not an object")
        if not {"path", "sha256", "kind"}.issubset(item):
            raise PolicyError(f"files[{index}] must define path, sha256, and kind")
        relative = _normalize_relative_path(item["path"])
        if relative in seen or relative.casefold() in seen_folded:
            raise PolicyError(f"files[{index}].path duplicates another approved path")
        seen.add(relative)
        seen_folded.add(relative.casefold())
        digest = item["sha256"]
        if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest):
            raise PolicyError(f"files[{index}].sha256 must be a lowercase SHA-256 digest")
        kind = item["kind"]
        if kind not in _KINDS:
            raise PolicyError(f"files[{index}].kind must be one of: {', '.join(sorted(_KINDS))}")
        reviewed_binary = item.get("reviewed_binary", False)
        if not isinstance(reviewed_binary, bool):
            raise PolicyError(f"files[{index}].reviewed_binary must be boolean")
        suffix = PurePosixPath(relative).suffix.casefold()
        if kind == "binary":
            if not reviewed_binary:
                raise PolicyError(f"files[{index}] requires reviewed_binary=true")
        elif reviewed_binary:
            raise PolicyError(f"files[{index}].reviewed_binary is only valid for binary files")
        elif kind == "license":
            if PurePosixPath(relative).name not in {"LICENSE", "NOTICE"}:
                raise PolicyError(f"files[{index}].path does not match kind license")
        elif kind == "config":
            if PurePosixPath(relative).name not in {".gitignore", ".gitattributes", "MANIFEST.in"}:
                raise PolicyError(f"files[{index}].path does not match kind config")
        elif suffix not in _TEXT_EXTENSIONS[kind]:
            raise PolicyError(f"files[{index}].path extension does not match its kind")
        raw_exceptions = item.get("allow_findings", [])
        if not isinstance(raw_exceptions, list) or any(not isinstance(code, str) for code in raw_exceptions):
            raise PolicyError(f"files[{index}].allow_findings must be an array of finding codes")
        exceptions = tuple(sorted(set(raw_exceptions)))
        if len(exceptions) != len(raw_exceptions):
            raise PolicyError(f"files[{index}].allow_findings must not contain duplicates")
        if exceptions and kind not in _SOURCE_KINDS:
            raise PolicyError(f"files[{index}].allow_findings is only valid for reviewed source files")
        unknown_exceptions = set(exceptions) - _EXCEPTION_CODES
        if unknown_exceptions:
            raise PolicyError(f"files[{index}].allow_findings contains unsupported codes")
        approved.append(ApprovedFile(relative, digest, kind, reviewed_binary, exceptions))
    return ExportPolicy(tuple(approved), max_files, max_file_bytes, max_total_bytes, tuple(deny_terms))


def _walk_json(value: Any) -> tuple[list[tuple[str, Any]], list[str]]:
    fields: list[tuple[str, Any]] = []
    strings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().casefold().replace("-", "_")
            fields.append((normalized, child))
            strings.append(str(key))
            child_fields, child_strings = _walk_json(child)
            fields.extend(child_fields)
            strings.extend(child_strings)
    elif isinstance(value, list):
        for child in value:
            child_fields, child_strings = _walk_json(child)
            fields.extend(child_fields)
            strings.extend(child_strings)
    elif isinstance(value, str):
        strings.append(value)
    return fields, strings


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _scan_text(path: str, text: str, kind: str, deny_terms: Sequence[str]) -> list[Finding]:
    findings: list[Finding] = []
    fields: list[tuple[str, Any]] = []
    searchable = text
    if kind in {"json", "excalidraw", "json-schema", "json-template"}:
        try:
            parseable = re.sub(r"__[A-Z][A-Z0-9_]*__", "0", text) if kind == "json-template" else text
            parsed = json.loads(parseable)
        except json.JSONDecodeError as exc:
            code = "invalid_json_template" if kind == "json-template" else "invalid_json"
            return [Finding(code, path, f"JSON is invalid at line {exc.lineno}, column {exc.colno}")]
        parsed_fields, strings = _walk_json(parsed)
        if kind != "json-schema":
            fields = parsed_fields
        searchable = "\n".join(strings)
    elif kind in {"csv", "tabular"}:
        try:
            delimiter = "\t" if kind == "tabular" else ","
            rows = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
            header = next(rows, [])
            fields = [(key.strip().casefold().replace("-", "_"), "column") for key in header]
            for _ in rows:
                pass
        except csv.Error as exc:
            code = "invalid_tsv" if kind == "tabular" else "invalid_csv"
            label = "TSV" if kind == "tabular" else "CSV"
            return [Finding(code, path, f"{label} is invalid: {exc}")]
    elif kind == "python":
        try:
            ast.parse(text, filename=path)
        except SyntaxError as exc:
            return [Finding("invalid_python", path, f"Python is invalid at line {exc.lineno}")]
    elif kind == "svg":
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            return [Finding("invalid_svg", path, f"SVG XML is invalid: {exc}")]
        if root.tag.rsplit("}", 1)[-1].casefold() != "svg":
            findings.append(Finding("invalid_svg", path, "XML root element is not svg"))
    elif kind == "html":
        parser = _CheckedHTMLParser()
        try:
            parser.feed(text)
            parser.finish()
        except (AssertionError, ValueError):
            return [Finding("invalid_html", path, "HTML could not be checked")]
        decoded_strings = list(parser.searchable)
        for block in parser.json_blocks:
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError as exc:
                return [Finding("invalid_html_json", path, f"embedded JSON is invalid at line {exc.lineno}, column {exc.colno}")]
            parsed_fields, parsed_strings = _walk_json(parsed)
            fields.extend(parsed_fields)
            decoded_strings.extend(parsed_strings)
        searchable = "\n".join([text, *decoded_strings])
    for code, blocked, message in (
        ("credential_field", _SENSITIVE_KEYS, "contains a credential field"),
        ("provider_receipt", _RECEIPT_KEYS, "contains provider receipt metadata"),
        ("internal_conversation", _CONVERSATION_KEYS, "contains conversation records"),
        ("case_identifier", _CASE_ID_KEYS, "contains a case-specific identifier field"),
    ):
        if any(key in blocked and _has_value(value) for key, value in fields):
            findings.append(Finding(code, path, message))
    if _PRIVATE_PATH_RE.search(searchable):
        findings.append(Finding("private_path", path, "contains a private absolute path"))
    if _CREDENTIAL_RE.search(searchable):
        findings.append(Finding("credential_value", path, "contains credential-shaped content"))
    if _UUID_RE.search(searchable):
        findings.append(Finding("case_identifier", path, "contains a case-shaped UUID"))
    if len(_ROLE_LINE_RE.findall(searchable)) >= 2:
        findings.append(Finding("internal_conversation", path, "contains conversation-shaped role records"))
    folded = searchable.casefold()
    if any(term.casefold() in folded for term in deny_terms):
        findings.append(Finding("deny_term", path, "contains a private deny term"))
    # One finding per category is enough to stop an export and keeps reports bounded.
    unique: dict[str, Finding] = {}
    for finding in findings:
        unique.setdefault(finding.code, finding)
    return list(unique.values())


def _selection(policy: ExportPolicy, include: Sequence[str] | None) -> tuple[list[ApprovedFile], list[Finding]]:
    by_path = {item.path: item for item in policy.files}
    if include is None:
        return list(policy.files), []
    if isinstance(include, (str, bytes)):
        return [], [Finding("invalid_path", ".", "include must be a sequence of relative paths")]
    selected: list[ApprovedFile] = []
    findings: list[Finding] = []
    seen: set[str] = set()
    for raw in include:
        try:
            path = _normalize_relative_path(raw)
        except PolicyError:
            findings.append(Finding("invalid_path", ".", "requested path is not a safe relative path"))
            continue
        if path in seen:
            continue
        seen.add(path)
        item = by_path.get(path)
        if item is None:
            display_path = path
            if any(term.casefold() in path.casefold() for term in policy.deny_terms):
                display_path = "."
            findings.append(Finding("unapproved_path", display_path, "path is not in the exact allowlist"))
        else:
            selected.append(item)
    return selected, findings


def _manifest(files: Sequence[CheckedFile]) -> dict[str, Any]:
    return {
        "version": 1,
        "files": [item.to_dict() for item in files],
        "file_count": len(files),
        "total_bytes": sum(item.bytes for item in files),
    }


def _manifest_bytes(files: Sequence[CheckedFile]) -> bytes:
    return (json.dumps(_manifest(files), indent=2, sort_keys=True) + "\n").encode("utf-8")


def check_repository(
    source: str | os.PathLike[str],
    policy: ExportPolicy | str | os.PathLike[str] | Mapping[str, Any],
    *,
    include: Sequence[str] | None = None,
    max_total_bytes: int | None = None,
) -> CheckReport:
    """Dry-run an exact reviewed subset and return bounded findings and sizes."""

    loaded = policy if isinstance(policy, ExportPolicy) else load_policy(policy)
    if max_total_bytes is None:
        cap = loaded.max_total_bytes
    else:
        cap = min(loaded.max_total_bytes, _positive_int(max_total_bytes, "max_total_bytes"))
    root = Path(source)
    selected, findings = _selection(loaded, include)
    if not selected:
        findings.append(Finding("empty_selection", ".", "export selection contains no approved files"))
    if len(selected) > loaded.max_files:
        findings.append(Finding("too_many_files", ".", "selection exceeds max_files"))
    if root.is_symlink():
        findings.append(Finding("source_symlink", ".", "source directory must not be a symlink"))
        return CheckReport((), tuple(findings), 0, len(_manifest_bytes(())))
    if not root.is_dir():
        findings.append(Finding("invalid_source", ".", "source must be an existing directory"))
        return CheckReport((), tuple(findings), 0, len(_manifest_bytes(())))
    checked: list[CheckedFile] = []
    total = 0
    for approved in selected:
        if any(term.casefold() in approved.path.casefold() for term in loaded.deny_terms):
            findings.append(Finding("deny_term", ".", "an approved path contains a private deny term"))
            continue
        target = root.joinpath(*PurePosixPath(approved.path).parts)
        current = root
        symlink = False
        for part in PurePosixPath(approved.path).parts:
            current = current / part
            if current.is_symlink():
                symlink = True
                break
        if symlink:
            findings.append(Finding("symlink", approved.path, "approved path or a parent is a symlink"))
            continue
        descriptor = -1
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(target, flags)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                findings.append(Finding("not_regular_file", approved.path, "approved path is not a regular file"))
                continue
            if metadata.st_size > loaded.max_file_bytes:
                total += metadata.st_size
                findings.append(Finding("file_too_large", approved.path, "file exceeds max_file_bytes"))
                continue
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                content = stream.read(loaded.max_file_bytes + 1)
        except FileNotFoundError:
            findings.append(Finding("missing_file", approved.path, "approved file is missing"))
            continue
        except OSError:
            findings.append(Finding("unreadable_file", approved.path, "approved file could not be read"))
            continue
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        total += len(content)
        if len(content) > loaded.max_file_bytes:
            findings.append(Finding("file_too_large", approved.path, "file exceeds max_file_bytes"))
            continue
        digest = hashlib.sha256(content).hexdigest()
        review_exceptions = approved.allow_findings
        if approved.kind == "binary":
            review_exceptions = ("binary_content_not_scanned",)
        checked_file = CheckedFile(approved.path, digest, len(content), approved.kind, review_exceptions)
        checked.append(checked_file)
        if digest != approved.sha256:
            findings.append(Finding("hash_mismatch", approved.path, "content changed since review"))
            continue
        if approved.kind != "binary":
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                findings.append(Finding("invalid_utf8", approved.path, "reviewed text file is not UTF-8"))
                continue
            content_findings = _scan_text(approved.path, text, approved.kind, loaded.deny_terms)
            findings.extend(item for item in content_findings if item.code not in approved.allow_findings)
    if total > cap:
        findings.append(Finding("total_too_large", ".", "selection exceeds max_total_bytes"))
    manifest_size = len(_manifest_bytes(checked))
    return CheckReport(tuple(checked), tuple(findings), total, manifest_size)


def export_subset(
    source: str | os.PathLike[str],
    output: str | os.PathLike[str],
    policy: ExportPolicy | str | os.PathLike[str] | Mapping[str, Any],
    *,
    include: Sequence[str] | None = None,
    write_manifest: bool = True,
    max_total_bytes: int | None = None,
) -> ExportReport:
    """Export a checked subset atomically into a new directory."""

    destination = Path(output)
    if destination.exists() or destination.is_symlink():
        raise ExportError("output directory must not already exist")
    if not destination.parent.is_dir():
        raise ExportError("output parent must be an existing directory")
    loaded = policy if isinstance(policy, ExportPolicy) else load_policy(policy)
    report = check_repository(source, loaded, include=include, max_total_bytes=max_total_bytes)
    if not report.ok:
        codes = ", ".join(sorted({finding.code for finding in report.findings}))
        raise ExportError(f"export check failed: {codes}")
    try:
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    except OSError as exc:
        raise ExportError("could not create export staging directory") from exc
    try:
        root = Path(source)
        for item in report.files:
            source_file = root.joinpath(*PurePosixPath(item.path).parts)
            output_file = temporary.joinpath(*PurePosixPath(item.path).parts)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            try:
                descriptor = os.open(source_file, flags)
            except OSError as exc:
                raise ExportError(f"could not reopen approved file safely: {item.path}") from exc
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise ExportError(f"approved path stopped being a regular file: {item.path}")
                with os.fdopen(descriptor, "rb") as stream:
                    descriptor = -1
                    copied = stream.read(loaded.max_file_bytes + 1)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            if len(copied) > loaded.max_file_bytes or hashlib.sha256(copied).hexdigest() != item.sha256:
                raise ExportError(f"copied file failed hash verification: {item.path}")
            output_file.write_bytes(copied)
        manifest = _manifest_bytes(report.files)
        if write_manifest:
            (temporary / _MANIFEST_NAME).write_bytes(manifest)
        if destination.exists() or destination.is_symlink():
            raise ExportError("output directory appeared during export")
        try:
            _rename_directory_exclusive(temporary, destination)
        except OSError as exc:
            raise ExportError("could not publish export; output may have appeared") from exc
    except ExportError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        raise ExportError("could not write export") from exc
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return ExportReport(
        str(destination),
        report.files,
        report.total_bytes,
        report.manifest_bytes,
        write_manifest,
    )


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Return a review aid hash for one regular, non-symlink file."""

    candidate = Path(path)
    if candidate.is_symlink():
        raise ExportError("cannot hash a symlink for review")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise ExportError("could not read file for review") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ExportError("review hash input must be a regular file")
    try:
        return hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError as exc:
        raise ExportError("could not read file for review") from exc


__all__ = [
    "ApprovedFile",
    "CheckedFile",
    "CheckReport",
    "ExportError",
    "ExportPolicy",
    "ExportReport",
    "Finding",
    "PolicyError",
    "check_repository",
    "export_subset",
    "load_policy",
    "sha256_file",
]
