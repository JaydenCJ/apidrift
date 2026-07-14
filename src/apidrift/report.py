"""Render a change list as text, Markdown, or JSON.

All three formats are deterministic for a given diff: the change order comes
from :mod:`apidrift.diffing` (sorted) and JSON keys are sorted, so reports
can be committed, diffed, and asserted on in CI.
"""

from __future__ import annotations

import json
from typing import List, Optional

from .rules import MAJOR, MINOR, NONE, PATCH, Change

_SEVERITY_LABEL = {MAJOR: "MAJOR", MINOR: "MINOR", PATCH: "PATCH"}
_SEVERITY_ORDER = (MAJOR, MINOR, PATCH)


def _counts(changes: List[Change]) -> dict:
    counts = {MAJOR: 0, MINOR: 0, PATCH: 0}
    for change in changes:
        counts[change.severity] += 1
    return counts


def summary_line(changes: List[Change]) -> str:
    counts = _counts(changes)
    return "{} breaking, {} addition{}, {} compatible".format(
        counts[MAJOR],
        counts[MINOR],
        "" if counts[MINOR] == 1 else "s",
        counts[PATCH],
    )


def bump_line(bump: str, current_version: Optional[str], next_ver: Optional[str]) -> str:
    if bump == NONE:
        return "suggested bump: none (no public API changes)"
    if current_version and next_ver:
        return "suggested bump: {} ({} -> {})".format(bump, current_version, next_ver)
    return "suggested bump: {}".format(bump)


def format_text(
    changes: List[Change],
    old_label: str,
    new_label: str,
    package: str,
    bump: str,
    current_version: Optional[str] = None,
    next_ver: Optional[str] = None,
) -> str:
    lines = [
        "apidrift: {} -> {} (package {})".format(old_label, new_label, package),
        "",
    ]
    if not changes:
        lines.append("no public API changes")
    for severity in _SEVERITY_ORDER:
        for change in changes:
            if change.severity != severity:
                continue
            lines.append(
                "{:<6} {}: {}".format(
                    _SEVERITY_LABEL[severity], change.symbol, change.message
                )
            )
    lines.append("")
    if changes:
        lines.append(summary_line(changes))
    lines.append(bump_line(bump, current_version, next_ver))
    return "\n".join(lines) + "\n"


def format_markdown(
    changes: List[Change],
    old_label: str,
    new_label: str,
    package: str,
    bump: str,
    current_version: Optional[str] = None,
    next_ver: Optional[str] = None,
) -> str:
    lines = [
        "## API diff: `{}` -> `{}` (`{}`)".format(old_label, new_label, package),
        "",
    ]
    if not changes:
        lines.append("No public API changes.")
    else:
        lines.append("| Severity | Symbol | Change |")
        lines.append("|---|---|---|")
        for severity in _SEVERITY_ORDER:
            for change in changes:
                if change.severity != severity:
                    continue
                lines.append(
                    "| {} | `{}` | {} |".format(
                        _SEVERITY_LABEL[severity],
                        change.symbol,
                        change.message.replace("|", "\\|"),
                    )
                )
        lines.append("")
        lines.append("**{}.**".format(summary_line(changes)))
    lines.append("")
    lines.append("**{}**".format(bump_line(bump, current_version, next_ver)))
    return "\n".join(lines) + "\n"


def format_json(
    changes: List[Change],
    old_label: str,
    new_label: str,
    package: str,
    bump: str,
    current_version: Optional[str] = None,
    next_ver: Optional[str] = None,
) -> str:
    counts = _counts(changes)
    payload = {
        "package": package,
        "old": old_label,
        "new": new_label,
        "changes": [change.to_dict() for change in changes],
        "counts": {
            "major": counts[MAJOR],
            "minor": counts[MINOR],
            "patch": counts[PATCH],
        },
        "suggested_bump": bump,
        "current_version": current_version,
        "next_version": next_ver,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


FORMATTERS = {
    "text": format_text,
    "markdown": format_markdown,
    "json": format_json,
}
