"""Module- and package-level diff rules: symbols, re-exports, __all__."""

import textwrap

from apidrift.diffing import diff_packages
from apidrift.extract import extract_package

from conftest import diff_src, kinds


def _pkg(sources: dict, name: str = "p", init_modules=None):
    return extract_package(
        {k: textwrap.dedent(v) for k, v in sources.items()},
        name,
        init_modules=init_modules,
    )


def test_removed_module_is_major_added_is_minor():
    old = _pkg({"p": "", "p.a": "", "p.b": ""})
    new = _pkg({"p": "", "p.a": "", "p.c": ""})
    changes = diff_packages(old, new)
    assert kinds(changes) == ["module-removed", "module-added"]
    assert changes[0].symbol == "p.b"
    assert changes[1].symbol == "p.c"


def test_removed_function_class_and_variable_are_all_major():
    changes = diff_src("def f(): pass\nclass C: pass\nX = 1", "")
    assert sorted(kinds(changes)) == [
        "class-removed",
        "function-removed",
        "variable-removed",
    ]
    assert all(change.severity == "major" for change in changes)


def test_making_a_symbol_private_reads_as_removal():
    # Renaming ``f`` to ``_f`` removes the public symbol; the private
    # replacement is not API, so no addition is reported.
    changes = diff_src("def f(): pass", "def _f(): pass")
    assert kinds(changes) == ["function-removed"]


def test_all_shrink_is_a_removal_growth_is_an_addition():
    v1 = "__all__ = ['a']\ndef a(): pass\ndef b(): pass"
    v2 = "__all__ = ['a', 'b']\ndef a(): pass\ndef b(): pass"
    grown = diff_src(v1, v2)
    shrunk = diff_src(v2, v1)
    assert kinds(grown) == ["function-added"]
    assert kinds(shrunk) == ["function-removed"]
    assert shrunk[0].symbol == "m.b"


def test_symbol_kind_change_is_major():
    changes = diff_src("def thing(): pass", "class thing: pass")
    assert kinds(changes) == ["symbol-kind-changed"]
    assert changes[0].severity == "major"


def test_reexport_removed_from_init_is_major():
    old = _pkg(
        {"p": "from .core import Client, Legacy", "p.core": ""},
        init_modules={"p"},
    )
    new = _pkg(
        {"p": "from .core import Client", "p.core": ""},
        init_modules={"p"},
    )
    changes = diff_packages(old, new)
    assert kinds(changes) == ["reexport-removed"]
    assert changes[0].symbol == "p.Legacy"
    assert changes[0].severity == "major"


def test_reexport_plumbing_changes_are_patch():
    # Re-pointing the import, or replacing it with a local definition, keeps
    # the name importable — plumbing, not breakage.
    repointed = diff_packages(
        _pkg({"p": "from .core import Client"}, init_modules={"p"}),
        _pkg({"p": "from .client import Client"}, init_modules={"p"}),
    )
    localized = diff_packages(
        _pkg({"p": "from .core import helper"}, init_modules={"p"}),
        _pkg({"p": "def helper(): pass"}, init_modules={"p"}),
    )
    assert kinds(repointed) == ["reexport-target-changed"]
    assert repointed[0].severity == "patch"
    assert kinds(localized) == ["reexport-target-changed"]
    assert localized[0].severity == "patch"


def test_variable_changes_are_patch_and_opaque_values_stay_silent():
    visible = diff_src("X: int = 1", "X: float = 2")
    assert sorted(kinds(visible)) == [
        "annotation-changed",
        "variable-value-changed",
    ]
    assert all(change.severity == "patch" for change in visible)
    # Both sides computed: apidrift cannot see a difference and says nothing.
    assert diff_src("X = compute()", "X = compute_differently()") == []


def test_identical_packages_diff_to_nothing_and_order_is_deterministic():
    sources = {
        "p": "from .core import Client",
        "p.core": "class Client:\n    def go(self): pass",
    }
    assert diff_packages(_pkg(sources), _pkg(sources)) == []
    old = _pkg({"p": "", "p.zeta": "def f(): pass", "p.alpha": "def g(): pass"})
    new = _pkg({"p": ""})
    changes = diff_packages(old, new)
    assert [change.symbol for change in changes] == ["p.alpha", "p.zeta"]
