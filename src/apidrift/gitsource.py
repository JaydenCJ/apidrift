"""Read Python source trees from git refs, directories, or dump snapshots.

apidrift shells out to the ``git`` binary (``ls-tree`` + ``cat-file``) instead
of linking a git library — that keeps the package at zero runtime
dependencies and works with every repository git itself can read. Nothing is
checked out: file contents are read straight from the object database, so the
working tree is never touched and dirty checkouts never leak into a ref diff.

Three "ref" spellings are accepted by the CLI and resolved here:

- a git rev (``v1.2.0``, ``HEAD~3``, a sha, a branch),
- a directory path (compared as-is; how the working tree is diffed),
- a ``.json`` file produced by ``apidrift dump``.
"""

from __future__ import annotations

import os
import subprocess
from typing import Dict, List, Optional, Set, Tuple

#: Sentinel ref meaning "the current working tree" (default NEW side).
WORKTREE = "WORKTREE"


class SourceError(RuntimeError):
    """Raised when a ref cannot be resolved or a package cannot be located."""


class _GitMissingError(SourceError):
    """git binary absent — kept distinct so its actionable hint survives."""


def _run_git(repo: str, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise _GitMissingError(
            "git executable not found; apidrift needs git on PATH to read refs"
        ) from None
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()
        raise SourceError(
            "git {} failed: {}".format(
                " ".join(args[:2]), detail[0] if detail else "unknown error"
            )
        )
    return proc.stdout


class GitTree:
    """Lazy view of the ``.py`` files reachable from one git ref."""

    def __init__(self, repo: str, ref: str):
        self.repo = repo
        self.ref = ref
        # Fail fast with a clear message on an unknown ref (rev-parse with
        # --quiet exits non-zero silently, so spell the diagnosis out).
        try:
            _run_git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        except _GitMissingError:
            raise
        except SourceError:
            raise SourceError(
                "cannot resolve {!r}: not a git revision in {!r}, an existing "
                "directory, or an apidrift dump .json file "
                "(use --repo to point at the right repository)".format(ref, repo)
            ) from None

    def python_files(self) -> List[str]:
        out = _run_git(self.repo, "ls-tree", "-r", "-z", "--name-only", self.ref)
        return sorted(
            path for path in out.split("\0") if path.endswith(".py")
        )

    def read(self, path: str) -> str:
        return _run_git(self.repo, "cat-file", "blob", "{}:{}".format(self.ref, path))

    def describe(self) -> str:
        return self.ref


class DirTree:
    """View of the ``.py`` files under a plain directory (or the worktree)."""

    _SKIP_DIRS = {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".eggs",
        "node_modules",
        "build",
        "dist",
    }

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        if not os.path.isdir(self.root):
            raise SourceError("not a directory: {}".format(root))

    def python_files(self) -> List[str]:
        found: List[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(
                d for d in dirnames if d not in self._SKIP_DIRS
            )
            for filename in sorted(filenames):
                if filename.endswith(".py"):
                    full = os.path.join(dirpath, filename)
                    found.append(os.path.relpath(full, self.root))
        return sorted(f.replace(os.sep, "/") for f in found)

    def read(self, path: str) -> str:
        with open(
            os.path.join(self.root, path.replace("/", os.sep)),
            "r",
            encoding="utf-8",
            errors="replace",
        ) as handle:
            return handle.read()

    def describe(self) -> str:
        return self.root


def resolve_tree(ref: str, repo: str) -> "GitTree | DirTree":
    """Turn a CLI ref argument into a readable tree."""
    if ref == WORKTREE:
        return DirTree(repo)
    if os.path.isdir(ref):
        return DirTree(ref)
    return GitTree(repo, ref)


# --------------------------------------------------------------------------
# Package discovery
# --------------------------------------------------------------------------

#: Conventional roots probed for packages, in priority order.
_CANDIDATE_ROOTS = ("src", ".", "lib")

_NON_PACKAGE_DIRS = {"tests", "test", "docs", "examples", "scripts", "benchmarks"}


def find_packages(files: List[str]) -> List[Tuple[str, str]]:
    """All importable top-level packages in a file list.

    Returns ``(root, package_name)`` pairs, e.g. ``("src", "mypkg")`` for
    ``src/mypkg/__init__.py``. Only conventional roots are probed so a
    vendored test fixture deep in the tree is never mistaken for the API.
    """
    found: List[Tuple[str, str]] = []
    for root in _CANDIDATE_ROOTS:
        prefix = "" if root == "." else root + "/"
        for path in files:
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix) :]
            parts = rest.split("/")
            if len(parts) == 2 and parts[1] == "__init__.py":
                name = parts[0]
                if name in _NON_PACKAGE_DIRS:
                    continue
                if (root, name) not in found:
                    found.append((root, name))
        if found:
            break  # src/ wins over ./ wins over lib/
    return found


def locate_package(
    tree: "GitTree | DirTree", package: Optional[str]
) -> Tuple[str, str]:
    """Find the package to analyze; ``package`` narrows an ambiguous tree."""
    files = tree.python_files()
    candidates = find_packages(files)
    if package is not None:
        for root, name in candidates:
            if name == package:
                return root, name
        raise SourceError(
            "package {!r} not found at {} (found: {})".format(
                package,
                tree.describe(),
                ", ".join(n for _, n in candidates) or "none",
            )
        )
    public = [(r, n) for r, n in candidates if not n.startswith("_")]
    pool = public or candidates
    if len(pool) == 1:
        return pool[0]
    if not pool:
        raise SourceError(
            "no package (a directory with __init__.py under ./, src/ or "
            "lib/) found at {}".format(tree.describe())
        )
    raise SourceError(
        "multiple packages found at {}: {}; pick one with --package".format(
            tree.describe(), ", ".join(n for _, n in pool)
        )
    )


def load_package_sources(
    tree: "GitTree | DirTree", root: str, package: str
) -> Tuple[Dict[str, str], Set[str]]:
    """Read every module of ``package`` from ``tree``.

    Returns ``(sources, init_modules)`` where ``sources`` maps dotted module
    names to source text and ``init_modules`` is the set of dotted names
    that came from an ``__init__.py``.
    """
    prefix = ("" if root == "." else root + "/") + package + "/"
    sources: Dict[str, str] = {}
    init_modules: Set[str] = set()
    for path in tree.python_files():
        if not path.startswith(prefix):
            continue
        rest = path[len(prefix) :]
        parts = rest.split("/")
        if parts[-1] == "__init__.py":
            dotted = ".".join([package] + parts[:-1])
            init_modules.add(dotted)
        else:
            dotted = ".".join([package] + parts)[: -len(".py")]
        sources[dotted] = tree.read(path)
    if not sources:
        raise SourceError(
            "package {!r} has no Python files at {}".format(
                package, tree.describe()
            )
        )
    return sources, init_modules


def read_file(tree: "GitTree | DirTree", path: str) -> Optional[str]:
    """Read one non-package file (e.g. ``pyproject.toml``); None if absent."""
    if isinstance(tree, DirTree):
        full = os.path.join(tree.root, path)
        if not os.path.isfile(full):
            return None
        with open(full, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    try:
        return _run_git(
            tree.repo, "cat-file", "blob", "{}:{}".format(tree.ref, path)
        )
    except SourceError:
        return None
