#!/usr/bin/env bash
#
# Guards the JavaScript dependency-resolution invariants of this monorepo.
#
# Background (#588): the repo is NOT an npm workspace. Each JS surface
# (`legal-search/frontend`, `legal-search/api`, `platform-control/admin`)
# installs its own `node_modules`, and the shared modules under `styles/`
# are consumed via per-surface aliases. That arrangement is easy to break in
# ways that are invisible in CI (which installs one surface per job) but
# corrupt local runs (where developers install several). This script asserts
# the invariants so the rot cannot silently return.
#
# Runs in pre-commit AND in CI (AGENTS.md: "the pre-commit hooks and CI
# workflows must run the same checks").

set -euo pipefail

# `JS_HYGIENE_REPO_ROOT` exists so the guard's own self-test
# (scripts/tests/test_check_js_workspace_hygiene.py) can point it at a fixture
# tree and assert BOTH directions. Unset in every real invocation.
repo_root="${JS_HYGIENE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$repo_root"

fail=0
err() {
  echo "FAIL: $*" >&2
  fail=1
}

# Paths matching a pattern, EXCLUDING anything under node_modules or a nested
# checkout. Prints one path per line; prints nothing when there is no match.
#
# Callers must test the OUTPUT for emptiness, never a pipeline's exit status.
# The obvious-looking `grep -rl … | grep -qv node_modules` is INVERTED: on empty
# input `grep -qv` returns 0 under some implementations (ugrep among them) and 1
# under GNU grep, so the guard fires precisely when the violation is ABSENT.
# That mis-fired for real — it reported a Dockerfile that does not exist.
#
# `.claude/worktrees/` holds agent git worktrees, each a full checkout of some
# OTHER branch. It is gitignored, but `grep -r` does not know that, so every
# worktree still carrying a pre-#588 branch reported as a live violation of the
# very invariant #588 fixed. The result: this gate FAILED on a clean tree
# locally while passing in CI (which checks out fresh and has no worktrees) —
# a gate that disagrees with CI in the direction of false alarm, which is how
# a gate stops being read. Excluded by path, not by `git check-ignore`, so the
# fixture-based self-test does not need a git repo.
matches_outside_node_modules() {
  grep -rl "$@" . 2>/dev/null | grep -v -e '/node_modules/' -e '^\./\.claude/' -e '/\.git/' || true
}

# 1. The root `node_modules` must never be a symlink into a surface.
#
#    A `postinstall` used to symlink `<repo>/node_modules` at whichever
#    surface installed FIRST, so the shared `styles/` modules resolved
#    `react` out of a foreign tree. That yields a SECOND React instance and
#    "Cannot read properties of null (reading 'useContext')" in whichever
#    surface lost the race — a failure that never reproduces in CI.
if [ -L node_modules ]; then
  err "repo-root 'node_modules' is a symlink -> $(readlink node_modules)
     The root package (evidara-doc-tools) is not a workspace root; nothing
     should resolve through it. Remove it:  rm node_modules
     Shared 'styles/' modules must resolve react from the CONSUMING surface
     (tsconfig paths + vitest resolve.dedupe + turbopack resolveAlias)."
fi

# 2. No package may re-introduce a postinstall that links the root.
offenders="$(matches_outside_node_modules '"postinstall".*ensure-monorepo-shared-modules' --include=package.json)"
if [ -n "$offenders" ]; then
  err "a package.json re-introduced the 'ensure-monorepo-shared-modules' postinstall:
$offenders"
fi

# 2b. No Dockerfile may still COPY the deleted symlink script (the image build
#     fails on a missing COPY source, which the unit gates never exercise).
offenders="$(matches_outside_node_modules 'ensure-monorepo-shared-modules' --include='Dockerfile*')"
if [ -n "$offenders" ]; then
  err "a Dockerfile still COPYs scripts/ensure-monorepo-shared-modules.mjs, which no longer exists:
$offenders"
fi

