"""Extract a package's public API surface from source text, via ``ast``.

This module never imports or executes the package under inspection: every
fact is read from the syntax tree. That makes extraction safe on untrusted
refs (no ``setup.py``/import side effects) and independent of the package's
own dependencies being installed.

Publicity rules (documented in ``docs/rules.md``):

- If a module defines a literal ``__all__``, exactly the listed names are
  public — nothing else, underscores included.
- Otherwise a defined name is public unless it starts with ``_``. Dunder
  *methods* (``__init__``, ``__call__``, ...) are public because they are the
  class's calling convention; dunder *attributes* are not.
- Names imported into a regular module are not part of that module's API,
  with one exception: the ``from x import y as y`` redundant-alias convention
  marks an explicit re-export. In an ``__init__.py`` every public imported
  name is treated as a re-export, because that is how Python packages
  conventionally assemble their top-level API.
- Modules whose own name starts with ``_`` are private wholesale.
"""

from __future__ import annotations

import ast
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple

from .model import (
    KEYWORD_ONLY,
    POSITIONAL_ONLY,
    POSITIONAL_OR_KEYWORD,
    ROLE_CLASSMETHOD,
    ROLE_FUNCTION,
    ROLE_METHOD,
    ROLE_PROPERTY,
    ROLE_STATICMETHOD,
    VAR_KEYWORD,
    VAR_POSITIONAL,
    Class,
    Function,
    Module,
    Package,
    Parameter,
    Variable,
)

_ENUM_BASES = {
    "Enum",
    "IntEnum",
    "StrEnum",
    "Flag",
    "IntFlag",
    "enum.Enum",
    "enum.IntEnum",
    "enum.StrEnum",
    "enum.Flag",
    "enum.IntFlag",
}


class ExtractError(ValueError):
    """Raised when a module cannot be parsed or ``__all__`` is malformed."""


def is_public_name(name: str) -> bool:
    """Default publicity rule for names without an ``__all__`` contract."""
    return not name.startswith("_")


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__") and len(name) > 4


def module_is_private(dotted: str) -> bool:
    """A module is private if any path component starts with ``_``."""
    return any(part.startswith("_") for part in dotted.split("."))


