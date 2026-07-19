#!/usr/bin/env bash
set -euo pipefail

cd platform-control

uv run ruff check .
uv run ruff format --check .
uv run pytest

# contracts/api/platform-control.openapi.yaml is generated from this app, not
# hand-maintained (#618). Without this gate the contract drifts behind the models
# and consumers that trust it ship bugs — #614 (admin knew 4 of 11 acquisition
# providers and coerced the rest to firecrawl) and #616 (contract omitted the list
# pagination envelope, so the admin capped every list at 100). Mirrors
# legal-search/frontend's `npm run openapi:check`.
uv run python ../scripts/generate_platform_control_contract.py --check

if [[ -f admin/package.json ]]; then
  (
    cd admin

    # Preflight: prove `next` resolves from THIS checkout before invoking Turbopack.
    #
    # Agents routinely run this gate from a git worktree under `.claude/worktrees/`.
    # That directory is nested INSIDE the main checkout, so Node's upward resolution
    # walks out of the worktree and can land on the main checkout's node_modules —
    # in particular via a repo-root `node_modules` symlink, which AGENTS.md forbids
    # and `scripts/check-js-workspace-hygiene.sh` fails on precisely because of this.
    #
    # When that happens `next.config.ts` has already pinned `turbopack.root` to the
    # worktree root, so Turbopack sees `next` living outside its declared root and
    # dies with an opaque workspace-root error about resolving `next/package.json`.
    # The same escape is what yields a second React instance (#588). Fail here, with
    # the actual cause, instead of letting Turbopack guess.
    checkout_root="$(cd ../.. && pwd -P)"

    if [[ ! -d node_modules ]]; then
      echo "check-platform-control: platform-control/admin/node_modules is missing in this checkout." >&2
      echo "  checkout: ${checkout_root}" >&2
      echo "  Each JS surface owns its node_modules (AGENTS.md); a worktree does NOT" >&2
      echo "  inherit the main checkout's. Install them here:" >&2
      echo "    (cd ${checkout_root}/platform-control/admin && nvm use && npm ci)" >&2
      exit 1
    fi

    resolved_next="$(node -e "console.log(require.resolve('next/package.json'))" 2>/dev/null || true)"
    if [[ -z "${resolved_next}" ]]; then
      echo "check-platform-control: cannot resolve 'next' from platform-control/admin." >&2
      echo "  Run 'npm ci' in ${checkout_root}/platform-control/admin." >&2
      exit 1
    fi
    if [[ "${resolved_next}" != "${checkout_root}/"* ]]; then
      echo "check-platform-control: 'next' resolves OUTSIDE this checkout." >&2
      echo "  checkout: ${checkout_root}" >&2
      echo "  next:     ${resolved_next}" >&2
      echo "  Node escaped this checkout and resolved next from another one — Turbopack's" >&2
      echo "  root is pinned to the checkout, so the build would fail with an opaque" >&2
      echo "  'cannot resolve next/package.json' workspace-root error." >&2
      echo "  Usual cause: a repo-root 'node_modules' symlink in the MAIN checkout, which" >&2
      echo "  worktrees under .claude/worktrees/ resolve through. AGENTS.md forbids it:" >&2
      echo "    rm <main-checkout>/node_modules   # it must never be a symlink" >&2
      echo "  Then verify with: bash scripts/check-js-workspace-hygiene.sh" >&2
      exit 1
    fi

    npm run check
    PLATFORM_CONTROL_API_URL="${PLATFORM_CONTROL_API_URL:-http://127.0.0.1:8000}" npm run build
  )
fi