# 3. `legal-search/` must not carry a package.json.
#
#    It used to hold a vestigial one (no `workspaces` field, no `src/`,
#    duplicating the frontend's deps). Nothing in CI installed it, but
#    `npm install` there ERESOLVEs on a @babel/core peer conflict and leaves
#    the tree uninstalled.
if [ -e legal-search/package.json ] || [ -e legal-search/package-lock.json ]; then
  err "legal-search/ has a package.json/package-lock.json again.
     legal-search is not an npm workspace root; the real packages are
     legal-search/frontend and legal-search/api. Installing at legal-search/
     ERESOLVEs (@babel/core peer conflict) and shadows the surfaces."
fi

# 4. Every React surface must dedupe React for the shared `styles/` modules.
#
#    Vite resolves a module's bare imports relative to the IMPORTING file, so
#    `styles/ui/*` would otherwise escape the workspace when resolving react.
for cfg in legal-search/frontend/vitest.config.ts platform-control/admin/vitest.config.ts; do
  if [ ! -f "$cfg" ]; then
    err "expected vitest config missing: $cfg"
    continue
  fi
  if ! grep -q 'dedupe' "$cfg" || ! grep -A2 'dedupe' "$cfg" | grep -q '"react"'; then
    err "$cfg does not dedupe 'react'.
     Shared 'styles/' modules would resolve a second React copy."
  fi
done

# 4b. Every React surface must alias the shared modules' runtime deps for
#     Turbopack, or `next build` fails with "Can't resolve 'clsx'" once the
#     root node_modules symlink is gone. (`react` is intentionally absent —
#     Next owns that resolution.)
for cfg in legal-search/frontend/next.config.ts platform-control/admin/next.config.ts; do
  if [ ! -f "$cfg" ]; then
    err "expected next config missing: $cfg"
    continue
  fi
  for pkg in clsx lucide-react tailwind-merge; do
    if ! grep -q "node_modules/${pkg}\"" "$cfg"; then
      err "$cfg does not resolveAlias '${pkg}' to its own node_modules.
     The shared 'styles/' modules import it; Turbopack cannot resolve it."
    fi
  done
done

# 5. Node must match the version CI pins (see .nvmrc / package.json engines).
#
#    Node >= 24 ships an experimental built-in Web Storage global. Under
#    vitest's jsdom environment it shadows jsdom's own `localStorage`, which
#    then reads back as `undefined` and fails any test touching it. Same code
#    + same node_modules pass on 22 and fail on 26, so an unpinned local Node
#    makes the local gate disagree with CI.
expected_major="$(tr -d 'v \n' < .nvmrc | cut -d. -f1)"
actual_major="$(node -v | tr -d 'v' | cut -d. -f1)"
if [ "$actual_major" != "$expected_major" ]; then
  err "Node $(node -v) does not match the pinned Node v${expected_major} (.nvmrc).
     CI runs Node ${expected_major}; your local test results are not
     trustworthy on this version (Node >= 24 breaks jsdom's localStorage).
     Use:  nvm use   (or install Node ${expected_major})"
fi

# 6. CI must pin the same Node as `.nvmrc`, or "local == CI" is a fiction.
#    (Ignores expression-valued pins like `${{ env.NODE_VERSION }}`.)
while read -r line; do
  ci_major="${line##*: }"
  # shellcheck disable=SC2016 # matching the literal GitHub Actions '${{' token
  case "$ci_major" in
  *'${{'* | '') continue ;;
  esac
  if [ "$ci_major" != "$expected_major" ]; then
    err "a workflow pins node-version: ${ci_major} but .nvmrc pins ${expected_major}.
     CI and local Node must match. Offending pin:
       $line"
  fi
done < <(grep -rn 'node-version: ' .github/workflows/ 2>/dev/null || true)

if [ "$fail" -ne 0 ]; then
  echo "" >&2
  echo "JS workspace hygiene check failed. See issue #588 for the full story." >&2
  exit 1
fi

echo "JS workspace hygiene: OK (no root node_modules symlink, no stale legal-search package, react deduped, Node v${actual_major})"
