from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "surface_atlas", *(str(argument) for argument in arguments)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_skill_destination_is_required_without_traceback() -> None:
    result = _run("install-skill")
    assert result.returncode == 2
    assert "--destination" in result.stderr
    assert "Traceback" not in result.stderr


def test_skill_error_does_not_echo_absolute_machine_path(tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    result = _run("install-skill", "--destination", destination)
    assert result.returncode == 1
    assert str(destination) not in result.stderr
    assert "Traceback" not in result.stderr


def test_init_collision_does_not_echo_absolute_machine_path(tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    result = _run("init", "safe-atlas", destination, "--disease", "Synthetic")
    assert result.returncode == 1
    assert str(destination) not in result.stderr
    assert "output directory already exists" in result.stderr


@pytest.mark.parametrize("command", ["init", "example", "report"])
def test_output_with_file_parent_gives_actionable_error(tmp_path: Path, command: str) -> None:
    parent = tmp_path / "parent-file"
    parent.write_text("existing file", encoding="utf-8")
    if command == "init":
        result = _run(command, "safe-atlas", parent / "atlas", "--disease", "Synthetic")
    elif command == "example":
        result = _run(command, parent / "atlas")
    else:
        source = Path(__file__).resolve().parents[1] / "examples" / "synthetic-atlas"
        result = _run(command, source, "--output-root", parent / "reports", "--run-id", "new-report")

    assert result.returncode == 1
    assert "beneath a writable directory" in result.stderr
    assert "Traceback" not in result.stderr
    assert str(tmp_path) not in result.stderr
    assert parent.read_text(encoding="utf-8") == "existing file"


def test_synthetic_example_validates_through_cli(tmp_path: Path) -> None:
    destination = tmp_path / "example"
    created = _run("example", destination, "--json")
    assert created.returncode == 0, created.stderr
    payload = json.loads(created.stdout)
    assert payload["synthetic"] is True
    assert payload["targets"] == 3

    validated = _run("validate", destination, "--json")
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["valid"] is True
