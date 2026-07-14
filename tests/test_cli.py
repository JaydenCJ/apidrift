"""End-to-end CLI behavior: subcommands, formats, exit codes."""

import json

import pytest

import apidrift
from apidrift.cli import main

from conftest import commit_package, git, git_repo  # noqa: F401  (fixture)

V1 = {
    "src/demo/__init__.py": "from .api import fetch\n",
    "src/demo/api.py": (
        "def fetch(url, timeout=30):\n    return url\n"
        "def ping(host):\n    return host\n"
    ),
}
# v2: `ping` removed (major), `retries` added optionally (minor).
V2 = {
    "src/demo/__init__.py": "from .api import fetch\n",
    "src/demo/api.py": (
        "def fetch(url, timeout=30, retries=0):\n    return url\n"
    ),
}


@pytest.fixture
def history(git_repo):
    """A repo with v1 tagged and v2 committed on top."""
    commit_package(git_repo, V1, "v1", version="1.0.0")
    git(git_repo, "tag", "v1.0.0")
    (git_repo / "src/demo/api.py").unlink()
    commit_package(git_repo, V2, "v2", version="1.1.0")
    return git_repo


def run(argv, capsys):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_diff_text_reports_changes_and_bump(history, capsys):
    code, out, _ = run(
        ["diff", "v1.0.0", "HEAD", "--repo", str(history)], capsys
    )
    assert code == 0
    assert "MAJOR  demo.api.ping: public function removed" in out
    assert "MINOR  demo.api.fetch: optional parameter retries added" in out
    assert "suggested bump: major (1.0.0 -> 2.0.0)" in out


def test_diff_defaults_to_the_worktree(history, capsys):
    # Uncommitted edit: remove another public function in the worktree.
    (history / "src/demo/api.py").write_text(
        "def fetch(url, timeout=30, retries=0):\n    return 1\n",
        encoding="utf-8",
    )
    code, out, _ = run(["diff", "HEAD", "--repo", str(history)], capsys)
    assert code == 0
    assert "worktree" in out
    assert "no public API changes" in out


def test_diff_json_and_markdown_formats(history, capsys):
    code, out, _ = run(
        ["diff", "v1.0.0", "HEAD", "--repo", str(history), "--format", "json"],
        capsys,
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["suggested_bump"] == "major"
    assert payload["counts"] == {"major": 1, "minor": 1, "patch": 0}
    kinds = {change["kind"] for change in payload["changes"]}
    assert kinds == {"function-removed", "param-added-optional"}

    code, out, _ = run(
        [
            "diff",
            "v1.0.0",
            "HEAD",
            "--repo",
            str(history),
            "--format",
            "markdown",
        ],
        capsys,
    )
    assert code == 0
    assert "| Severity | Symbol | Change |" in out
    assert "| MAJOR | `demo.api.ping` |" in out


def test_fail_on_gates_the_exit_code(history, capsys):
    code, _, _ = run(
        ["diff", "v1.0.0", "HEAD", "--repo", str(history), "--fail-on", "major"],
        capsys,
    )
    assert code == 1
    # A patch threshold also trips on a major change...
    code, _, _ = run(
        ["diff", "v1.0.0", "HEAD", "--repo", str(history), "--fail-on", "patch"],
        capsys,
    )
    assert code == 1
    # ...but never on a clean diff.
    code, _, _ = run(
        ["diff", "v1.0.0", "v1.0.0", "--repo", str(history), "--fail-on", "patch"],
        capsys,
    )
    assert code == 0


def test_bump_prints_a_single_word(history, capsys):
    code, out, _ = run(["bump", "v1.0.0", "HEAD", "--repo", str(history)], capsys)
    assert code == 0
    assert out.strip() == "major"


def test_check_fails_on_insufficient_declared_bump(history, capsys):
    # v1 -> v2 declares 1.0.0 -> 1.1.0 but the diff is breaking.
    code, out, err = run(["check", "v1.0.0", "HEAD", "--repo", str(history)], capsys)
    assert code == 1
    assert "required bump: major, declared bump: minor" in out
    assert "FAIL" in err


def test_check_passes_with_explicit_version_overrides(history, capsys):
    code, out, _ = run(
        [
            "check",
            "v1.0.0",
            "HEAD",
            "--repo",
            str(history),
            "--new-version",
            "2.0.0",
        ],
        capsys,
    )
    assert code == 0
    assert "OK: declared version covers the API changes" in out


def test_dump_then_diff_against_the_snapshot(history, tmp_path, capsys):
    snapshot = tmp_path / "api-v1.json"
    code, _, _ = run(
        [
            "dump",
            "v1.0.0",
            "--repo",
            str(history),
            "-o",
            str(snapshot),
        ],
        capsys,
    )
    assert code == 0
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    assert data["package"] == "demo"
    assert data["project_version"] == "1.0.0"

    code, out, _ = run(
        ["diff", str(snapshot), "HEAD", "--repo", str(history)], capsys
    )
    assert code == 0
    assert "MAJOR  demo.api.ping: public function removed" in out

    # Without -o the snapshot goes to stdout.
    code, out, _ = run(["dump", "HEAD", "--repo", str(history)], capsys)
    assert code == 0
    assert json.loads(out)["package"] == "demo"


def test_unknown_ref_is_a_clean_usage_error(history, capsys):
    code, _, err = run(["diff", "no-such-tag", "--repo", str(history)], capsys)
    assert code == 2
    assert "apidrift: error:" in err


def test_comparing_directories_needs_no_git(tmp_path, capsys):
    for version, files in (("old", V1), ("new", V2)):
        for rel, text in files.items():
            path = tmp_path / version / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    code, out, _ = run(
        ["diff", str(tmp_path / "old"), str(tmp_path / "new")], capsys
    )
    assert code == 0
    assert "MAJOR  demo.api.ping: public function removed" in out
    assert "suggested bump: major" in out


def test_version_flag_matches_the_package(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "apidrift " + apidrift.__version__


def test_mismatched_package_names_error_clearly(tmp_path, capsys):
    for name in ("alpha", "beta"):
        path = tmp_path / name / "src" / name / "__init__.py"
        path.parent.mkdir(parents=True)
        path.write_text("", encoding="utf-8")
    code, _, err = run(
        ["diff", str(tmp_path / "alpha"), str(tmp_path / "beta")], capsys
    )
    assert code == 2
    assert "different packages" in err
