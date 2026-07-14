"""Extraction at module and package level: __all__, re-exports, privacy."""

import pytest

from apidrift.extract import ExtractError, extract_package

from conftest import extract_src


def test_all_list_governs_publicity_exactly():
    mod = extract_src(
        """
        __all__ = ["shown", "_special"]

        def shown(): pass
        def _special(): pass
        def not_listed(): pass
        """
    )
    assert mod.has_all
    assert set(mod.functions) == {"shown", "_special"}


def test_all_supports_tuples_concatenation_and_augmented_assignment():
    concatenated = extract_src(
        """
        __all__ = ("a",) + ("b",)

        def a(): pass
        def b(): pass
        def c(): pass
        """
    )
    assert set(concatenated.functions) == {"a", "b"}
    extended = extract_src(
        """
        __all__ = ["a"]
        __all__ += ["b"]

        def a(): pass
        def b(): pass
        """
    )
    assert set(extended.functions) == {"a", "b"}


def test_unreadable_all_raises_a_clear_error():
    # Dynamic __all__ would make every diff silently wrong; refuse loudly.
    with pytest.raises(ExtractError, match="__all__"):
        extract_src("__all__ = [n for n in dir()]")
    with pytest.raises(ExtractError, match="list or tuple of strings"):
        extract_src("__all__ = [1, 2]")


def test_module_variables_annotations_and_tuple_unpacking():
    mod = extract_src("TIMEOUT: float\nLIMIT = 100\nA, B = make_pair()")
    assert mod.variables["TIMEOUT"].annotation == "float"
    assert mod.variables["TIMEOUT"].value is None
    assert mod.variables["LIMIT"].value == "100"
    # Tuple unpacking registers each name with an opaque value.
    assert {"A", "B"} <= set(mod.variables)
    assert mod.variables["A"].value is None


def test_imports_are_api_only_via_the_redundant_alias_convention():
    plain = extract_src("import os\nfrom json import dumps")
    assert plain.reexports == {}
    # PEP 484 / type-checker convention: ``from x import y as y`` re-exports.
    marked = extract_src("from .impl import Engine as Engine")
    assert marked.reexports == {"Engine": ".impl:Engine"}


def test_package_init_reexports_public_imports():
    mod = extract_src(
        "from .core import Client\nfrom ._internal import _secret",
        name="pkg",
        is_package_init=True,
    )
    assert mod.reexports == {"Client": ".core:Client"}
    # The same behavior via extract_package's init_modules argument.
    pkg = extract_package(
        {"p": "from .core import Client", "p.core": "class Client: pass"},
        "p",
        init_modules={"p"},
    )
    assert pkg.modules["p"].reexports == {"Client": ".core:Client"}


def test_init_with_all_only_reexports_listed_names():
    mod = extract_src(
        """
        __all__ = ["Client"]
        from .core import Client, Helper
        """,
        name="pkg",
        is_package_init=True,
    )
    assert mod.reexports == {"Client": ".core:Client"}


def test_syntax_error_reports_the_module_name():
    with pytest.raises(ExtractError, match="badmod"):
        extract_src("def broken(:", name="badmod")


def test_private_modules_are_dropped_but_an_underscore_root_survives():
    pkg = extract_package(
        {"p": "", "p._internal": "def f(): pass", "p.api": "def g(): pass"},
        "p",
    )
    assert set(pkg.modules) == {"p", "p.api"}
    # A top-level package named ``_native`` is still the package under test;
    # only components below the root are privacy-filtered.
    rooted = extract_package({"_native": "def f(): pass"}, "_native")
    assert "f" in rooted.modules["_native"].functions


