"""Signature diff rules: every parameter change maps to the right severity."""

from conftest import diff_src, kinds


def test_identical_signatures_produce_no_changes():
    src = "def f(a, b=1, *args, c, **kw): pass"
    assert diff_src(src, src) == []


def test_param_removal_and_addition_severities():
    removed = diff_src("def f(a, b): pass", "def f(a): pass")
    required = diff_src("def f(a): pass", "def f(a, b): pass")
    optional = diff_src("def f(a): pass", "def f(a, b=1): pass")
    required_kwonly = diff_src("def f(a): pass", "def f(a, *, b): pass")
    assert kinds(removed) == ["param-removed"]
    assert removed[0].severity == "major"
    assert removed[0].symbol == "m.f"
    assert kinds(required) == ["param-added-required"]
    assert required[0].severity == "major"
    assert kinds(optional) == ["param-added-optional"]
    assert optional[0].severity == "minor"
    # A required keyword-only addition breaks every existing call too.
    assert kinds(required_kwonly) == ["param-added-required"]
    assert required_kwonly[0].severity == "major"


def test_default_removal_addition_and_value_change_severities():
    removed = diff_src("def f(a=1): pass", "def f(a): pass")
    added = diff_src("def f(a): pass", "def f(a=1): pass")
    changed = diff_src("def f(a=1): pass", "def f(a=2): pass")
    assert kinds(removed) == ["param-default-removed"]
    assert removed[0].severity == "major"  # optional param became required
    assert kinds(added) == ["param-default-added"]
    assert added[0].severity == "minor"
    assert kinds(changed) == ["param-default-value-changed"]
    assert changed[0].severity == "patch"
    assert changed[0].old == "1" and changed[0].new == "2"


def test_renames_break_keyword_callers_but_not_positional_only_ones():
    keyword_capable = diff_src("def f(count): pass", "def f(limit): pass")
    positional_only = diff_src("def f(x, /): pass", "def f(y, /): pass")
    assert kinds(keyword_capable) == ["param-renamed"]
    assert keyword_capable[0].severity == "major"
    # ``def f(x, /)`` callers cannot use the name, so a rename is invisible.
    assert kinds(positional_only) == ["param-renamed-positional-only"]
    assert positional_only[0].severity == "patch"


def test_reordering_parameters_is_major():
    changes = diff_src("def f(a, b): pass", "def f(b, a): pass")
    assert kinds(changes) == ["param-reordered"]
    assert changes[0].severity == "major"


def test_moves_between_positional_and_keyword_only_groups():
    to_kwonly = diff_src("def f(a, b): pass", "def f(a, *, b): pass")
    relaxed = diff_src("def f(a, *, b): pass", "def f(a, b): pass")
    assert kinds(to_kwonly) == ["param-became-keyword-only"]
    assert to_kwonly[0].severity == "major"  # positional callers break
    assert kinds(relaxed) == ["param-became-flexible"]
    assert relaxed[0].severity == "minor"  # strictly more call spellings


def test_moves_between_positional_only_and_flexible_kinds():
    to_posonly = diff_src("def f(a): pass", "def f(a, /): pass")
    relaxed = diff_src("def f(a, /): pass", "def f(a): pass")
    assert kinds(to_posonly) == ["param-became-positional-only"]
    assert to_posonly[0].severity == "major"  # keyword callers break
    assert kinds(relaxed) == ["param-became-flexible"]
    assert relaxed[0].severity == "minor"


def test_star_args_and_kwargs_removal_is_major_addition_is_minor():
    assert kinds(diff_src("def f(*a): pass", "def f(): pass")) == [
        "var-positional-removed"
    ]
    assert kinds(diff_src("def f(): pass", "def f(*a): pass")) == [
        "var-positional-added"
    ]
    assert kinds(diff_src("def f(**k): pass", "def f(): pass")) == [
        "var-keyword-removed"
    ]
    assert kinds(diff_src("def f(): pass", "def f(**k): pass")) == [
        "var-keyword-added"
    ]


def test_sync_async_flips_are_major_in_both_directions():
    to_async = diff_src("def f(): pass", "async def f(): pass")
    to_sync = diff_src("async def f(): pass", "def f(): pass")
    assert kinds(to_async) == ["async-changed"]
    assert kinds(to_sync) == ["async-changed"]
    assert to_async[0].severity == "major"


def test_annotation_changes_are_patch_level():
    changes = diff_src(
        "def f(a: int) -> int: pass", "def f(a: str) -> bool: pass"
    )
    assert sorted(kinds(changes)) == [
        "annotation-changed",
        "return-annotation-changed",
    ]
    assert all(change.severity == "patch" for change in changes)


def test_self_rename_in_methods_is_ignored():
    changes = diff_src(
        """
        class C:
            def f(self, a): pass
        """,
        """
        class C:
            def f(this, a): pass
        """,
    )
    assert changes == []


def test_multiple_changes_are_all_reported_in_order():
    changes = diff_src(
        "def f(a, b=1): pass",
        "def f(a, b=2, c=None): pass",
    )
    assert kinds(changes) == [
        "param-default-value-changed",
        "param-added-optional",
    ]
