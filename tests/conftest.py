"""Shared fixtures and helpers for the apidrift test suite.

Everything is offline and deterministic: git fixtures are created in
``tmp_path`` with pinned author/committer identities, and module fixtures
are inline source strings parsed by the extractor.
"""

from __future__ import annotations

import subprocess
import textwrap
from typing import List

import pytest

from apidrift.diffing import diff_packages
from apidrift.extract import extract_module, extract_package
from apidrift.rules import Change


def extract_src(source: str, name: str = "m", **kwargs):
    """Extract a single module from dedented inline source."""
    return extract_module(textwrap.dedent(source), name, **kwargs)


def diff_src(old: str, new: str, **kwargs) -> List[Change]:
    """Diff two versions of a single-module package given as inline source."""
    old_pkg = extract_package({"m": textwrap.dedent(old)}, "m", **kwargs)
    new_pkg = extract_package({"m": textwrap.dedent(new)}, "m", **kwargs)
    return diff_packages(old_pkg, new_pkg)


def kinds(changes: List[Change]) -> List[str]:
    return [change.kind for change in changes]


def git(repo, *args: str) -> str:
    """Run git in ``repo`` with a pinned identity so commits are reproducible."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=dev@example.test",
            "-c",
            "user.name=apidrift tests",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


@pytest.fixture
def git_repo(tmp_path):
    """An empty initialized git repository on the default branch ``main``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    return repo


def commit_package(repo, files: dict, message: str, version: str = "0.0.0") -> None:
    """Write ``files`` (relative path -> source) plus a pyproject, then commit.

    Existing files from earlier commits are left in place unless overwritten,
    mirroring how real history accretes.
    """
    for rel, source in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "{}"\n'.format(version),
        encoding="utf-8",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
