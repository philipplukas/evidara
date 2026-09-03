#!/usr/bin/env bash
#
# Syntax-check every workflow script in this directory.
#
# Workflow scripts are NOT standalone modules: the Workflow tool strips `export const meta` and
# runs the rest of the body inside an async function, which is why they legally use top-level
# `await` and a top-level `return`. A bare `node --check foo.js` rejects both — the `return` as an
# "Illegal return statement", and the whole file as CommonJS because the repo root is not
# `type: module`. So this wraps each script the way the tool does before parsing it.
#
# This is a PARSE check only. It cannot tell you the script does the right thing, and none of these
# scripts has ever been executed. See README.md.
#
# Usage:  bash .claude/workflows/check-syntax.sh
# Node:   must be 22 (.nvmrc) — export NVM_DIR="$HOME/.config/nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail=0
found=0

for src in "$here"/*.js; do
  [ -e "$src" ] || continue
  found=$((found + 1))
  name="$(basename "$src" .js)"
  out="$tmp/$name.mjs"
  {
    printf 'async function __workflow_body__() {\n'
    # `export const meta` becomes a plain const so it can live inside the wrapper.
    sed 's/^export const meta/const meta/' "$src"
    printf '\n}\nvoid __workflow_body__;\n'
  } >"$out"

  if node --check "$out" 2>"$tmp/$name.err"; then
    echo "OK    $name"
  else
    echo "FAIL  $name" >&2
    sed 's/^/      /' "$tmp/$name.err" >&2
    fail=1
  fi
done

if [ "$found" -eq 0 ]; then
  echo "no workflow scripts found in $here" >&2
  exit 1
fi

if [ "$fail" -ne 0 ]; then
  echo "" >&2
  echo "workflow syntax check FAILED" >&2
  exit 1
fi

echo "workflow syntax: OK ($found script(s), Node $(node -v))"
