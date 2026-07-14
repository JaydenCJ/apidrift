# apidrift examples

`pricelib-v1/` and `pricelib-v2/` are two versions of a deliberately small
fake library. v2 ships one **accidental breaking change** (`convert` made
`rate` keyword-only, `format_price` deleted) buried under harmless additions
— exactly the situation apidrift exists to catch — while its `pyproject.toml`
only steps the version from `1.4.2` to `1.5.0`.

## Directory-vs-directory diff (no git needed)

From the repository root:

```bash
python -m apidrift diff examples/pricelib-v1 examples/pricelib-v2
```

Expected output:

```text
apidrift: examples/pricelib-v1 -> examples/pricelib-v2 (package pricelib)

MAJOR  pricelib.money.convert: parameter rate became keyword-only; positional callers break
MAJOR  pricelib.money.format_price: public function removed
MINOR  pricelib.with_tax: public reexport added
MINOR  pricelib.cart.Cart.add: optional parameter note added (default None)
MINOR  pricelib.money.Money.rounded: optional parameter mode added (default 'half-even')
MINOR  pricelib.tax: public module added
PATCH  pricelib.money.DEFAULT_CURRENCY: value changed from 'USD' to 'EUR'

2 breaking, 4 additions, 1 compatible
suggested bump: major (1.4.2 -> 2.0.0)
```

## The same diff as a git history

`scripts/smoke.sh` turns these fixtures into a real two-commit repository
(v1 tagged `v1.4.2`, v2 on top) and then runs `diff`, `bump`, `check`, and
`dump` against actual refs. Read it as a worked example of wiring apidrift
into a release pipeline:

```bash
bash scripts/smoke.sh
```

The `check` step is the interesting one: v2 declares only a minor version
bump, so `apidrift check v1.4.2 HEAD` exits 1 with
`required bump: major, declared bump: minor`.
