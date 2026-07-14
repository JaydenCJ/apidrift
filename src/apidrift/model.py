"""Data model for a Python package's public API surface.

Everything apidrift knows about an API is captured in the small, plain
dataclasses in this module. They are produced by :mod:`apidrift.extract`
(from source text, via ``ast``), consumed by :mod:`apidrift.diffing`, and
round-trip losslessly through JSON so that ``apidrift dump`` snapshots can be
stored and diffed later.

No object in this module ever holds a live Python object — defaults,
annotations, and values are stored as *source text* (``ast.unparse`` output),
which is what makes apidrift safe to run against untrusted refs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

#: Version of the JSON snapshot schema written by ``apidrift dump``.
FORMAT_VERSION = 1

# Parameter kinds, mirroring inspect.Parameter but as plain strings.
POSITIONAL_ONLY = "positional-only"
POSITIONAL_OR_KEYWORD = "positional-or-keyword"
VAR_POSITIONAL = "var-positional"
KEYWORD_ONLY = "keyword-only"
VAR_KEYWORD = "var-keyword"

# Function roles derived from decorators.
ROLE_METHOD = "method"
ROLE_PROPERTY = "property"
ROLE_CLASSMETHOD = "classmethod"
ROLE_STATICMETHOD = "staticmethod"
ROLE_FUNCTION = "function"


@dataclass
class Parameter:
    """One parameter of a function signature."""

    name: str
    kind: str = POSITIONAL_OR_KEYWORD
    has_default: bool = False
    default: Optional[str] = None  # source text, e.g. "10" or "()"
    annotation: Optional[str] = None  # source text, e.g. "int | None"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "has_default": self.has_default,
            "default": self.default,
            "annotation": self.annotation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Parameter":
        return cls(
            name=data["name"],
            kind=data["kind"],
            has_default=data.get("has_default", False),
            default=data.get("default"),
            annotation=data.get("annotation"),
        )


@dataclass
class Function:
    """A module-level function or a class method (role tells which flavor)."""

    name: str
    params: List[Parameter] = field(default_factory=list)
    returns: Optional[str] = None  # return annotation source text
    is_async: bool = False
    role: str = ROLE_FUNCTION
    is_abstract: bool = False
    has_setter: bool = False  # properties only: a ``@name.setter`` exists
    lineno: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "params": [p.to_dict() for p in self.params],
            "returns": self.returns,
            "is_async": self.is_async,
            "role": self.role,
            "is_abstract": self.is_abstract,
            "has_setter": self.has_setter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Function":
        return cls(
            name=data["name"],
            params=[Parameter.from_dict(p) for p in data.get("params", [])],
            returns=data.get("returns"),
            is_async=data.get("is_async", False),
            role=data.get("role", ROLE_FUNCTION),
            is_abstract=data.get("is_abstract", False),
            has_setter=data.get("has_setter", False),
        )

    def signature(self) -> str:
        """Human-readable signature, used in diff messages."""
        parts: List[str] = []
        seen_posonly = False
        seen_star = False
        for p in self.params:
            if p.kind == POSITIONAL_ONLY:
                seen_posonly = True
            elif seen_posonly:
                parts.append("/")
                seen_posonly = False
            if p.kind == KEYWORD_ONLY and not seen_star:
                parts.append("*")
                seen_star = True
            if p.kind == VAR_POSITIONAL:
                seen_star = True
                parts.append("*" + p.name)
            elif p.kind == VAR_KEYWORD:
                parts.append("**" + p.name)
            else:
                text = p.name
                if p.annotation:
                    text += ": " + p.annotation
                if p.has_default:
                    text += "=" + (p.default if p.default is not None else "...")
                parts.append(text)
        if seen_posonly:
            parts.append("/")
        prefix = "async def " if self.is_async else "def "
        suffix = " -> " + self.returns if self.returns else ""
        return "{}{}({}){}".format(prefix, self.name, ", ".join(parts), suffix)


@dataclass
class Variable:
    """A module-level or class-level assignment that is part of the API."""

    name: str
    annotation: Optional[str] = None
    value: Optional[str] = None  # source text for literal values, else None
    lineno: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "annotation": self.annotation,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Variable":
        return cls(
            name=data["name"],
            annotation=data.get("annotation"),
            value=data.get("value"),
        )


@dataclass
class Class:
    """A class definition: bases, methods, and class-level attributes."""

    name: str
    bases: List[str] = field(default_factory=list)
    methods: Dict[str, Function] = field(default_factory=dict)
    attributes: Dict[str, Variable] = field(default_factory=dict)
    is_enum: bool = False
    is_dataclass: bool = False
    lineno: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "bases": list(self.bases),
            "methods": {k: v.to_dict() for k, v in sorted(self.methods.items())},
            "attributes": {
                k: v.to_dict() for k, v in sorted(self.attributes.items())
            },
            "is_enum": self.is_enum,
            "is_dataclass": self.is_dataclass,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Class":
        return cls(
            name=data["name"],
            bases=list(data.get("bases", [])),
            methods={
                k: Function.from_dict(v)
                for k, v in data.get("methods", {}).items()
            },
            attributes={
                k: Variable.from_dict(v)
                for k, v in data.get("attributes", {}).items()
            },
            is_enum=data.get("is_enum", False),
            is_dataclass=data.get("is_dataclass", False),
        )


@dataclass
class Module:
    """One module of the package, keyed by its dotted name."""

    name: str
    functions: Dict[str, Function] = field(default_factory=dict)
    classes: Dict[str, Class] = field(default_factory=dict)
    variables: Dict[str, Variable] = field(default_factory=dict)
    #: Re-exported names: local name -> "source_module.original_name".
    reexports: Dict[str, str] = field(default_factory=dict)
    #: True when the module defines a literal ``__all__``.
    has_all: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "functions": {
                k: v.to_dict() for k, v in sorted(self.functions.items())
            },
            "classes": {k: v.to_dict() for k, v in sorted(self.classes.items())},
            "variables": {
                k: v.to_dict() for k, v in sorted(self.variables.items())
            },
            "reexports": dict(sorted(self.reexports.items())),
            "has_all": self.has_all,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Module":
        return cls(
            name=data["name"],
            functions={
                k: Function.from_dict(v)
                for k, v in data.get("functions", {}).items()
            },
            classes={
                k: Class.from_dict(v) for k, v in data.get("classes", {}).items()
            },
            variables={
                k: Variable.from_dict(v)
                for k, v in data.get("variables", {}).items()
            },
            reexports=dict(data.get("reexports", {})),
            has_all=data.get("has_all", False),
        )


@dataclass
class Package:
    """The whole extracted API surface of one package at one ref."""

    name: str
    modules: Dict[str, Module] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "format_version": FORMAT_VERSION,
            "package": self.name,
            "modules": {k: v.to_dict() for k, v in sorted(self.modules.items())},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Package":
        version = data.get("format_version")
        if version != FORMAT_VERSION:
            raise ValueError(
                "unsupported snapshot format_version: {!r} "
                "(this apidrift reads version {})".format(version, FORMAT_VERSION)
            )
        return cls(
            name=data["package"],
            modules={
                k: Module.from_dict(v) for k, v in data.get("modules", {}).items()
            },
        )
