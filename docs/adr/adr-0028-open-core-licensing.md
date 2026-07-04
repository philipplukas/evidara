# ADR-0028: Open-core licensing (AGPL-3.0 code + CC-BY-4.0 data) and CLA

Status: Proposed
Date: 2026-07-04
Deciders: Owner / Project lead
Related: ADR-0004 (contract strategy), ADR-0026 (`authority_id` / `jurisdiction_id` naming policy)

## Context

Evidara has, until now, carried no license file. Under default copyright law
that makes the repository "all rights reserved": even though the code is
readable, no third party may legally use, modify, fork, or contribute to it.
That is fine while the project is private, but it blocks two things the project
wants:

1. **An open-law contribution.** Evidara processes public legal and regulatory
   content (Fedlex and other national sources) and produces reusable,
   machine-readable structure: shared IDs, JSON Schemas, jurisdiction overlays.
   That structure has the most value when it is openly adopted by the wider
   open-law ecosystem (ECLI, Akoma Ntoso / LegalDocML, civic-tech, researchers).
2. **A preserved commercial path.** The project may later become a commercial
   product or company. The license structure chosen now must not foreclose
   selling, hosting, or dual-licensing the same code later.

These two goals are usually framed as opposed. They are not, provided the
copyright holder retains the rights needed to relicense. This ADR records the
structure that keeps both open.

The copyright holder is the individual project owner (personal project, no
employer assignment). This is the precondition that makes dual-licensing
possible and must remain true.

## Decision

### 1. Open core, split by artifact type

The repository is licensed under **two** licenses, chosen per artifact class:

| Artifact class | License | Rationale |
|---|---|---|
| Platform **code** (`platform-control/`, `document-intelligence/`, `legal-search/`, `infra/`, `scripts/`, `tools/`, `service-template/`, `k8s/`) | **GNU AGPL-3.0-only** (`/LICENSE`) | Strong copyleft moat for a network-served product; preserves a dual-license lever. |
| **Data, schemas, and contracts** (`contracts/`, `country-overlays/`, `docs/`) | **CC-BY-4.0** (`/LICENSE-data`) | Maximizes adoption of the open-law contribution; attribution only. |

Where a directory's applicable license is not obvious, that directory carries a
short `README`/`LICENSE` pointer stating which of the two applies. In case of
conflict, the pointer nearest the file wins; absent a pointer, code defaults to
AGPL-3.0 and data/documentation defaults to CC-BY-4.0.

Vendored third-party material (e.g. `vendor/`) keeps its upstream license and is
out of scope for this ADR.

### 2. AGPL-3.0, not permissive, for the core

The core is served over a network. AGPL-3.0's §13 (remote-network-interaction
clause) requires anyone who runs a modified version as a network service to
offer their modifications under AGPL-3.0. A permissive license (MIT/Apache-2.0)
would let a third party build a closed hosted competitor and contribute nothing
back, forfeiting both the moat and the future dual-license option. AGPL-3.0
keeps individual and research use free while making closed commercial hosting
require a separate agreement with the copyright holder.

### 3. Dual-licensing is retained as a future option

Because the owner holds copyright on the entire code base, the owner is not
bound by AGPL-3.0 and may additionally offer the same code under a separate
**commercial license** to parties who cannot accept copyleft terms. No such
commercial license is published today; this ADR only records that the structure
keeps it available. Publishing a commercial-license offer is a future decision.

### 4. Contributor License Agreement (CLA)

To keep dual-licensing possible, **every external contribution requires a signed
CLA** (`/CLA.md`) granting the project owner a broad, sublicensable,
relicensable license to the contribution. Without this, the first merged outside
contribution would leave part of the code base un-relicensable and permanently
foreclose §3. The CLA is enforced on pull requests (CLA Assistant or an
equivalent bot); see `CLA.md` for wiring. A lighter DCO (`Signed-off-by`) is
explicitly **not** sufficient here because it does not grant relicensing rights.

### 5. Data provenance obligation

CC-BY-4.0 on `country-overlays/` and `contracts/` covers **Evidara's own**
structuring work, not the underlying primary legal texts, which carry their own
upstream terms. Each ingested source must record its upstream license / terms of
use and provenance before any data dump derived from it is published. This
obligation is additive to ADR-0026's ID-as-contract rules.

## Alternatives considered

### A. Permissive (MIT / Apache-2.0) for everything

Rejected: removes the moat and the dual-license lever. Anyone, including a
well-funded competitor, could ship a closed hosted product on the core and owe
nothing. Permissive is appropriate for the *data/schema* layer (adoption is the
goal there) but not for the code the project may monetize.

### B. Fully proprietary / closed

Rejected: forfeits the open-law contribution, the distribution and credibility
benefits of building in public, and community-contributed jurisdiction
coverage — the project's primary near-term source of value — while protecting
revenue that does not yet exist.

### C. AGPL for code, but no CLA (DCO only)

Rejected: a DCO certifies provenance but does not grant the owner the right to
relicense. The first external contribution would make the code base
un-relicensable and kill the dual-license option in §3.

### D. Single license across code and data

Rejected: code and data want different terms. AGPL on the overlays would
discourage exactly the open-law reuse those files exist to enable; CC-BY on the
code would leave the core with no copyleft protection.

## Consequences

**Positive:**

- The open-law contribution (schemas, IDs, overlays) is openly reusable under
  CC-BY-4.0, maximizing adoption and goodwill.
- The core carries a copyleft moat: hosted forks must open their changes or
  obtain a separate license.
- The dual-license / commercial path is preserved, not foreclosed, by the CLA.
- Building in public becomes a distribution and credibility asset.

**Negative / obligations:**

- Every external contributor must sign the CLA before merge; this adds a small
  amount of friction and a bot to maintain.
- The code/data license boundary must be kept accurate as new directories are
  added (per-directory pointers).
- Commercial ambition depends on the copyright holder remaining the individual
  owner; any future assignment (e.g. to a company) must be handled deliberately.
- Upstream source terms must be tracked per §5 before publishing derived data.

## Implementation

- **`/LICENSE`** — verbatim GNU AGPL-3.0.
- **`/LICENSE-data`** — verbatim CC-BY-4.0.
- **`/CLA.md`** — contributor agreement + CLA Assistant wiring note.
- **README "Licensing & Commercial Use"** — human-readable summary of the split
  and of free vs. commercial use.
- **Per-directory pointers** — `contracts/README.md`, `country-overlays/README.md`.
- **This ADR** — records the decision; status `Proposed` until the owner
  accepts and the repository is made public.

## References

- `/LICENSE`, `/LICENSE-data`, `/CLA.md`
- GNU AGPL-3.0: <https://www.gnu.org/licenses/agpl-3.0.html>
- CC-BY-4.0: <https://creativecommons.org/licenses/by/4.0/>
- ADR-0026 — `authority_id` / `jurisdiction_id` naming policy (IDs as contracts)
- `docs/architecture/clean-room-principles.md`
