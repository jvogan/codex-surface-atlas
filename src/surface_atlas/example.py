"""Create the small, visibly synthetic atlas shipped with the package."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


class ExampleError(ValueError):
    """Raised when the synthetic example cannot be created safely."""


@dataclass(frozen=True)
class ExampleResult:
    directory: str
    atlas_id: str
    targets: int

    def to_dict(self) -> dict[str, object]:
        return {
            "directory": self.directory,
            "atlas_id": self.atlas_id,
            "targets": self.targets,
            "synthetic": True,
            "network_or_provider_calls": False,
        }


def _example_source() -> Path:
    return Path(__file__).resolve().parent / "assets" / "synthetic-atlas"


def create_example(output_directory: str | Path) -> ExampleResult:
    """Copy the packaged synthetic fixture to a new destination.

    The destination must not exist.  The fixture contains three invented
    targets and no source snapshots, credentials, provider receipts, or local
    workstation paths.
    """

    destination = Path(output_directory)
    if destination.exists():
        raise ExampleError(f"refusing to overwrite existing path: {destination}")
    source = _example_source()
    if not source.is_dir():  # pragma: no cover - package corruption guard
        raise ExampleError("packaged synthetic example is unavailable")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source, destination)
    except FileExistsError as exc:
        raise ExampleError(f"refusing to overwrite existing path: {destination}") from exc
    except OSError as exc:
        raise ExampleError(f"could not create synthetic example: {exc}") from exc
    return ExampleResult(str(destination.resolve()), "synthetic-surface-atlas", 3)
