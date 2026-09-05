"""Keep the plugin skill payload aligned with the Python package payload."""

from __future__ import annotations

import json
from pathlib import Path

from surface_atlas.installer import _managed_files


REPOSITORY = Path(__file__).resolve().parents[1]
PACKAGE_SKILL = REPOSITORY / "src" / "surface_atlas" / "skill"
PLUGIN_SKILL = REPOSITORY / "skills" / "codex-surface-targets"


def _files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }


def test_plugin_skill_tree_matches_packaged_skill_tree() -> None:
    """The plugin carries the same skill, references, and assets as the wheel."""
    assert PACKAGE_SKILL.is_dir()
    assert PLUGIN_SKILL.is_dir()
    assert not any(path.is_symlink() for path in PLUGIN_SKILL.rglob("*"))

    package_files = _files(PACKAGE_SKILL)
    plugin_files = _files(PLUGIN_SKILL)
    assert plugin_files.keys() == package_files.keys()

    for relative_path, package_file in package_files.items():
        assert plugin_files[relative_path].read_bytes() == package_file.read_bytes()


def test_plugin_manifest_uses_plugin_skill_root() -> None:
    manifest = json.loads(
        (REPOSITORY / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["skills"] == "./skills/"


def test_skill_installer_manages_agent_descriptor() -> None:
    assert "agents/openai.yaml" in _managed_files()
