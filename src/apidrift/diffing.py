"""Compare two extracted API surfaces and emit :class:`~apidrift.rules.Change`s.

The comparison is purely structural — two :class:`~apidrift.model.Package`
values in, a flat list of changes out — so it works identically whether the
sides came from git refs, directories, or ``apidrift dump`` snapshots.

Changes are emitted in a deterministic order: modules sorted by name, then
symbols sorted by name, then signature details in parameter order. Output
stability matters because diffs get pasted into changelogs and CI logs.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .model import (
    KEYWORD_ONLY,
    POSITIONAL_ONLY,
    POSITIONAL_OR_KEYWORD,
    ROLE_PROPERTY,
    VAR_KEYWORD,
    VAR_POSITIONAL,
    Class,
    Function,
    Module,
    Package,
    Parameter,
    Variable,
)
from .rules import Change

_POSITIONAL_KINDS = (POSITIONAL_ONLY, POSITIONAL_OR_KEYWORD)


def diff_packages(old: Package, new: Package) -> List[Change]:
    """All API changes going from ``old`` to ``new``."""
    changes: List[Change] = []
    old_mods, new_mods = old.modules, new.modules
    for name in sorted(set(old_mods) | set(new_mods)):
        if name not in new_mods:
            changes.append(
                Change("module-removed", name, "public module removed")
            )
        elif name not in old_mods:
            changes.append(Change("module-added", name, "public module added"))
        else:
            changes.extend(_diff_module(old_mods[name], new_mods[name]))
    return changes


def _diff_module(old: Module, new: Module) -> List[Change]:
    changes: List[Change] = []
    prefix = old.name + "."

    # A name can move between categories (e.g. a re-exported class becomes a
    # locally defined one). Build a unified view first so a category move is
    # not misreported as removed + added.
    def categories(mod: Module) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name in mod.functions:
            out[name] = "function"
        for name in mod.classes:
            out[name] = "class"
        for name in mod.variables:
            out[name] = "variable"
        for name in mod.reexports:
            out.setdefault(name, "reexport")
        return out

    old_cat, new_cat = categories(old), categories(new)
    for name in sorted(set(old_cat) | set(new_cat)):
        symbol = prefix + name
        if name not in new_cat:
            kind = {
                "function": "function-removed",
                "class": "class-removed",
                "variable": "variable-removed",
                "reexport": "reexport-removed",
            }[old_cat[name]]
            changes.append(
                Change(kind, symbol, "public {} removed".format(old_cat[name]))
            )
            continue
        if name not in old_cat:
            kind = {
                "function": "function-added",
                "class": "class-added",
                "variable": "variable-added",
                "reexport": "reexport-added",
            }[new_cat[name]]
            changes.append(
                Change(kind, symbol, "public {} added".format(new_cat[name]))
            )
            continue
        if old_cat[name] != new_cat[name]:
            # Re-export replaced by a local definition (or vice versa) keeps
            # the name importable; treat as plumbing, not a break.
            if "reexport" in (old_cat[name], new_cat[name]):
                changes.append(
                    Change(
                        "reexport-target-changed",
                        symbol,
                        "now provided as a {} (was a {})".format(
                            new_cat[name], old_cat[name]
                        ),
                        old=old_cat[name],
                        new=new_cat[name],
                    )
                )
            else:
                changes.append(
                    Change(
                        "symbol-kind-changed",
                        symbol,
                        "was a {}, is now a {}".format(
                            old_cat[name], new_cat[name]
                        ),
                        old=old_cat[name],
                        new=new_cat[name],
                    )
                )
            continue
        category = old_cat[name]
        if category == "function":
            changes.extend(
                _diff_function(old.functions[name], new.functions[name], symbol)
            )
        elif category == "class":
            changes.extend(
                _diff_class(old.classes[name], new.classes[name], symbol)
            )
        elif category == "variable":
            changes.extend(
                _diff_variable(old.variables[name], new.variables[name], symbol)
            )
        elif category == "reexport":
            if old.reexports[name] != new.reexports[name]:
                changes.append(
                    Change(
                        "reexport-target-changed",
                        symbol,
                        "re-export now points at {} (was {})".format(
                            new.reexports[name], old.reexports[name]
                        ),
                        old=old.reexports[name],
                        new=new.reexports[name],
                    )
                )
    return changes


def _diff_variable(old: Variable, new: Variable, symbol: str) -> List[Change]:
    changes: List[Change] = []
    if old.annotation != new.annotation:
        changes.append(
            Change(
                "annotation-changed",
                symbol,
                "annotation changed from {} to {}".format(
                    old.annotation or "<none>", new.annotation or "<none>"
                ),
                old=old.annotation,
                new=new.annotation,
            )
        )
    # Only compare when both sides are known literals: opaque -> opaque is
    # not evidence of change, and literal -> opaque usually means the value
    # became computed, which is invisible to callers.
    if old.value is not None and new.value is not None and old.value != new.value:
        changes.append(
            Change(
                "variable-value-changed",
                symbol,
                "value changed from {} to {}".format(old.value, new.value),
                old=old.value,
                new=new.value,
            )
        )
    return changes


def _diff_class(old: Class, new: Class, symbol: str) -> List[Change]:
    changes: List[Change] = []
    for base in old.bases:
        if base not in new.bases:
            changes.append(
                Change(
                    "base-removed",
                    symbol,
                    "no longer inherits from {}".format(base),
                    old=base,
                )
            )
    for base in new.bases:
        if base not in old.bases:
            changes.append(
                Change(
                    "base-added",
                    symbol,
                    "now inherits from {}".format(base),
                    new=base,
                )
            )

    for name in sorted(set(old.methods) | set(new.methods)):
        method_symbol = symbol + "." + name
        if name not in new.methods:
            changes.append(
                Change("method-removed", method_symbol, "public method removed")
            )
        elif name not in old.methods:
            changes.append(
                Change("method-added", method_symbol, "public method added")
            )
        else:
            changes.extend(
                _diff_function(old.methods[name], new.methods[name], method_symbol)
            )

    member_noun = "enum member" if old.is_enum and new.is_enum else "attribute"
    for name in sorted(set(old.attributes) | set(new.attributes)):
        attr_symbol = symbol + "." + name
        if name not in new.attributes:
            kind = (
                "enum-member-removed" if member_noun == "enum member" else "attribute-removed"
            )
            changes.append(
                Change(kind, attr_symbol, "public {} removed".format(member_noun))
            )
        elif name not in old.attributes:
            kind = (
                "enum-member-added" if member_noun == "enum member" else "attribute-added"
            )
            changes.append(
                Change(kind, attr_symbol, "public {} added".format(member_noun))
            )
        else:
            changes.extend(
                _diff_variable(old.attributes[name], new.attributes[name], attr_symbol)
            )
    return changes


def _diff_function(old: Function, new: Function, symbol: str) -> List[Change]:
    changes: List[Change] = []
    if old.role != new.role:
        changes.append(
            Change(
                "role-changed",
                symbol,
                "was a {}, is now a {}".format(old.role, new.role),
                old=old.role,
                new=new.role,
            )
        )
        # Signatures of different roles are not comparable (property has no
        # call signature for the caller); stop here.
        return changes
    if old.is_async != new.is_async:
        changes.append(
            Change(
                "async-changed",
                symbol,
                "became async" if new.is_async else "is no longer async",
                old="async" if old.is_async else "sync",
                new="async" if new.is_async else "sync",
            )
        )
    if old.is_abstract != new.is_abstract:
        if new.is_abstract:
            changes.append(
                Change(
                    "method-became-abstract",
                    symbol,
                    "became abstract; existing subclasses no longer instantiate",
                )
            )
        else:
            changes.append(
                Change(
                    "method-became-concrete",
                    symbol,
                    "is no longer abstract",
                )
            )
    if old.returns != new.returns:
        changes.append(
            Change(
                "return-annotation-changed",
                symbol,
                "return annotation changed from {} to {}".format(
                    old.returns or "<none>", new.returns or "<none>"
                ),
                old=old.returns,
                new=new.returns,
            )
        )
    if old.role == ROLE_PROPERTY:
        # A property has no caller-facing call signature; the accessor defs'
        # parameters are an implementation detail. Only setter presence is
        # part of the contract (``obj.x = value`` works or it does not).
        if old.has_setter and not new.has_setter:
            changes.append(
                Change(
                    "property-setter-removed",
                    symbol,
                    "property setter removed; assignments to it break",
                )
            )
        elif not old.has_setter and new.has_setter:
            changes.append(
                Change(
                    "property-setter-added",
                    symbol,
                    "property gained a setter and is now assignable",
                )
            )
        return changes
    changes.extend(_diff_params(old, new, symbol))
    return changes


def _split_params(func: Function):
    positional = [p for p in func.params if p.kind in _POSITIONAL_KINDS]
    keyword_only = {p.name: p for p in func.params if p.kind == KEYWORD_ONLY}
    vararg = next((p for p in func.params if p.kind == VAR_POSITIONAL), None)
    kwarg = next((p for p in func.params if p.kind == VAR_KEYWORD), None)
    return positional, keyword_only, vararg, kwarg


def _skip_self(func: Function, positional: List[Parameter]) -> List[Parameter]:
    """Drop the implicit receiver so renaming ``self``/``cls`` is never reported."""
    if func.role in ("method", "classmethod") and positional:
        return positional[1:]
    return positional


def _diff_params(old: Function, new: Function, symbol: str) -> List[Change]:
    changes: List[Change] = []
    old_pos, old_kw, old_vararg, old_kwarg = _split_params(old)
    new_pos, new_kw, new_vararg, new_kwarg = _split_params(new)
    old_pos = _skip_self(old, old_pos)
    new_pos = _skip_self(new, new_pos)

    if old_vararg is not None and new_vararg is None:
        changes.append(
            Change(
                "var-positional-removed",
                symbol,
                "*{} removed".format(old_vararg.name),
                old="*" + old_vararg.name,
            )
        )
    elif old_vararg is None and new_vararg is not None:
        changes.append(
            Change(
                "var-positional-added",
                symbol,
                "*{} added".format(new_vararg.name),
                new="*" + new_vararg.name,
            )
        )
    if old_kwarg is not None and new_kwarg is None:
        changes.append(
            Change(
                "var-keyword-removed",
                symbol,
                "**{} removed".format(old_kwarg.name),
                old="**" + old_kwarg.name,
            )
        )
    elif old_kwarg is None and new_kwarg is not None:
        changes.append(
            Change(
                "var-keyword-added",
                symbol,
                "**{} added".format(new_kwarg.name),
                new="**" + new_kwarg.name,
            )
        )

    old_pos_names = [p.name for p in old_pos]
    new_pos_names = [p.name for p in new_pos]

    # Pairwise walk over shared positions.
    for index in range(min(len(old_pos), len(new_pos))):
        a, b = old_pos[index], new_pos[index]
        if a.name == b.name:
            changes.extend(_diff_same_param(a, b, symbol))
            continue
        moved_away = a.name in new_kw or a.name in new_pos_names[index + 1 :]
        moved_in = b.name in old_kw or b.name in old_pos_names[index + 1 :]
        if moved_away or moved_in:
            changes.append(
                Change(
                    "param-reordered",
                    symbol,
                    "positional parameters reordered at position {} "
                    "({} -> {})".format(index, a.name, b.name),
                    old=a.name,
                    new=b.name,
                )
            )
            # Positions after a reorder are unreliable; stop the pairwise walk.
            return changes
        if a.kind == POSITIONAL_ONLY and b.kind == POSITIONAL_ONLY:
            # Positional-only parameters cannot be passed by name, so a
            # rename is invisible to every legal caller.
            changes.append(
                Change(
                    "param-renamed-positional-only",
                    symbol,
                    "positional-only parameter {} renamed to {}".format(
                        a.name, b.name
                    ),
                    old=a.name,
                    new=b.name,
                )
            )
        else:
            changes.append(
                Change(
                    "param-renamed",
                    symbol,
                    "parameter {} renamed to {}; keyword callers break".format(
                        a.name, b.name
                    ),
                    old=a.name,
                    new=b.name,
                )
            )
        changes.extend(_diff_same_param(a, b, symbol, renamed_to=b.name))

    # Old positional params past the shared prefix.
    for a in old_pos[len(new_pos) :]:
        if a.name in new_kw:
            changes.append(
                Change(
                    "param-became-keyword-only",
                    symbol,
                    "parameter {} became keyword-only; positional callers "
                    "break".format(a.name),
                    old=a.name,
                    new=a.name,
                )
            )
            changes.extend(_diff_same_param(a, new_kw[a.name], symbol))
        else:
            changes.append(
                Change(
                    "param-removed",
                    symbol,
                    "parameter {} removed".format(a.name),
                    old=a.name,
                )
            )
    # New positional params past the shared prefix.
    for b in new_pos[len(old_pos) :]:
        if b.name in old_kw:
            changes.append(
                Change(
                    "param-became-flexible",
                    symbol,
                    "keyword-only parameter {} may now also be passed "
                    "positionally".format(b.name),
                    old=b.name,
                    new=b.name,
                )
            )
            changes.extend(_diff_same_param(old_kw[b.name], b, symbol))
        elif b.has_default:
            changes.append(
                Change(
                    "param-added-optional",
                    symbol,
                    "optional parameter {} added (default {})".format(
                        b.name, b.default
                    ),
                    new=b.name,
                )
            )
        else:
            changes.append(
                Change(
                    "param-added-required",
                    symbol,
                    "required parameter {} added; every existing call "
                    "breaks".format(b.name),
                    new=b.name,
                )
            )

    handled_old = set(old_pos_names)
    handled_new = set(new_pos_names)
    for name in sorted(set(old_kw) | set(new_kw)):
        if name in handled_old or name in handled_new:
            continue  # cross-group moves were handled above
        if name not in new_kw:
            changes.append(
                Change(
                    "param-removed",
                    symbol,
                    "keyword-only parameter {} removed".format(name),
                    old=name,
                )
            )
        elif name not in old_kw:
            if new_kw[name].has_default:
                changes.append(
                    Change(
                        "param-added-optional",
                        symbol,
                        "optional keyword-only parameter {} added "
                        "(default {})".format(name, new_kw[name].default),
                        new=name,
                    )
                )
            else:
                changes.append(
                    Change(
                        "param-added-required",
                        symbol,
                        "required keyword-only parameter {} added; every "
                        "existing call breaks".format(name),
                        new=name,
                    )
                )
        else:
            changes.extend(_diff_same_param(old_kw[name], new_kw[name], symbol))
    return changes


def _diff_same_param(
    a: Parameter, b: Parameter, symbol: str, renamed_to: Optional[str] = None
) -> List[Change]:
    """Detail diff for a parameter matched across the two signatures."""
    changes: List[Change] = []
    label = renamed_to or b.name
    if a.kind != b.kind and {a.kind, b.kind} <= set(_POSITIONAL_KINDS):
        if b.kind == POSITIONAL_ONLY:
            changes.append(
                Change(
                    "param-became-positional-only",
                    symbol,
                    "parameter {} became positional-only; keyword callers "
                    "break".format(label),
                    old=a.kind,
                    new=b.kind,
                )
            )
        else:
            changes.append(
                Change(
                    "param-became-flexible",
                    symbol,
                    "positional-only parameter {} may now also be passed "
                    "by keyword".format(label),
                    old=a.kind,
                    new=b.kind,
                )
            )
    if a.has_default and not b.has_default:
        changes.append(
            Change(
                "param-default-removed",
                symbol,
                "parameter {} lost its default and became required".format(label),
                old=a.default,
            )
        )
    elif not a.has_default and b.has_default:
        changes.append(
            Change(
                "param-default-added",
                symbol,
                "parameter {} gained a default ({})".format(label, b.default),
                new=b.default,
            )
        )
    elif a.has_default and b.has_default and a.default != b.default:
        changes.append(
            Change(
                "param-default-value-changed",
                symbol,
                "default of {} changed from {} to {}".format(
                    label, a.default, b.default
                ),
                old=a.default,
                new=b.default,
            )
        )
    if a.annotation != b.annotation:
        changes.append(
            Change(
                "annotation-changed",
                symbol,
                "annotation of {} changed from {} to {}".format(
                    label, a.annotation or "<none>", b.annotation or "<none>"
                ),
                old=a.annotation,
                new=b.annotation,
            )
        )
    return changes
