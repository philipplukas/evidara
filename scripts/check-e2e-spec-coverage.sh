#!/usr/bin/env bash
#
# Asserts that every Playwright spec under legal-search/frontend/e2e/ is
# actually SELECTED by at least one command CI invokes.
#
# Background (#686): `playwright.config.ts` sets `testDir: "./e2e"` with no
# `projects`, no `testMatch` and no `grep`. Selection happens entirely through
# `-g <tag>` in the npm scripts, so a spec that carries no matching tag is
# committed, linted, typechecked — and executed by nothing. That is how
# `workspace-panels.spec.ts` sat 4/4 red on main unnoticed, and why the geometry
# guard added in #605 has been inert since it landed.
#
# The set of CI-invoked commands is DERIVED from the workflow file rather than
# hardcoded here, so this guard cannot itself drift from what CI runs.
#
# Selection is resolved with `playwright test --list`, which loads the config
# and enumerates matching tests without starting the webServer or a browser.

set -euo pipefail

repo_root="${E2E_COVERAGE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
frontend="$repo_root/legal-search/frontend"
workflow="$repo_root/.github/workflows/legal-search.yml"

# Specs deliberately not reachable from any CI job. Each entry must carry a
# reason — an exclusion is argued for once, not discovered later as a surprise.
#
#   demo-queries.spec.ts — @demo, gated on PLAYWRIGHT_USE_REAL_BACKEND against a
#     live index. It cannot run on the mocked CI webServer, and 3 of its 4
#     queries are still TBD placeholders (#686 §3). Wire it in when a real
#     backend is available to CI (#684).
allowlist=(
  "demo-queries.spec.ts"
)

fail=0
err() {
  echo "FAIL: $*" >&2
  fail=1
}

if [ ! -d "$frontend/node_modules" ]; then
  echo "SKIP: $frontend/node_modules is absent; run 'npm ci' there first." >&2
  exit 0
fi

# 1. Which `npm run e2e:*` scripts does the workflow actually invoke?
mapfile -t ci_scripts < <(
  grep -oE 'npm run (e2e:[a-z0-9:-]+)' "$workflow" 2>/dev/null |
    sed 's/^npm run //' | sort -u
)

if [ "${#ci_scripts[@]}" -eq 0 ]; then
  err "no 'npm run e2e:*' invocations found in $workflow.
     Either the workflow stopped running Playwright, or this guard's parsing
     broke. Both are worth failing on."
  exit 1
fi

# 2. Resolve each script to the specs it selects.
covered=""
for script in "${ci_scripts[@]}"; do
  cmd="$(cd "$frontend" && node -e '
    const pkg = require("./package.json");
    process.stdout.write(pkg.scripts?.[process.argv[1]] ?? "");
  ' "$script")"

  if [ -z "$cmd" ]; then
    err "the workflow invokes 'npm run $script', which is not defined in
     legal-search/frontend/package.json."
    continue
  fi

  # Composite scripts (e.g. e2e:interaction-flow) chain other npm scripts; the
  # scripts they chain are invoked in their own right, so skip the wrapper.
  case "$cmd" in
  *"npm run "*) continue ;;
  esac

  # Strip everything up to and including `playwright test`, keeping the
  # selection arguments (`-g @smoke`, a path, ...). Leading env assignments and
  # any runner prefix fall away with it.
  args="${cmd#*playwright test}"
  [ "$args" = "$cmd" ] && continue # not a playwright invocation

  # shellcheck disable=SC2086 # word splitting of the arg string is intended
  listed="$(cd "$frontend" && npx playwright test --list $args 2>/dev/null |
    grep -oE '^[[:space:]]+[A-Za-z0-9._/-]+\.spec\.ts' | tr -d ' ' | sort -u || true)"

  if [ -z "$listed" ]; then
    err "'npm run $script' selects NO tests at all.
     Its filter matches nothing — the job passes having run nothing."
    continue
  fi
  covered="$covered$listed"$'\n'
done

covered="$(printf '%s' "$covered" | sed '/^$/d' | sort -u)"

# 3. Every spec on disk must appear in that union.
for path in "$frontend"/e2e/*.spec.ts; do
  spec="$(basename "$path")"

  allowed=0
  for entry in "${allowlist[@]}"; do
    [ "$entry" = "$spec" ] && allowed=1
  done

  if printf '%s\n' "$covered" | grep -qxF "$spec"; then
    if [ "$allowed" -eq 1 ]; then
      err "e2e/$spec is on the allowlist but IS selected by CI.
     Remove it from the allowlist in scripts/check-e2e-spec-coverage.sh."
    fi
    continue
  fi

  [ "$allowed" -eq 1 ] && continue

  err "e2e/$spec is selected by no CI command.
     playwright.config.ts has no testMatch/projects, so selection is entirely
     by '-g <tag>' or by path. This spec carries neither, so it runs nowhere
     while still looking maintained (#686).
     Fix by one of:
       - tag its tests with a tag CI greps (@smoke / @contract / @screenshots)
       - add an npm script that runs it by path and invoke it in
         .github/workflows/legal-search.yml
       - add it to the allowlist above WITH a reason"
done

if [ "$fail" -ne 0 ]; then
  echo "" >&2
  echo "e2e spec coverage check failed. See issue #686." >&2
  exit 1
fi

echo "e2e spec coverage: OK (${#ci_scripts[@]} CI commands select every spec under legal-search/frontend/e2e/)"
