#!/usr/bin/env bash
#
# Asserts that every Playwright spec on every guarded surface is actually
# SELECTED by at least one command CI invokes.
#
# Background (#686): `playwright.config.ts` sets `testDir: "./e2e"` with no
# `projects`, no `testMatch` and no `grep`. Selection happens entirely through
# `-g <tag>` in the npm scripts, so a spec that carries no matching tag is
# committed, linted, typechecked — and executed by nothing. That is how
# `workspace-panels.spec.ts` sat 4/4 red on main unnoticed, and why the geometry
# guard added in #605 has been inert since it landed.
#
# The platform-control admin was a harder version of the same failure: its six
# specs were selected by nothing because *no workflow ran Playwright for that
# surface at all*. `npm run check` there is typecheck + lint + vitest + openapi.
# So "the code is there" was weak evidence about the built app — which is
# exactly how a clipped ACTIONS column, a contradictory attention chip and a
# non-existent dark mode all survived review. This guard now covers both
# surfaces; a surface with no Playwright job fails loudly instead of quietly.
#
# The set of CI-invoked commands is DERIVED from the workflow file rather than
# hardcoded here, so this guard cannot itself drift from what CI runs.
#
# Selection is resolved with `playwright test --list`, which loads the config
# and enumerates matching tests without starting the webServer or a browser.

set -euo pipefail

repo_root="${E2E_COVERAGE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Guarded surfaces: "<package dir>|<workflow file>|<comma-separated allowlist>".
#
# Each allowlist entry is a spec deliberately unreachable from any CI job, and
# must carry a reason below — an exclusion is argued for once, not discovered
# later as a surprise.
#
#   demo-queries.spec.ts — @demo, gated on PLAYWRIGHT_USE_REAL_BACKEND against a
#     live index. It cannot run on the mocked CI webServer, and 3 of its 4
#     queries are still TBD placeholders (#686 §3). Wire it in when a real
#     backend is available to CI (#684).
SURFACES=(
  "legal-search/frontend|.github/workflows/legal-search.yml|demo-queries.spec.ts"
  "platform-control/admin|.github/workflows/platform-control.yml|"
)

fail=0
err() {
  echo "FAIL: $*" >&2
  fail=1
}

checked_surfaces=0

check_surface() {
  local package_dir="$1" workflow_rel="$2" allowlist_raw="$3"
  local package_path="$repo_root/$package_dir"
  local workflow="$repo_root/$workflow_rel"

  local allowlist=()
  if [ -n "$allowlist_raw" ]; then
    IFS=',' read -r -a allowlist <<<"$allowlist_raw"
  fi

  if [ ! -d "$package_path/node_modules" ]; then
    echo "SKIP: $package_path/node_modules is absent; run 'npm ci' there first." >&2
    return 0
  fi

  # 1. Which `npm run e2e*` scripts does the workflow actually invoke?
  local ci_scripts=()
  mapfile -t ci_scripts < <(
    grep -oE 'npm run (e2e[a-z0-9:-]*)' "$workflow" 2>/dev/null |
      sed 's/^npm run //' | sort -u
  )

  if [ "${#ci_scripts[@]}" -eq 0 ]; then
    err "no 'npm run e2e*' invocations found in $workflow_rel.
     Either the workflow stopped running Playwright for $package_dir, or this
     guard's parsing broke. Both are worth failing on: specs that no job runs
     look maintained and prove nothing."
    return 0
  fi

  # 2. Resolve each script to the specs it selects.
  local covered="" script cmd args listed
  for script in "${ci_scripts[@]}"; do
    cmd="$(cd "$package_path" && node -e '
      const pkg = require("./package.json");
      process.stdout.write(pkg.scripts?.[process.argv[1]] ?? "");
    ' "$script")"

    if [ -z "$cmd" ]; then
      err "$workflow_rel invokes 'npm run $script', which is not defined in
     $package_dir/package.json."
      continue
    fi

    # Composite scripts (e.g. e2e:interaction-flow) chain other npm scripts; the
    # scripts they chain are invoked in their own right, so skip the wrapper.
    case "$cmd" in
    *"npm run "*) continue ;;
    esac

    # Strip everything up to and including `playwright test`, keeping the
    # selection arguments (`-g @smoke`, a path, ...). Leading env assignments and
    # any runner prefix fall away with it. A script that is not a `playwright
    # test` invocation at all (`playwright install chromium`) falls out here.
    args="${cmd#*playwright test}"
    [ "$args" = "$cmd" ] && continue

    # `--list` prefixes each line with the project name when the config declares
    # `projects` (`  [chromium] › foo.spec.ts:12:3 › …`) and does not when it
    # does not (`  e2e/foo.spec.ts:12:3 › …`). Matching the spec name anywhere on
    # the line, then reducing to a basename, handles both — an anchored pattern
    # silently matched nothing for the admin surface, which reads exactly like
    # "this job runs no tests" and is the failure mode this script exists to
    # report rather than to have.
    # shellcheck disable=SC2086 # word splitting of the arg string is intended
    listed="$(cd "$package_path" && npx playwright test --list $args 2>/dev/null |
      grep -oE '[A-Za-z0-9._/-]+\.spec\.ts' | sed 's|.*/||' | sort -u || true)"

    if [ -z "$listed" ]; then
      err "'npm run $script' ($package_dir) selects NO tests at all.
     Its filter matches nothing — the job passes having run nothing."
      continue
    fi
    covered="$covered$listed"$'\n'
  done

  covered="$(printf '%s' "$covered" | sed '/^$/d' | sort -u)"

  # 3. Every spec on disk must appear in that union.
  local path spec entry allowed
  for path in "$package_path"/e2e/*.spec.ts; do
    [ -e "$path" ] || continue
    spec="$(basename "$path")"

    allowed=0
    for entry in ${allowlist[@]+"${allowlist[@]}"}; do
      [ "$entry" = "$spec" ] && allowed=1
    done

    if printf '%s\n' "$covered" | grep -qxF "$spec"; then
      if [ "$allowed" -eq 1 ]; then
        err "$package_dir/e2e/$spec is on the allowlist but IS selected by CI.
     Remove it from the allowlist in scripts/check-e2e-spec-coverage.sh."
      fi
      continue
    fi

    [ "$allowed" -eq 1 ] && continue

    err "$package_dir/e2e/$spec is selected by no CI command.
     playwright.config.ts has no testMatch/projects, so selection is entirely
     by '-g <tag>' or by path. This spec carries neither, so it runs nowhere
     while still looking maintained (#686).
     Fix by one of:
       - tag its tests with a tag CI greps (@smoke / @contract / @screenshots)
       - add an npm script that runs it by path and invoke it in
         $workflow_rel
       - add it to the allowlist above WITH a reason"
  done

  checked_surfaces=$((checked_surfaces + 1))
  if [ "$fail" -eq 0 ]; then
    echo "e2e spec coverage: $package_dir OK (${#ci_scripts[@]} CI commands select every spec)"
  fi
}

for surface in "${SURFACES[@]}"; do
  IFS='|' read -r surface_dir surface_workflow surface_allowlist <<<"$surface"
  check_surface "$surface_dir" "$surface_workflow" "$surface_allowlist"
done

if [ "$fail" -ne 0 ]; then
  echo "" >&2
  echo "e2e spec coverage check failed. See issue #686." >&2
  exit 1
fi

if [ "$checked_surfaces" -eq 0 ]; then
  echo "e2e spec coverage: no surface had node_modules installed; nothing was checked." >&2
  exit 0
fi

echo "e2e spec coverage: OK ($checked_surfaces surface(s) checked)"
