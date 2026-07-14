# apidrift rule reference

This document is the contract behind every `MAJOR`/`MINOR`/`PATCH` line
apidrift prints. The mapping lives in `src/apidrift/rules.py` and is pinned
by the test suite; changing a severity is itself a breaking change of
apidrift.

Severities assume a package at `>= 1.0.0`. Before 1.0.0 the suggested bump
is downshifted one notch (breaking -> minor, additive/compatible -> patch),
matching the convention Cargo uses; the rule table itself never changes.

## What counts as public API

- If a module defines a **literal `__all__`** (list/tuple, `+`
  concatenation, `+=` extension), exactly those names are public —
  underscore-prefixed names included. A dynamic `__all__` is an error:
  apidrift refuses to guess a contract it cannot read.
- Otherwise, a defined name is public unless it starts with `_`.
- **Dunder methods** (`__init__`, `__call__`, ...) are public API — they are
  the class's calling convention. Dunder *attributes* (`__slots__`, ...) are
  not.
- In an `__init__.py`, public **imported names are re-exports** (that is how
  packages assemble their top-level API). In regular modules, imports are
  only API when marked with the redundant-alias convention
  (`from x import y as y`).
- Modules with any underscore-prefixed path component are private wholesale.
- `--include-private` disables all of the above filtering.

## Major — existing callers can break

| Kind | Trigger |
|---|---|
| `module-removed` | a public module disappeared |
| `function-removed` / `class-removed` / `method-removed` / `variable-removed` / `attribute-removed` / `reexport-removed` | a public symbol disappeared (or became private) |
| `enum-member-removed` | an enum lost a member |
| `param-removed` | a parameter disappeared |
| `param-added-required` | a new parameter without a default (positional or keyword-only) |
| `param-renamed` | a keyword-capable parameter changed its name |
| `param-reordered` | positional parameters swapped positions |
| `param-became-keyword-only` | positional callers now break |
| `param-became-positional-only` | keyword callers now break |
| `param-default-removed` | an optional parameter became required |
| `var-positional-removed` / `var-keyword-removed` | `*args` / `**kwargs` disappeared |
| `async-changed` | sync -> async or async -> sync |
| `role-changed` | property <-> method <-> classmethod <-> staticmethod |
| `property-setter-removed` | `obj.attr = value` assignments now break |
| `method-became-abstract` | existing subclasses stop instantiating |
| `base-removed` | `isinstance`/`issubclass` and inherited API can break |
| `symbol-kind-changed` | e.g. a function became a class |

## Minor — new surface, old callers unaffected

| Kind | Trigger |
|---|---|
| `module-added` / `function-added` / `class-added` / `method-added` / `variable-added` / `attribute-added` / `reexport-added` | new public symbol |
| `enum-member-added` | an enum gained a member |
| `param-added-optional` | a new parameter with a default |
| `param-default-added` | a required parameter became optional |
| `param-became-flexible` | keyword-only -> positional-or-keyword, or positional-only relaxed |
| `property-setter-added` | the property became assignable |
| `var-positional-added` / `var-keyword-added` | `*args` / `**kwargs` appeared |
| `base-added` | new base class |
| `method-became-concrete` | an abstract method gained an implementation |

## Patch — visible in source, compatible at call sites

| Kind | Trigger |
|---|---|
| `annotation-changed` / `return-annotation-changed` | type hints changed (not enforced at runtime) |
| `param-default-value-changed` | same parameter, different default |
| `param-renamed-positional-only` | the name was never usable by callers |
| `variable-value-changed` | a literal constant changed value |
| `reexport-target-changed` | the name resolves elsewhere (or became a local definition) |

## Deliberate limitations

- **Literal values only.** Computed values (`X = compute()`) are opaque;
  opaque-to-opaque changes are never reported, so refactors do not create
  noise. Behavior changes inside function bodies are out of scope by design
  — apidrift tracks the *surface*, not the semantics.
- **Annotations are patch-level.** Python does not enforce them at runtime.
  Projects that treat typing as contract can still gate on
  `--fail-on patch`.
- **Inheritance is not resolved.** Methods inherited from a base class are
  attributed to the base, so moving a method up the hierarchy reports a
  removal on the subclass. This is honest: apidrift never imports code, and
  the base may live in another distribution.
- **Top-level statements only.** Symbols defined under `if`/`try` blocks
  (conditional imports, version shims) are not extracted in 0.1.0.
