# Contributing to apidrift

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Development setup

```bash
git clone https://github.com/JaydenCJ/apidrift
cd apidrift
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Python >= 3.9 and a `git` binary on `PATH` are the only prerequisites.

## Running the checks

```bash
pytest                 # 91 unit + CLI tests, fully offline
bash scripts/smoke.sh  # end-to-end: real git history, all four subcommands
```

Both must pass before a pull request is reviewed; the smoke script prints
`SMOKE OK` on success. The suite creates its own throwaway git repositories
under a temp directory and never touches the network.

## Ground rules

- **No new runtime dependencies.** The package is standard-library only
  (plus the `git` CLI at runtime); that is a feature, not an accident.
  Test-only dependencies belong in the `dev` extra.
- **Never import the package under inspection.** Every fact apidrift reports
  must come from `ast`. If a rule cannot be decided statically, report
  nothing or fail loudly — never execute user code to find out.
- **Severity mappings are contract.** Changing a kind's severity in
  `rules.py` is itself a breaking change: update `docs/rules.md` and the
  tests pinning the table in the same pull request.
- **Every public API needs an English docstring and a test.** Keep logic in
  pure, unit-testable modules; the CLI layer stays thin.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` share the same structure; update all three when you change
  one (English is the authoritative version).

## Reporting bugs

Please include `apidrift --version`, the exact command line, the two refs
being compared, and — ideally — a minimal pair of module sources that
reproduces the wrong (or missing) change report. `apidrift dump` output for
both sides makes diagnosis almost mechanical.

## Security

Please do not report security issues in public GitHub issues. Use GitHub's
private vulnerability reporting on the repository instead.
