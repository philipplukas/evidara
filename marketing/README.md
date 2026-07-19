# marketing

The public Evidara page: positioning and a waitlist form. See
[ADR-0039](../docs/adr/0039-public-marketing-surface.md) for the decisions
behind it.

This is the **third** frontend surface, alongside `legal-search/frontend`
(the product) and `platform-control/admin` (the ops panel). It is an
independent npm package with its own `node_modules`, installed with `npm ci` —
the repo is not an npm workspace (#588).

## Quick start

```bash
nvm use          # Node 22, pinned in the root .nvmrc
npm ci
npm run dev      # http://localhost:3000
npm run check    # the gate: typecheck + lint + test
npm run build    # static export into out/
```

## What makes this surface different

**It is public.** Every other Evidara surface sits behind the shared BasicAuth
password in `infra/hetzner/auth/ingress-tls.yaml`. This one deliberately does
not, which makes it the only component whose threat model includes anonymous
internet traffic.

**It is statically exported.** `output: "export"` — the build emits plain
HTML/CSS/JS and the container is a static file server. There is no server
runtime, no route handler, and no outbound network dependency on any other
Evidara container. That is a security property, not just a simplification:
the only publicly reachable surface cannot reach the control plane.

**It does not link to the product.** Not an oversight. Search has unmerged
correctness fixes (#672, #673, #675) and there is no end-user authentication,
so "letting someone try it" would mean handing out the shared operator
password. A test (`page.test.tsx`, "links to no live product surface") fails if
a product link appears. When ADR-0038 (#676) lands a real design-partner flow,
delete that test deliberately.

## Copy rules — read before editing text

All page copy lives in [`src/lib/content.ts`](src/lib/content.ts), not in the
JSX, so a reviewer can audit every claim in one diff.

This is legal technology. An overclaim here is a false statement about system
capability made to people whose professional work depends on it. Two rules,
both enforced by [`content.test.ts`](src/lib/content.test.ts):

1. **No claim without a code path.** Every entry needs an `evidence` field
   pointing at code that does the thing *today*. A roadmap item is not
   evidence. A schema field that is never populated is not evidence — it
   belongs in `NOT_YET` (see `delegates_to`, which is there for exactly that
   reason).
2. **The limitations section is not optional.** `NOT_YET` is load-bearing
   positioning, not a disclaimer. The tests fail if it is trimmed to a token
   note, if a capability card hedges into the future, or if the copy implies
   an AI agent answers legal questions (ADR-0033 §4) or that search is
   semantic (it is BM25).

Claims were last verified against the code on **2026-07-19**. Re-verify when
the platform's capability set changes materially.

## Design tokens

Colour comes from `var(--token)`, sourced from the canonical
[`styles/tokens/tokens.css`](../styles/tokens/tokens.css) per
[ADR-0027](../docs/adr/0027-workspace-admin-visual-language.md). Marketing-local
tokens (reading measure, section rhythm) live in `src/app/globals.css` and must
never leak back into the shared file.

`src/__tests__/marketing-token-parity.test.ts` fails the build on any hardcoded
hex/rgb/hsl/oklch literal — the same guard `platform-control/admin` has.

## Waitlist storage

There is none yet, deliberately (ADR-0039 D3). `src/lib/waitlist.ts` is a
single seam: set `NEXT_PUBLIC_WAITLIST_ENDPOINT` at build time and the form
posts to it; leave it unset and the UI says signups are not open rather than
faking success.

When storage lands it should be **Listmonk on the existing CNPG cluster**, with
its own database *and its own role*, ingress-level rate limiting, a
server-side honeypot re-check, and double opt-in. It should **not** be an
endpoint on platform-control — that service is the operator control plane and
#680 just made it fail closed on purpose.

## Deployment

Not deployed. The proposed ingress is
[`infra/hetzner/marketing/ingress-tls.yaml`](../infra/hetzner/marketing/ingress-tls.yaml),
which requires human review before `kubectl apply` — it is the first Ingress in
the cluster that intentionally omits the BasicAuth middleware, and it needs a
DNS A record for `evidara.veyo.dev` to resolve first.