def _unparse(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    return ast.unparse(node)


def _decorator_name(node: ast.expr) -> str:
    """Flatten a decorator expression to a dotted-name string."""
    if isinstance(node, ast.Call):
        node = node.func
    return ast.unparse(node)


def _extract_params(args: ast.arguments) -> List[Parameter]:
    params: List[Parameter] = []

    def annotation(a: ast.arg) -> Optional[str]:
        return _unparse(a.annotation)

    # Defaults for positional params align to the *tail* of posonly + args.
    positional = list(args.posonlyargs) + list(args.args)
    defaults: List[Optional[ast.expr]] = [None] * (
        len(positional) - len(args.defaults)
    ) + list(args.defaults)
    for arg, default in zip(positional, defaults):
        kind = (
            POSITIONAL_ONLY if arg in args.posonlyargs else POSITIONAL_OR_KEYWORD
        )
        params.append(
            Parameter(
                name=arg.arg,
                kind=kind,
                has_default=default is not None,
                default=_unparse(default),
                annotation=annotation(arg),
            )
        )
    if args.vararg is not None:
        params.append(
            Parameter(
                name=args.vararg.arg,
                kind=VAR_POSITIONAL,
                annotation=annotation(args.vararg),
            )
        )
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        params.append(
            Parameter(
                name=arg.arg,
                kind=KEYWORD_ONLY,
                has_default=default is not None,
                default=_unparse(default),
                annotation=annotation(arg),
            )
        )
    if args.kwarg is not None:
        params.append(
            Parameter(
                name=args.kwarg.arg,
                kind=VAR_KEYWORD,
                annotation=annotation(args.kwarg),
            )
        )
    return params


def _extract_function(
    node: "ast.FunctionDef | ast.AsyncFunctionDef", in_class: bool
) -> Tuple[Function, bool, Optional[str]]:
    """Build a Function from a def node.

    Returns ``(function, is_overload, accessor)`` where ``accessor`` is
    ``"setter"``/``"deleter"`` for a ``@name.setter`` / ``@name.deleter``
    property accessor and ``None`` otherwise.
    """
    decorators = [_decorator_name(d) for d in node.decorator_list]
    role = ROLE_METHOD if in_class else ROLE_FUNCTION
    is_overload = False
    is_abstract = False
    accessor: Optional[str] = None
    for deco in decorators:
        base = deco.split(".")[-1]
        if base == "overload":
            is_overload = True
        elif base in ("property", "cached_property"):
            role = ROLE_PROPERTY
        elif base in ("setter", "deleter") and deco.count(".") == 1:
            # ``@name.setter`` / ``@name.deleter`` — still the property surface.
            role = ROLE_PROPERTY
            accessor = base
        elif base == "classmethod":
            role = ROLE_CLASSMETHOD
        elif base == "staticmethod":
            role = ROLE_STATICMETHOD
        elif base == "abstractproperty":
            role = ROLE_PROPERTY
            is_abstract = True
        elif base == "abstractmethod":
            is_abstract = True

    func = Function(
        name=node.name,
        params=_extract_params(node.args),
        returns=_unparse(node.returns),
        is_async=isinstance(node, ast.AsyncFunctionDef),
        role=role,
        is_abstract=is_abstract,
        has_setter=accessor == "setter",
        lineno=node.lineno,
    )
    return func, is_overload, accessor


def _literal_value(node: ast.expr) -> Optional[str]:
    """Source text for a value we consider stable enough to diff.

    Only literal constants and containers of literals count; anything with
    behavior (calls, names, comprehensions) is opaque and returns ``None``,
    so a change from one opaque value to another never produces noise.
    """
    try:
        ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return None
    return ast.unparse(node)


class _AllTypeError(Exception):
    """Internal: ``__all__`` resolved statically but is not all strings."""


def _eval_all_expr(node: ast.expr) -> List[str]:
    """Evaluate an ``__all__`` value: literal lists/tuples, ``+``-joined."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _eval_all_expr(node.left) + _eval_all_expr(node.right)
    value = ast.literal_eval(node)  # ValueError and friends for dynamic code
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise _AllTypeError
    return list(value)


def _extract_all(module_body: Iterable[ast.stmt], module_name: str) -> Optional[List[str]]:
    """Return the literal ``__all__`` list if one can be resolved statically.

    Supports ``__all__ = [...]``, tuples, ``+`` concatenation of literals,
    and ``__all__ += [...]``. A dynamic ``__all__`` raises ExtractError so
    the user learns the contract could not be read rather than getting a
    silently wrong diff.
    """
    names: Optional[List[str]] = None
    for stmt in module_body:
        target = None
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
        elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.op, ast.Add):
            target = stmt.target
        if not (isinstance(target, ast.Name) and target.id == "__all__"):
            continue
        try:
            value = _eval_all_expr(stmt.value)
        except _AllTypeError:
            raise ExtractError(
                "{}: __all__ must be a list or tuple of strings".format(module_name)
            ) from None
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            raise ExtractError(
                "{}: __all__ is not a static literal; apidrift cannot "
                "determine the public API contract".format(module_name)
            ) from None
        if isinstance(stmt, ast.AugAssign):
            names = (names or []) + value
        else:
            names = value
    return names


def _extract_class(node: ast.ClassDef, include_private: bool) -> Class:
    bases = [ast.unparse(b) for b in node.bases]
    decorators = [_decorator_name(d) for d in node.decorator_list]
    cls = Class(
        name=node.name,
        bases=bases,
        is_enum=any(b in _ENUM_BASES for b in bases),
        is_dataclass=any(d.split(".")[-1] == "dataclass" for d in decorators),
        lineno=node.lineno,
    )
    for stmt in node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = stmt.name
            public = is_public_name(name) or _is_dunder(name)
            if not public and not include_private:
                continue
            func, is_overload, accessor = _extract_function(stmt, in_class=True)
            # @overload stubs are typing artifacts; the implementation (or
            # the last stub, in a pure stub class) defines the signature.
            if is_overload and name in cls.methods:
                continue
            if accessor is not None:
                # ``@name.setter`` / ``@name.deleter``: the getter stays the
                # canonical record; only note that the property is writable.
                existing = cls.methods.get(name)
                if existing is not None and existing.role == ROLE_PROPERTY:
                    if accessor == "setter":
                        existing.has_setter = True
                    continue
            cls.methods[name] = func
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            for name, var in _extract_assignment(stmt):
                if _is_dunder(name):
                    continue  # __slots__, __module__, ... are not API
                if not is_public_name(name) and not include_private:
                    continue
                cls.attributes[name] = var
        elif isinstance(stmt, ast.ClassDef):
            # Nested classes are rare API; represent them as an opaque
            # attribute so removal is still caught.
            name = stmt.name
            if is_public_name(name) or include_private:
                cls.attributes[name] = Variable(
                    name=name, annotation="type", value=None, lineno=stmt.lineno
                )
    return cls


def _extract_assignment(
    stmt: "ast.Assign | ast.AnnAssign",
) -> List[Tuple[str, Variable]]:
    out: List[Tuple[str, Variable]] = []
    if isinstance(stmt, ast.AnnAssign):
        if isinstance(stmt.target, ast.Name):
            value = _literal_value(stmt.value) if stmt.value is not None else None
            out.append(
                (
                    stmt.target.id,
                    Variable(
                        name=stmt.target.id,
                        annotation=_unparse(stmt.annotation),
                        value=value,
                        lineno=stmt.lineno,
                    ),
                )
            )
    else:
        value = _literal_value(stmt.value)
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                out.append(
                    (
                        target.id,
                        Variable(
                            name=target.id,
                            annotation=None,
                            value=value,
                            lineno=stmt.lineno,
                        ),
                    )
                )
            elif isinstance(target, ast.Tuple):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        out.append(
                            (
                                elt.id,
                                Variable(
                                    name=elt.id,
                                    annotation=None,
                                    value=None,  # tuple unpack: opaque
                                    lineno=stmt.lineno,
                                ),
                            )
                        )
    return out


def _import_reexports(stmt: ast.stmt, module_name: str) -> Dict[str, str]:
    """Map local name -> source for import statements."""
    out: Dict[str, str] = {}
    if isinstance(stmt, ast.ImportFrom):
        source = "." * stmt.level + (stmt.module or "")
        for alias in stmt.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            out[local] = "{}:{}".format(source, alias.name)
    elif isinstance(stmt, ast.Import):
        for alias in stmt.names:
            local = alias.asname or alias.name.split(".")[0]
            out[local] = "{}:{}".format(alias.name, alias.name)
    return out


def extract_module(
    source: str,
    module_name: str,
    include_private: bool = False,
    is_package_init: bool = False,
) -> Module:
    """Parse one module's source text into a :class:`Module` API record."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ExtractError(
            "{}: cannot parse: {}".format(module_name, exc)
        ) from None

    all_names = _extract_all(tree.body, module_name)
    module = Module(name=module_name, has_all=all_names is not None)

    def is_public(name: str) -> bool:
        if include_private:
            return True
        if all_names is not None:
            return name in all_names
        return is_public_name(name)

    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not is_public(stmt.name):
                continue
            func, is_overload, _ = _extract_function(stmt, in_class=False)
            if is_overload and stmt.name in module.functions:
                continue
            module.functions[stmt.name] = func
        elif isinstance(stmt, ast.ClassDef):
            if not is_public(stmt.name):
                continue
            module.classes[stmt.name] = _extract_class(stmt, include_private)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            for name, var in _extract_assignment(stmt):
                if name == "__all__" or _is_dunder(name):
                    continue
                if not is_public(name):
                    continue
                module.variables[name] = var
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for local, source_ref in _import_reexports(stmt, module_name).items():
                explicit = source_ref.endswith(":" + local) and _is_redundant_alias(
                    stmt, local
                )
                if all_names is not None:
                    exported = local in all_names
                elif is_package_init:
                    exported = is_public_name(local) or include_private
                else:
                    exported = explicit
                if exported:
                    module.reexports[local] = source_ref
    return module


