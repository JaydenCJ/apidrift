"""Command-line interface for apidrift.

Subcommands:

- ``apidrift diff OLD [NEW]``  — full report of API changes between two refs.
- ``apidrift bump OLD [NEW]``  — print just the suggested bump word.
- ``apidrift check OLD [NEW]`` — verify the declared version step covers the
  observed changes; exit 1 when it does not (the CI gate).
- ``apidrift dump REF``        — write a JSON snapshot of the API surface,
  usable later as either side of a diff.

Exit codes: 0 success, 1 gate failure (``check`` insufficient bump, or
``diff --fail-on`` threshold reached), 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Tuple

from . import __version__
from .extract import ExtractError, extract_package
from .gitsource import (
    WORKTREE,
    SourceError,
    load_package_sources,
    locate_package,
    read_file,
    resolve_tree,
)
from .model import Package
from .report import FORMATTERS
from .rules import MAJOR, MINOR, NONE, PATCH, SEVERITY_RANK
from .semver import (
    VersionError,
    actual_bump,
    is_sufficient,
    next_version,
    read_project_version,
    required_bump_for,
)


class CliError(Exception):
    """User-facing error; printed to stderr with exit code 2."""


def _load_side(
    ref: str, repo: str, package: Optional[str], include_private: bool
) -> Tuple[Package, str, Optional[str]]:
    """Load one side of a diff.

    Returns ``(api, label, declared_version)``. The ref may be a git rev, a
    directory, or an ``apidrift dump`` JSON snapshot.
    """
    if ref.endswith(".json") and os.path.isfile(ref):
        with open(ref, "r", encoding="utf-8") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as exc:
                raise CliError("{}: not a valid snapshot: {}".format(ref, exc))
        try:
            api = Package.from_dict(data)
        except (KeyError, ValueError) as exc:
            raise CliError("{}: {}".format(ref, exc))
        return api, ref, data.get("project_version")

    tree = resolve_tree(ref, repo)
    root, name = locate_package(tree, package)
    sources, init_modules = load_package_sources(tree, root, name)
    api = extract_package(
        sources, name, include_private=include_private, init_modules=init_modules
    )
    pyproject = read_file(tree, "pyproject.toml")
    declared = read_project_version(pyproject) if pyproject else None
    label = "worktree" if ref == WORKTREE else ref
    return api, label, declared


def _diff_sides(args) -> Tuple[list, str, str, str, Optional[str], Optional[str]]:
    old_api, old_label, old_version = _load_side(
        args.old, args.repo, args.package, args.include_private
    )
    new_api, new_label, new_version = _load_side(
        args.new, args.repo, args.package, args.include_private
    )
    if old_api.name != new_api.name:
        raise CliError(
            "comparing different packages: {!r} vs {!r} "
            "(use --package to pin one)".format(old_api.name, new_api.name)
        )
    from .diffing import diff_packages

    changes = diff_packages(old_api, new_api)
    return changes, old_label, new_label, old_api.name, old_version, new_version


def _cmd_diff(args) -> int:
    changes, old_label, new_label, package, old_version, _ = _diff_sides(args)
    bump = required_bump_for(changes, old_version)
    next_ver = next_version(old_version, bump) if old_version else None
    formatter = FORMATTERS[args.format]
    sys.stdout.write(
        formatter(
            changes,
            old_label,
            new_label,
            package,
            bump,
            current_version=old_version,
            next_ver=next_ver,
        )
    )
    if args.fail_on != "never":
        worst = max(
            (SEVERITY_RANK[c.severity] for c in changes), default=SEVERITY_RANK[NONE]
        )
        if worst >= SEVERITY_RANK[args.fail_on]:
            return 1
    return 0


def _cmd_bump(args) -> int:
    changes, _, _, _, old_version, _ = _diff_sides(args)
    print(required_bump_for(changes, old_version))
    return 0


def _cmd_check(args) -> int:
    changes, old_label, new_label, package, old_declared, new_declared = _diff_sides(
        args
    )
    old_version = args.old_version or old_declared
    new_version = args.new_version or new_declared
    if old_version is None or new_version is None:
        raise CliError(
            "could not read a static [project] version from pyproject.toml "
            "on both refs; pass --old-version and --new-version"
        )
    needed = required_bump_for(changes, old_version)
    stepped = actual_bump(old_version, new_version)
    ok = is_sufficient(old_version, new_version, changes)
    print(
        "apidrift check: {} ({}) -> {} ({}), package {}".format(
            old_label, old_version, new_label, new_version, package
        )
    )
    print("required bump: {}, declared bump: {}".format(needed, stepped))
    if ok:
        print("OK: declared version covers the API changes")
        return 0
    print(
        "FAIL: API changes require at least a {} bump "
        "(e.g. {})".format(needed, next_version(old_version, needed)),
        file=sys.stderr,
    )
    return 1


def _cmd_dump(args) -> int:
    api, _, declared = _load_side(
        args.ref, args.repo, args.package, args.include_private
    )
    payload = api.to_dict()
    payload["project_version"] = declared
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        default=".",
        help="repository to read refs from (default: current directory)",
    )
    parser.add_argument(
        "--package",
        help="top-level package to analyze (default: auto-detected)",
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="also track underscore-prefixed modules and names",
    )


def _add_ref_pair(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("old", help="old side: git ref, directory, or dump .json")
    parser.add_argument(
        "new",
        nargs="?",
        default=WORKTREE,
        help="new side (default: the working tree)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apidrift",
        description=(
            "Diff a Python package's public API between git refs and suggest "
            "the semver bump. AST-based: the package is never imported."
        ),
    )
    parser.add_argument(
        "--version", action="version", version="apidrift {}".format(__version__)
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_diff = sub.add_parser(
        "diff", help="report all public API changes between two refs"
    )
    _add_ref_pair(p_diff)
    _add_common(p_diff)
    p_diff.add_argument(
        "--format",
        choices=sorted(FORMATTERS),
        default="text",
        help="output format (default: text)",
    )
    p_diff.add_argument(
        "--fail-on",
        choices=[MAJOR, MINOR, PATCH, "never"],
        default="never",
        help="exit 1 when a change of this severity (or worse) is found",
    )
    p_diff.set_defaults(func=_cmd_diff)

    p_bump = sub.add_parser(
        "bump", help="print only the suggested bump: major/minor/patch/none"
    )
    _add_ref_pair(p_bump)
    _add_common(p_bump)
    p_bump.set_defaults(func=_cmd_bump)

    p_check = sub.add_parser(
        "check",
        help="verify the declared version step covers the API changes (CI gate)",
    )
    _add_ref_pair(p_check)
    _add_common(p_check)
    p_check.add_argument(
        "--old-version", help="override the old side's declared version"
    )
    p_check.add_argument(
        "--new-version", help="override the new side's declared version"
    )
    p_check.set_defaults(func=_cmd_check)

    p_dump = sub.add_parser(
        "dump", help="write a JSON snapshot of the API surface at a ref"
    )
    p_dump.add_argument("ref", help="git ref or directory to snapshot")
    _add_common(p_dump)
    p_dump.add_argument(
        "-o",
        "--output",
        default="-",
        help="output file (default: stdout)",
    )
    p_dump.set_defaults(func=_cmd_dump)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (CliError, SourceError, ExtractError, VersionError) as exc:
        print("apidrift: error: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
