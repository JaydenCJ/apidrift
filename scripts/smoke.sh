#!/usr/bin/env bash
# Smoke test for apidrift: build a tiny git history from the example
# fixtures, then exercise diff / bump / check / dump end-to-end.
# Self-contained: pure stdlib + the git CLI, no network, idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# The package has zero runtime dependencies, so running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/apidrift-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"
echo "[smoke] git:    $(git --version)"

# 0. Build a two-commit repo: v1.4.2 tagged, then the (accidentally
#    breaking) v2 committed on top declaring only a minor version bump.
REPO="$WORKDIR/pricelib"
mkdir -p "$REPO"
git -C "$REPO" init -q -b main
git -C "$REPO" config user.email dev@example.test
git -C "$REPO" config user.name "apidrift smoke"
git -C "$REPO" config commit.gpgsign false

cp -R "$ROOT/examples/pricelib-v1/." "$REPO/"
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "release 1.4.2"
git -C "$REPO" tag v1.4.2
rm -rf "$REPO/src"
cp -R "$ROOT/examples/pricelib-v2/." "$REPO/"
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "release 1.5.0 (oops)"

# 1. diff between two git refs finds the breakage and suggests major.
diff_out="$("$PYTHON" -m apidrift diff v1.4.2 HEAD --repo "$REPO")" \
  || fail "diff between refs exited non-zero"
echo "$diff_out" | sed 's/^/[diff] /'
echo "$diff_out" | grep -q "MAJOR  pricelib.money.convert: parameter rate became keyword-only" \
  || fail "diff missed the keyword-only break"
echo "$diff_out" | grep -q "MAJOR  pricelib.money.format_price: public function removed" \
  || fail "diff missed the removed function"
echo "$diff_out" | grep -q "suggested bump: major (1.4.2 -> 2.0.0)" \
  || fail "diff did not suggest a major bump"

# 2. the second ref defaults to the working tree (the README quickstart).
wt_out="$(cd "$REPO" && "$PYTHON" -m apidrift diff v1.4.2)" \
  || fail "default-worktree diff exited non-zero"
echo "$wt_out" | grep -q "apidrift: v1.4.2 -> worktree (package pricelib)" \
  || fail "default-worktree diff did not label the new side 'worktree'"

# 3. bump prints exactly one word.
bump_out="$("$PYTHON" -m apidrift bump v1.4.2 HEAD --repo "$REPO")"
[ "$bump_out" = "major" ] || fail "bump printed '$bump_out', expected 'major'"

# 4. check catches the insufficient declared bump (1.4.2 -> 1.5.0) with exit 1.
set +e
check_out="$("$PYTHON" -m apidrift check v1.4.2 HEAD --repo "$REPO" 2>&1)"
check_rc=$?
set -e
echo "$check_out" | sed 's/^/[check] /'
[ "$check_rc" -eq 1 ] || fail "check should exit 1 on an insufficient bump, got $check_rc"
echo "$check_out" | grep -q "required bump: major, declared bump: minor" \
  || fail "check did not explain the mismatch"

# 5. check passes once the new side declares 2.0.0.
"$PYTHON" -m apidrift check v1.4.2 HEAD --repo "$REPO" --new-version 2.0.0 >/dev/null \
  || fail "check with --new-version 2.0.0 should pass"

# 6. dump a snapshot of v1.4.2, then diff the snapshot against HEAD.
"$PYTHON" -m apidrift dump v1.4.2 --repo "$REPO" -o "$WORKDIR/api-v1.json" \
  || fail "dump exited non-zero"
grep -q '"format_version": 1' "$WORKDIR/api-v1.json" || fail "snapshot missing format_version"
snap_out="$("$PYTHON" -m apidrift diff "$WORKDIR/api-v1.json" HEAD --repo "$REPO")"
echo "$snap_out" | grep -q "MAJOR  pricelib.money.format_price" \
  || fail "diff against a snapshot missed the removed function"

# 7. plain directory-vs-directory diff needs no git repo at all.
dir_out="$("$PYTHON" -m apidrift diff "$ROOT/examples/pricelib-v1" "$ROOT/examples/pricelib-v2")"
echo "$dir_out" | grep -q "suggested bump: major" \
  || fail "directory diff did not suggest a major bump"

# 8. --fail-on turns the diff into a CI gate (exit 1).
set +e
"$PYTHON" -m apidrift diff v1.4.2 HEAD --repo "$REPO" --fail-on major >/dev/null
gate_rc=$?
set -e
[ "$gate_rc" -eq 1 ] || fail "--fail-on major should exit 1, got $gate_rc"

# 9. identical refs: clean report, gate stays green.
"$PYTHON" -m apidrift diff v1.4.2 v1.4.2 --repo "$REPO" --fail-on patch >/dev/null \
  || fail "identical refs should pass --fail-on patch"

# 10. --version agrees with the package metadata.
version_out="$("$PYTHON" -m apidrift --version)"
pkg_version="$("$PYTHON" -c 'import apidrift; print(apidrift.__version__)')"
[ "$version_out" = "apidrift $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

echo "SMOKE OK"
