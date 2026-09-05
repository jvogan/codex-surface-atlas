"""Safe, project-local installation of the packaged agent skill."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .version import __version__


SKILL_NAME = "codex-surface-targets"
INSTALL_MANIFEST = ".surface-atlas-skill.json"
MANIFEST_SCHEMA = "surface-atlas-skill-install/v1"


class SkillInstallError(ValueError):
    """Raised when a skill install or uninstall is unsafe."""


def _skill_source() -> Path:
    return Path(__file__).resolve().parent / "skill"


def _managed_files() -> list[str]:
    source = _skill_source()
    if not source.is_dir():
        raise SkillInstallError("packaged skill resources are unavailable")
    files: list[str] = []
    for path in source.rglob("*"):
        if path.is_symlink():
            raise SkillInstallError("packaged skill resources contain a symlink")
        if path.is_file():
            files.append(path.relative_to(source).as_posix())
        elif not path.is_dir():
            raise SkillInstallError("packaged skill resources contain an unsupported file type")
    files = [path for path in files if path != INSTALL_MANIFEST and "__pycache__" not in PurePosixPath(path).parts]
    if "SKILL.md" not in files:
        raise SkillInstallError("packaged skill is missing SKILL.md")
    return sorted(files)


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SkillInstallError("could not read a managed skill file") from exc


def _manifest_payload(files: list[str], source: Path) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA,
        "package": "codex-surface-atlas",
        "package_version": __version__,
        "skill_name": SKILL_NAME,
        "managed_files": [{"path": name, "sha256": _digest(source / name)} for name in files],
    }


def _safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise SkillInstallError("skill manifest contains an unsafe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise SkillInstallError("skill manifest contains an unsafe relative path")
    return value


def _read_manifest(destination: Path) -> tuple[dict[str, Any], list[str]]:
    path = destination / INSTALL_MANIFEST
    if path.is_symlink():
        raise SkillInstallError("skill installation manifest must not be a symlink")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillInstallError("destination is not a managed Surface Atlas skill installation") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SkillInstallError("skill installation manifest is invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != MANIFEST_SCHEMA:
        raise SkillInstallError("destination is not a managed Surface Atlas skill installation")
    if payload.get("package") != "codex-surface-atlas" or payload.get("skill_name") != SKILL_NAME:
        raise SkillInstallError("skill installation manifest belongs to another package")
    raw_files = payload.get("managed_files")
    if not isinstance(raw_files, list) or not raw_files:
        raise SkillInstallError("skill installation manifest has no managed files")
    files: list[str] = []
    for item in raw_files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise SkillInstallError("skill installation manifest has an invalid file entry")
        name = _safe_relative(item["path"])
        if len(item["sha256"]) != 64 or any(ch not in "0123456789abcdef" for ch in item["sha256"]):
            raise SkillInstallError("skill installation manifest has an invalid file digest")
        files.append(name)
    if len(files) != len(set(files)):
        raise SkillInstallError("skill installation manifest contains duplicate files")
    return payload, files


def _expected_entries(files: list[str]) -> set[str]:
    entries = set(files) | {INSTALL_MANIFEST}
    for name in files:
        parent = PurePosixPath(name).parent
        while parent.parts:
            entries.add(parent.as_posix())
            parent = parent.parent
    return entries


def _destination_entries(destination: Path) -> set[str]:
    try:
        return {path.relative_to(destination).as_posix() for path in destination.rglob("*")}
    except OSError as exc:
        raise SkillInstallError("could not inspect the skill destination") from exc


def _default_destination() -> Path:
    """Return a project-local default; never target a user's global skill dir."""

    return Path.cwd() / ".surface-atlas" / "skills" / SKILL_NAME


