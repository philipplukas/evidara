# Licence history

This project has been released under two licences. The change is **forward-only**: it does not
reach back and does not withdraw anything already published.

## The cutover

| | |
|---|---|
| Up to and including commit `36a07ceb` | **Apache License 2.0** |
| From the commit that introduced this file onward | **AGPL-3.0-only** |

`36a07ceb` is the last commit on `main` published under Apache-2.0 — the parent of the relicensing
commit. Every commit reachable from it was released under Apache-2.0 and **stays available under
it**. Anyone who obtained a copy at or before that commit keeps the Apache-2.0 grant permanently;
Apache-2.0 is irrevocable, and nothing here purports to revoke it. You can check out `36a07ceb` or
any of its ancestors today and use it under Apache-2.0.

What changes is the licence on the code *after* that point. A copy obtained from a later commit
carries AGPL-3.0-only terms, including the network-use obligation in section 13.

The two periods do not blend. A file's history may contain both Apache-2.0 and AGPL-3.0 revisions;
which licence applies depends on which revision you took, not on which file you are looking at.

## Why the owner could make this change

Evidara has no outside copyright holders. Counted at the cutover with
`git log --format='%an <%ae>' | sort | uniq -c`:

| Scope | Commits | Philipp Guldimann's identities | Everything else |
|---|---:|---:|---:|
| `main` history | 1,285 | 1,225 | 60 |
| All refs, including unmerged branches | 1,865 | 1,742 | 123 |

"Everything else" is Claude (acting as a tool, under the owner's direction and attributed in commit
trailers), GitHub Copilot, the `coderabbitai` review bot, `github-actions`, and a local `cleanup`
identity. There are **zero third-party human contributors**. No contributor's permission was needed
to relicense, and no retroactive sign-off was collected because there was nobody to collect it
from.

That is exactly the condition that stops being true the moment someone else contributes — which is
why the [CLA](CLA.md) landed in the same change.

## What did not change

- **Third-party dependencies keep their own licences.** Nothing in this repository relicenses
  anything it did not write. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for the material
  copied into this tree, and
  [docs/licensing/agpl-compatibility-audit.md](docs/licensing/agpl-compatibility-audit.md) for the
  dependency audit that established the change was safe to make.
- **The legal corpus is not licensed here.** Primary law acquired through the platform carries the
  terms of the body that issued it. Neither Apache-2.0 nor AGPL-3.0 has anything to say about it.

## Section 13, in one place

AGPL-3.0 section 13 requires that users who interact with the software over a network be offered
its Corresponding Source. This project discharges that by linking to the public repository from
every network-facing surface:

| Surface | Where the link is |
|---|---|
| `legal-search/frontend` | `src/components/layout/RepositoryLink.tsx`, rendered in the app header |
| `platform-control/admin` | `@evidara/shell`'s `RepositoryLink`, rendered in the admin shell header |
| `marketing` | `@evidara/shell`'s `RepositoryLink`, rendered in the page footer |

`legal-search/api` and `platform-control` are HTTP APIs with no rendered UI of their own; they are
reached through the surfaces above, which carry the link.
