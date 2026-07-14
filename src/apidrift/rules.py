"""Change taxonomy: every kind of API change apidrift can report.

Each change kind carries a fixed severity. The mapping is the contract that
``docs/rules.md`` documents and the test suite pins down — if a kind's
severity changes, that is itself a breaking change of apidrift.

Severity semantics follow SemVer for a package at ``>= 1.0.0``:

- ``major``  — existing callers can break.
- ``minor``  — new surface; existing callers keep working.
- ``patch``  — visible in the source but compatible at call sites
  (annotations, default values, re-export plumbing).

The pre-1.0 remapping (major -> minor, minor -> patch) happens later, in
:mod:`apidrift.semver`, so the rule table stays version-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MAJOR = "major"
MINOR = "minor"
PATCH = "patch"
NONE = "none"

#: Severity ordering used to pick the suggested bump.
SEVERITY_RANK = {MAJOR: 3, MINOR: 2, PATCH: 1, NONE: 0}

#: kind -> severity. Keep alphabetized within each severity block.
KIND_SEVERITY = {
    # -- major: removals and call-compatibility breaks -----------------------
    "async-changed": MAJOR,
    "attribute-removed": MAJOR,
    "base-removed": MAJOR,
    "class-removed": MAJOR,
    "enum-member-removed": MAJOR,
    "function-removed": MAJOR,
    "method-removed": MAJOR,
    "method-became-abstract": MAJOR,
    "module-removed": MAJOR,
    "param-added-required": MAJOR,
    "param-became-keyword-only": MAJOR,
    "param-became-positional-only": MAJOR,
    "param-default-removed": MAJOR,
    "param-removed": MAJOR,
    "param-renamed": MAJOR,
    "param-reordered": MAJOR,
    "property-setter-removed": MAJOR,
    "reexport-removed": MAJOR,
    "role-changed": MAJOR,
    "symbol-kind-changed": MAJOR,
    "var-keyword-removed": MAJOR,
    "var-positional-removed": MAJOR,
    "variable-removed": MAJOR,
    # -- minor: pure additions ------------------------------------------------
    "attribute-added": MINOR,
    "base-added": MINOR,
    "class-added": MINOR,
    "enum-member-added": MINOR,
    "function-added": MINOR,
    "method-added": MINOR,
    "method-became-concrete": MINOR,
    "module-added": MINOR,
    "param-added-optional": MINOR,
    "param-became-flexible": MINOR,
    "param-default-added": MINOR,
    "property-setter-added": MINOR,
    "reexport-added": MINOR,
    "var-keyword-added": MINOR,
    "var-positional-added": MINOR,
    "variable-added": MINOR,
    # -- patch: compatible, but worth surfacing --------------------------------
    "annotation-changed": PATCH,
    "param-default-value-changed": PATCH,
    "param-renamed-positional-only": PATCH,
    "reexport-target-changed": PATCH,
    "return-annotation-changed": PATCH,
    "variable-value-changed": PATCH,
}


@dataclass
class Change:
    """One observed API change, anchored to a dotted symbol path."""

    kind: str
    symbol: str  # e.g. "pkg.client.Client.fetch"
    message: str
    old: Optional[str] = None  # old-side detail (signature, value, ...)
    new: Optional[str] = None  # new-side detail

    @property
    def severity(self) -> str:
        return KIND_SEVERITY[self.kind]

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "symbol": self.symbol,
            "message": self.message,
            "old": self.old,
            "new": self.new,
        }


def max_severity(changes) -> str:
    """The highest severity present in ``changes`` (``none`` when empty)."""
    best = NONE
    for change in changes:
        if SEVERITY_RANK[change.severity] > SEVERITY_RANK[best]:
            best = change.severity
        if best == MAJOR:
            break
    return best
