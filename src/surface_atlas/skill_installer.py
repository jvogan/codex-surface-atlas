"""Compatibility import for the package skill lifecycle API."""

from .installer import (
    INSTALL_MANIFEST,
    MANIFEST_SCHEMA,
    SKILL_NAME,
    SkillInstallError,
    install_skill,
    uninstall_skill,
)

__all__ = [
    "INSTALL_MANIFEST",
    "MANIFEST_SCHEMA",
    "SKILL_NAME",
    "SkillInstallError",
    "install_skill",
    "uninstall_skill",
]

