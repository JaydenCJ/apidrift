"""apidrift — diff a Python package's public API between git refs.

AST-based and zero-dependency: the package under inspection is parsed, never
imported or executed, so apidrift is safe to point at any ref of any
repository. The library surface below is what the CLI is built on:

- :func:`extract_package` / :func:`extract_module` — source text -> API model
- :func:`diff_packages` — two API models -> a list of :class:`Change`
- :func:`required_bump_for` / :func:`next_version` — changes -> semver advice
"""

from .diffing import diff_packages
from .extract import ExtractError, extract_module, extract_package
from .gitsource import SourceError
from .model import Class, Function, Module, Package, Parameter, Variable
from .rules import Change, KIND_SEVERITY, max_severity
from .semver import (
    VersionError,
    actual_bump,
    is_sufficient,
    next_version,
    parse_version,
    required_bump,
    required_bump_for,
)

__version__ = "0.1.0"

__all__ = [
    "Change",
    "Class",
    "ExtractError",
    "Function",
    "KIND_SEVERITY",
    "Module",
    "Package",
    "Parameter",
    "SourceError",
    "Variable",
    "VersionError",
    "__version__",
    "actual_bump",
    "diff_packages",
    "extract_module",
    "extract_package",
    "is_sufficient",
    "max_severity",
    "next_version",
    "parse_version",
    "required_bump",
    "required_bump_for",
]
