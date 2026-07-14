"""Reading source trees: git refs, directories, package discovery."""

import pytest

from apidrift.gitsource import (
    DirTree,
    GitTree,
    SourceError,
    find_packages,
    load_package_sources,
    locate_package,
    read_file,
    resolve_tree,
)

from conftest import commit_package, git, git_repo  # noqa: F401  (fixture)


def test_git_tree_lists_only_python_files(git_repo):
    commit_package(
        git_repo,
        {"src/demo/__init__.py": "", "src/demo/api.py": "def f(): pass"},
        "v1",
    )
    (git_repo / "notes.txt").write_text("hi", encoding="utf-8")
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "-q", "-m", "notes")
    tree = GitTree(str(git_repo), "HEAD")
    assert tree.python_files() == ["src/demo/__init__.py", "src/demo/api.py"]


def test_git_tree_reads_the_committed_content_not_the_worktree(git_repo):
    commit_package(git_repo, {"src/demo/__init__.py": "X = 1"}, "v1")
    # Dirty the worktree; the ref must still see the committed content.
    (git_repo / "src/demo/__init__.py").write_text("X = 2", encoding="utf-8")
    tree = GitTree(str(git_repo), "HEAD")
    assert tree.read("src/demo/__init__.py") == "X = 1"


def test_git_tree_rejects_unknown_refs_with_an_actionable_message(git_repo):
    commit_package(git_repo, {"src/demo/__init__.py": ""}, "v1")
    # A typo'd tag is the most common user error; the message must name the
    # bad ref and list what a ref may be, not echo raw git plumbing.
    with pytest.raises(SourceError, match="cannot resolve 'no-such-ref'"):
        GitTree(str(git_repo), "no-such-ref")


def test_dir_tree_walks_skips_junk_and_wins_ref_resolution(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "junk.py").write_text("", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("", encoding="utf-8")
    tree = DirTree(str(tmp_path))
    assert tree.python_files() == ["pkg/__init__.py"]
    # An existing directory is taken as a directory, never as a git rev.
    assert isinstance(resolve_tree(str(tmp_path), repo="."), DirTree)


def test_find_packages_prefers_src_and_skips_conventional_dirs():
    assert find_packages(
        ["src/demo/__init__.py", "flat/__init__.py", "tests/__init__.py"]
    ) == [("src", "demo")]
    assert find_packages(
        ["demo/__init__.py", "tests/__init__.py", "docs/__init__.py"]
    ) == [(".", "demo")]


def test_locate_package_requires_disambiguation(tmp_path):
    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "__init__.py").write_text("", encoding="utf-8")
    tree = DirTree(str(tmp_path))
    with pytest.raises(SourceError, match="--package"):
        locate_package(tree, None)
    assert locate_package(tree, "beta") == (".", "beta")


def test_locate_package_errors_for_missing_or_absent_packages(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SourceError, match="no package"):
        locate_package(DirTree(str(empty)), None)
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "__init__.py").write_text("", encoding="utf-8")
    with pytest.raises(SourceError, match="'gamma' not found"):
        locate_package(DirTree(str(tmp_path)), "gamma")


def test_load_package_sources_maps_dotted_names(git_repo):
    commit_package(
        git_repo,
        {
            "src/demo/__init__.py": "",
            "src/demo/api.py": "def f(): pass",
            "src/demo/sub/__init__.py": "",
            "src/demo/sub/deep.py": "def g(): pass",
        },
        "v1",
    )
    tree = GitTree(str(git_repo), "HEAD")
    sources, init_modules = load_package_sources(tree, "src", "demo")
    assert set(sources) == {"demo", "demo.api", "demo.sub", "demo.sub.deep"}
    assert init_modules == {"demo", "demo.sub"}


def test_read_file_returns_content_or_none(git_repo):
    commit_package(git_repo, {"src/demo/__init__.py": ""}, "v1", version="1.0.0")
    tree = GitTree(str(git_repo), "HEAD")
    assert "1.0.0" in read_file(tree, "pyproject.toml")
    assert read_file(tree, "nonexistent.toml") is None
    dir_tree = DirTree(str(git_repo))
    assert "1.0.0" in read_file(dir_tree, "pyproject.toml")
    assert read_file(dir_tree, "nonexistent.toml") is None
