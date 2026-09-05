"""Keep malformed snapshots bounded and portable filenames usable in requests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from surface_atlas.example import create_example
from surface_atlas.structure_preview import normalized_scene, snapshot_errors
from surface_atlas.validator import validate_workspace


REPOSITORY = Path(__file__).resolve().parents[1]


def _snapshot() -> dict:
    return {
        "schema_version": "codex-surface-structure-snapshot/v0.1",
        "coordinate_sources": [
            {
                "path": "coordinates/target.pdb",
                "sha256": "a" * 64,
                "bytes": 100,
                "format": "pdb",
                "object_name": "target",
                "state": 1,
            }
        ],
        "layers": [
            {
                "object_name": "target",
                "selection": "chain A",
                "color": "#123456",
                "representation": "cartoon",
                "color_mode": "solid",
                "opacity": 1,
                "label": "Target",
            }
        ],
    }


@pytest.mark.parametrize("sources", [None, 3, True])
def test_workspace_reports_non_array_coordinate_sources_without_crashing(
    tmp_path: Path, sources: object
) -> None:
    atlas = tmp_path / "atlas"
    create_example(atlas)
    path = atlas / "targets.json"
    collection = json.loads(path.read_text(encoding="utf-8"))
    snapshot = _snapshot()
    snapshot["coordinate_sources"] = sources
    collection["records"][0]["structure_snapshot"] = snapshot
    path.write_text(json.dumps(collection), encoding="utf-8")

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert any("coordinate_sources" in error for error in result["errors"])


@pytest.mark.parametrize("field", ["object_name", "representation", "color_mode"])
@pytest.mark.parametrize("value", [[], {}])
def test_snapshot_reports_container_valued_layer_fields_without_crashing(
    field: str, value: object
) -> None:
    snapshot = _snapshot()
    snapshot["layers"][0][field] = value

    errors = snapshot_errors(snapshot)

    assert errors
    assert any(field in error for error in errors)


def test_copy_request_accepts_valid_portable_filenames_and_rejects_escape() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the browser path helper")
    script_path = REPOSITORY / "src/surface_atlas/assets/report/structure-preview.js"
    script = script_path.read_text(encoding="utf-8")
    start = script.index("  function artifactPath(")
    end = script.index("\n  function handoffMetadata(", start)
    helper = script[start:end]
    filenames = ["coordinates/target copy.pdb", "coordinates/cible-é.pdb"]
    accepted: list[str] = []
    for filename in filenames:
        snapshot = copy.deepcopy(_snapshot())
        snapshot["coordinate_sources"][0]["path"] = filename
        assert snapshot_errors(snapshot) == []
        href = "data/artifacts/" + filename
        scene = normalized_scene(snapshot, {filename: href})
        assert scene is not None
        accepted.append(scene["sources"][0]["href"])

    rejected = [
        "data/artifacts/../outside.pdb",
        "data/artifacts/coordinates/../../outside.pdb",
        "data/artifacts/coordinates/target.pdb?source=other",
        "data/artifacts/coordinates/target.pdb#other",
        "data/artifacts/coordinates\\target.pdb",
        "/data/artifacts/coordinates/target.pdb",
        "https://example.test/target.pdb",
    ]
    probe = helper + "\n" + f"""
const assert = require('node:assert/strict');
for (const path of {json.dumps(accepted)}) assert.equal(artifactPath(path), path);
for (const path of {json.dumps(rejected)}) assert.throws(() => artifactPath(path));
"""
    result = subprocess.run([node, "-"], input=probe, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
