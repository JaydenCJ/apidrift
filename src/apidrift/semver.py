"""Semantic-version arithmetic: suggest, apply, and verify bumps.

apidrift only ever *suggests*; the policy encoded here is deliberately
conservative and explicit:

- At ``>= 1.0.0``, the SemVer spec applies directly: breaking -> major,
  additive -> minor, compatible -> patch.
- Before 1.0.0, the spec technically allows anything, but the ecosystem
  convention (shared with Cargo) is one notch down: breaking -> minor,
  additive/compatible -> patch. :func:`required_bump_for` implements that
  remapping when it knows the current version.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Tuple

from .rules import MAJOR, MINOR, NONE, PATCH, max_severity

_VERSION_RE = re.compile(
    r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+.]?(?P<rest>[0-9A-Za-z.\-+]*))?\s*$"
)

_BUMP_RANK = {MAJOR: 3, MINOR: 2, PATCH: 1, NONE: 0}


class VersionError(ValueError):
    """Raised for version strings apidrift cannot interpret."""


def parse_version(text: str) -> Tuple[int, int, int]:
    """Parse ``[v]MAJOR.MINOR[.PATCH][pre-release]`` into a 3-tuple.

    Pre-release/build suffixes are tolerated and ignored; apidrift compares
    release positions only.
    """
    match = _VERSION_RE.match(text)
    if match is None:
        raise VersionError("cannot parse version: {!r}".format(text))
    major, minor, patch = match.group(1), match.group(2), match.group(3)
    return int(major), int(minor), int(patch or 0)


def required_bump(changes: Iterable) -> str:
    """Version-independent bump implied by a change list (SemVer >= 1.0.0)."""
    return max_severity(changes)


def required_bump_for(changes: Iterable, current_version: Optional[str]) -> str:
    """Bump required from ``current_version``, applying the pre-1.0 remap."""
    bump = required_bump(changes)
    if current_version is None:
        return bump
    major, _, _ = parse_version(current_version)
    if major == 0:
        if bump == MAJOR:
            return MINOR
        if bump == MINOR:
            return PATCH
    return bump


def next_version(current: str, bump: str) -> str:
    """Smallest version after ``current`` that satisfies ``bump``."""
    major, minor, patch = parse_version(current)
    if bump == MAJOR:
        return "{}.0.0".format(major + 1)
    if bump == MINOR:
        return "{}.{}.0".format(major, minor + 1)
    if bump == PATCH:
        return "{}.{}.{}".format(major, minor, patch + 1)
    if bump == NONE:
        return "{}.{}.{}".format(major, minor, patch)
    raise VersionError("unknown bump: {!r}".format(bump))


def actual_bump(old_version: str, new_version: str) -> str:
    """Which position was bumped going from ``old_version`` to ``new_version``.

    Raises :class:`VersionError` if the new version is not greater than or
    equal to the old one — apidrift cannot reason about version rollbacks.
    """
    old = parse_version(old_version)
    new = parse_version(new_version)
    if new < old:
        raise VersionError(
            "version went backwards: {} -> {}".format(old_version, new_version)
        )
    if new[0] > old[0]:
        return MAJOR
    if new[1] > old[1]:
        return MINOR
    if new[2] > old[2]:
        return PATCH
    return NONE


def is_sufficient(old_version: str, new_version: str, changes: Iterable) -> bool:
    """True when the declared version step covers the observed API changes."""
    needed = required_bump_for(changes, old_version)
    got = actual_bump(old_version, new_version)
    return _BUMP_RANK[got] >= _BUMP_RANK[needed]


_PROJECT_SECTION_RE = re.compile(r"^\[project\]\s*$", re.MULTILINE)
_SECTION_RE = re.compile(r"^\[", re.MULTILINE)
_VERSION_LINE_RE = re.compile(
    r"""^\s*version\s*=\s*["']([^"']+)["']""", re.MULTILINE
)


def read_project_version(pyproject_text: str) -> Optional[str]:
    """Best-effort ``[project] version`` reader for ``pyproject.toml`` text.

    Deliberately not a full TOML parser (that would be a dependency);
    it finds the ``[project]`` table and the first ``version = "..."`` line
    inside it. Returns ``None`` when no static version is declared (e.g.
    ``dynamic = ["version"]``), in which case the CLI asks the user to pass
    ``--old-version`` / ``--new-version`` explicitly.
    """
    section = _PROJECT_SECTION_RE.search(pyproject_text)
    if section is None:
        return None
    rest = pyproject_text[section.end() :]
    next_section = _SECTION_RE.search(rest)
    body = rest[: next_section.start()] if next_section else rest
    match = _VERSION_LINE_RE.search(body)
    return match.group(1) if match else None
