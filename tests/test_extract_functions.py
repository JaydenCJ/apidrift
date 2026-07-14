"""Extraction of module-level functions: signatures, defaults, decorators."""

from apidrift.model import (
    KEYWORD_ONLY,
    POSITIONAL_ONLY,
    POSITIONAL_OR_KEYWORD,
    VAR_KEYWORD,
    VAR_POSITIONAL,
)

from conftest import extract_src


def test_simple_function_parameters_in_order():
    mod = extract_src("def f(a, b, c): pass")
    assert [p.name for p in mod.functions["f"].params] == ["a", "b", "c"]
    assert all(
        p.kind == POSITIONAL_OR_KEYWORD for p in mod.functions["f"].params
    )


def test_defaults_align_to_the_tail_of_positional_params():
    # The classic ast pitfall: defaults belong to the LAST n positional
    # parameters, not the first n.
    mod = extract_src("def f(a, b=1, c='x'): pass")
    params = mod.functions["f"].params
    assert [p.has_default for p in params] == [False, True, True]
    assert params[1].default == "1"
    assert params[2].default == "'x'"
    # Complex default expressions survive as source text.
    rich = extract_src("def f(a=(1, 2), b=frozenset({'x'})): pass")
    assert rich.functions["f"].params[0].default == "(1, 2)"
    assert "frozenset" in rich.functions["f"].params[1].default


def test_all_five_parameter_kinds_are_distinguished():
    mod = extract_src("def f(a, /, b, *rest, c, **extra): pass")
    params = {p.name: p.kind for p in mod.functions["f"].params}
    assert params == {
        "a": POSITIONAL_ONLY,
        "b": POSITIONAL_OR_KEYWORD,
        "rest": VAR_POSITIONAL,
        "c": KEYWORD_ONLY,
        "extra": VAR_KEYWORD,
    }


def test_keyword_only_defaults_align_by_position():
    mod = extract_src("def f(*, a, b=2): pass")
    params = {p.name: p for p in mod.functions["f"].params}
    assert not params["a"].has_default
    assert params["b"].has_default and params["b"].default == "2"


def test_annotations_are_stored_as_source_text():
    mod = extract_src("def f(a: int, b: 'dict[str, int]' = {}) -> list: pass")
    func = mod.functions["f"]
    assert func.params[0].annotation == "int"
    assert func.params[1].annotation == "'dict[str, int]'"
    assert func.returns == "list"


def test_privacy_rule_and_the_include_private_escape_hatch():
    source = "def _hidden(): pass\ndef shown(): pass"
    assert set(extract_src(source).functions) == {"shown"}
    private = extract_src(source, include_private=True)
    assert set(private.functions) == {"_hidden", "shown"}


def test_nested_functions_are_not_api():
    mod = extract_src(
        """
        def outer():
            def inner():
                pass
        """
    )
    assert set(mod.functions) == {"outer"}


def test_overload_stubs_collapse_to_the_implementation():
    mod = extract_src(
        """
        from typing import overload

        @overload
        def f(x: int) -> int: ...
        @overload
        def f(x: str) -> str: ...
        def f(x, extra=None):
            return x
        """
    )
    func = mod.functions["f"]
    assert [p.name for p in func.params] == ["x", "extra"]
    assert func.returns is None  # the implementation's (absent) annotation

    # A .pyi-style module with no implementation keeps the first stub, so
    # the symbol exists and its removal is still detectable.
    stubs_only = extract_src(
        """
        from typing import overload

        @overload
        def f(x: int) -> int: ...
        @overload
        def f(x: str, y: str = "a") -> str: ...
        """
    )
    assert [p.name for p in stubs_only.functions["f"].params] == ["x"]


def test_async_flag_and_signature_rendering():
    mod = extract_src("async def f(a, /, b: int = 1, *args, c, **kw) -> bool: pass")
    func = mod.functions["f"]
    assert func.is_async
    assert func.signature() == "async def f(a, /, b: int=1, *args, c, **kw) -> bool"