def install_skill(destination: str | Path | None = None, *, force: bool = False) -> dict[str, Any]:
    """Install the packaged skill transactionally at *destination*.

    The destination is the skill directory itself.  It must not already exist;
    this avoids replacing an empty directory or files that happen to share the
    requested name.  Repeating an install against an existing managed copy is
    reported as ``already_installed`` after its manifest and hashes are checked.
    """

    del force  # Replacement is intentionally never permitted by this installer.
    destination = _default_destination() if destination is None else Path(destination)
    source = _skill_source()
    files = _managed_files()
    if destination.is_symlink():
        raise SkillInstallError("skill destination must not be a symlink")
    if destination.exists():
        if not destination.is_dir():
            raise SkillInstallError("skill destination is not a directory")
        try:
            manifest, managed = _read_manifest(destination)
        except SkillInstallError as exc:
            raise SkillInstallError("refusing to replace an unmanaged destination") from exc
        expected_manifest = _manifest_payload(files, source)
        expected_files = {item["path"]: item["sha256"] for item in expected_manifest["managed_files"]}
        if managed != files or manifest.get("package_version") != __version__:
            raise SkillInstallError("existing skill installation has a different file set")
        expected = {item["path"]: item["sha256"] for item in manifest["managed_files"]}
        if expected != expected_files:
            raise SkillInstallError("existing skill installation is from a different package version")
        if _destination_entries(destination) != _expected_entries(files):
            raise SkillInstallError("existing skill installation contains unmanaged files")
        for name in files:
            path = destination / name
            if path.is_symlink() or not path.is_file() or _digest(path) != expected[name]:
                raise SkillInstallError(f"existing skill file is modified or unsafe: {name}")
        return {
            "skill_name": SKILL_NAME,
            "destination": str(destination),
            "installed": False,
            "already_installed": True,
            "managed_file_count": len(files),
        }

    parent = destination.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SkillInstallError("could not create the skill destination parent") from exc
    created_files: list[Path] = []
    created_dirs: list[Path] = []
    try:
        # mkdir is exclusive.  In particular, it does not replace a race-created
        # empty directory the way a directory rename can on POSIX.
        destination.mkdir()
        for name in files:
            target = destination / name
            if not target.parent.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                created_dirs.append(target.parent)
            shutil.copyfile(source / name, target)
            created_files.append(target)
        manifest = _manifest_payload(files, source)
        manifest_path = destination / INSTALL_MANIFEST
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        created_files.append(manifest_path)
    except FileExistsError as exc:
        raise SkillInstallError("refusing to replace an existing destination") from exc
    except OSError as exc:
        for path in reversed(created_files):
            try:
                path.unlink()
            except OSError:
                pass
        for directory in sorted(created_dirs, key=lambda path: len(path.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            destination.rmdir()
        except OSError:
            pass
        raise SkillInstallError("could not install skill") from exc
    return {
        "skill_name": SKILL_NAME,
        "destination": str(destination),
        "installed": True,
        "already_installed": False,
        "managed_file_count": len(files),
    }


def uninstall_skill(destination: str | Path | None = None) -> dict[str, Any]:
    """Remove only a verified, package-managed skill installation."""

    destination = _default_destination() if destination is None else Path(destination)
    if destination.is_symlink():
        raise SkillInstallError("refusing to remove a non-directory skill destination")
    if not destination.exists():
        return {
            "skill_name": SKILL_NAME,
            "destination": str(destination),
            "removed": False,
            "not_installed": True,
        }
    if not destination.is_dir():
        raise SkillInstallError("refusing to remove a non-directory skill destination")
    manifest, files = _read_manifest(destination)
    current_files = _managed_files()
    if files != current_files or manifest.get("package") != "codex-surface-atlas":
        raise SkillInstallError("refusing to remove a skill installation with an unknown file set")
    current_manifest = _manifest_payload(current_files, _skill_source())
    if manifest.get("package_version") != __version__ or manifest.get("managed_files") != current_manifest["managed_files"]:
        raise SkillInstallError("refusing to remove a skill installation from a different package build")
    expected = {item["path"]: item["sha256"] for item in manifest["managed_files"]}
    if _destination_entries(destination) != _expected_entries(files):
        raise SkillInstallError("refusing to remove a skill directory containing unmanaged files")
    for name in files:
        path = destination / name
        if path.is_symlink() or not path.is_file() or _digest(path) != expected[name]:
            raise SkillInstallError(f"refusing to remove modified or unsafe skill file: {name}")
    try:
        staging_root = Path(tempfile.mkdtemp(prefix=".surface-atlas-uninstall-", dir=destination.parent))
    except OSError as exc:
        raise SkillInstallError("could not create uninstall staging directory") from exc
    staged = staging_root / "skill"
    try:
        os.rename(destination, staged)
    except OSError as exc:
        try:
            staging_root.rmdir()
        except OSError:
            pass
        raise SkillInstallError("could not stage the skill for removal") from exc
    try:
        shutil.rmtree(staged)
        staging_root.rmdir()
    except OSError as exc:
        if staged.exists() and not destination.exists():
            try:
                os.rename(staged, destination)
            except OSError:
                pass
        try:
            staging_root.rmdir()
        except OSError:
            pass
        raise SkillInstallError("could not remove the staged skill installation") from exc
    return {
        "skill_name": SKILL_NAME,
        "destination": str(destination),
        "removed": True,
        "not_installed": False,
    }
