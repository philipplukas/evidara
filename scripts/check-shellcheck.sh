#!/usr/bin/env bash
set -euo pipefail

# Lint every tracked shell script with shellcheck.
#
# WHY THIS EXISTS
# ---------------
# The repo already carried `# shellcheck disable=` directives in `scripts/` and in
# a workflow, so someone was linting locally at some point — but nothing enforced
# it, in pre-commit or in CI. AGENTS.md is explicit that the two must run the same
# checks and names `scripts/` as the shared entry point.
#
# The backlog when this landed was 14 findings across 58 scripts, zero errors —
# small enough to clear in one pass rather than defer behind a warning-only mode.
# The one with teeth was `export DOCKER_CONFIG="$(mktemp -d)"` in a deploy script:
# `export` always returns 0, so under `set -e` a failing mktemp was invisible and
# helm fell back to the broken credsStore that line exists to avoid.
#
# `-x` follows `source`d files, which is what lets the fast-loop harnesses be
# checked against `fast-loop-evidence.sh` rather than reporting SC1091 on every
# run. It also means a bug in a sourced library surfaces at its callers.
#
# Deliberate suppressions carry a reason inline (`# shellcheck disable=SCxxxx # why`).
# A bare disable with no reason is worse than the finding it hides.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v shellcheck >/dev/null 2>&1; then
  echo "error: shellcheck is not installed." >&2
  echo "  Developer tooling is workstation-managed (see AGENTS.md):" >&2
  echo "    Arch:   sudo pacman -S shellcheck" >&2
  echo "    Debian: sudo apt install shellcheck" >&2
  echo "    macOS:  brew install shellcheck" >&2
  exit 1
fi

mapfile -t scripts < <(git ls-files '*.sh')

if [[ "${#scripts[@]}" -eq 0 ]]; then
  # A glob that silently matches nothing would make this gate vacuous — the
  # failure mode this repo keeps paying for (#605, #675, #713).
  echo "error: no tracked *.sh files found; the gate would pass without checking anything." >&2
  exit 1
fi

echo "==> shellcheck -x over ${#scripts[@]} tracked shell scripts"
if ! shellcheck -x "${scripts[@]}"; then
  echo "" >&2
  echo "❌ shellcheck reported findings." >&2
  echo "   Fix them, or suppress with a reason:" >&2
  echo "     # shellcheck disable=SC2086 # intentional: word splitting is wanted here" >&2
  exit 1
fi

echo "✅ shellcheck clean."