def _is_redundant_alias(stmt: ast.stmt, local: str) -> bool:
    """True for the ``from x import y as y`` explicit re-export convention."""
    if not isinstance(stmt, ast.ImportFrom):
        return False
    for alias in stmt.names:
        if (alias.asname or alias.name) == local:
            return alias.asname is not None and alias.asname == alias.name
    return False


def extract_package(
    sources: Mapping[str, str],
    package_name: str,
    include_private: bool = False,
    init_modules: Optional[Set[str]] = None,
) -> Package:
    """Extract every public module of a package.

    ``sources`` maps dotted module names (``pkg``, ``pkg.sub.mod``) to source
    text, as produced by :func:`apidrift.gitsource.load_package_sources`.
    ``init_modules`` names the modules that came from an ``__init__.py``; if
    omitted, a module counts as an init when it is the package root or has
    child modules in ``sources``.
    """
    package = Package(name=package_name)
    for dotted in sorted(sources):
        if not include_private and module_is_private_below_root(dotted, package_name):
            continue
        if init_modules is not None:
            is_init = dotted in init_modules
        else:
            is_init = dotted == package_name or _has_child_modules(dotted, sources)
        package.modules[dotted] = extract_module(
            sources[dotted],
            dotted,
            include_private=include_private,
            is_package_init=is_init,
        )
    return package


def _has_child_modules(dotted: str, sources: Mapping[str, str]) -> bool:
    prefix = dotted + "."
    return any(other.startswith(prefix) for other in sources)


def module_is_private_below_root(dotted: str, package_name: str) -> bool:
    """Privacy check that tolerates an underscore in the package's own name.

    A distribution may legitimately ship a top-level ``_yaml``-style package;
    only components *below* the root make a module private.
    """
    if dotted == package_name:
        return False
    if dotted.startswith(package_name + "."):
        rest = dotted[len(package_name) + 1 :]
        return any(part.startswith("_") for part in rest.split("."))
    return module_is_private(dotted)
