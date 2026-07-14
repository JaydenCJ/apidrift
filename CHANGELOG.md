# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- AST-based API extractor: functions, classes, methods, properties,
  classmethods/staticmethods, abstract methods, enums, dataclasses,
  module/class attributes, and `__init__.py` re-exports — all read from
  source text, never by importing the package.
- Publicity rules: literal `__all__` contracts (lists, tuples, `+`
  concatenation, `+=`), underscore privacy for names and modules, dunder
  methods as API, the `from x import y as y` explicit re-export convention,
  and `--include-private` to opt out.
- Structural diff engine with a fixed change taxonomy (~40 kinds) mapped to
  SemVer severities: removals and call-compatibility breaks are major
  (renames, reorders, keyword-only/positional-only moves, lost defaults,
  sync/async flips, property-setter removal, base-class and enum-member
  removal, ...), pure additions
  are minor, and annotation/default-value/re-export plumbing changes are
  patch.
- Semver advisor: worst-severity bump suggestion, the pre-1.0 downshift
  convention (breaking -> minor before 1.0.0), `next_version`, and a
  declared-vs-required bump comparison that reads `[project] version`
  straight from `pyproject.toml` at each ref.
- Source readers for three ref spellings: git revs (via `git ls-tree` +
  `cat-file`, no checkout, dirty worktrees never leak), plain directories,
  and versioned JSON snapshots written by `apidrift dump`.
- `apidrift` CLI: `diff` (text/markdown/json, `--fail-on` CI gate), `bump`
  (one-word answer), `check` (exit 1 when the declared version step is too
  small), and `dump`; package auto-detection for `src/`, flat, and `lib/`
  layouts with `--package` to disambiguate.
- Runnable example fixture (`examples/pricelib-v1` and `-v2`) shipping one
  accidental breaking change alongside harmless additions.
- 91 offline pytest tests and `scripts/smoke.sh`, an end-to-end check that
  builds a real git history and exercises all four subcommands.

### Notes

- The repository ships no CI workflow; verification is local —
  `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/apidrift/releases/tag/v0.1.0
