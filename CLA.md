# Evidara Contributor License Agreement (CLA)

> **Template — not yet legal advice.** This CLA is scaffolding for the
> open-core structure recorded in [ADR-0028](docs/adr/adr-0028-open-core-licensing.md).
> Before you rely on it to accept external contributions or to sell a
> commercial license, have an IP lawyer review the wording (especially the
> relicensing grant in §2 and §3) and confirm the named copyright holder.
> Replace **"the Project Owner"** below with the actual legal copyright
> holder name once confirmed (current assumption: **Philipp Lukas**).

## Why this exists

Evidara's core code is licensed under the GNU AGPL-3.0 (`LICENSE`), and its
data/schemas under CC-BY-4.0 (`LICENSE-data`). The project intends to keep open
the option of also offering the code under a separate **commercial license**
(dual-licensing; see ADR-0028 §3).

That option only survives if the Project Owner holds a broad enough license to
**every** contribution to relicense it. If an external contribution were merged
without such a grant, that part of the code base could no longer be
relicensed, and dual-licensing would be permanently foreclosed. This CLA
secures that grant. It does **not** transfer your copyright — you keep it.

## Agreement

By signing this CLA (see "How to sign" below), You accept and agree to the
following terms for Your present and future Contributions submitted to Evidara.

### 1. Definitions

- **"You" / "Your"** means the individual or legal entity making a Contribution.
- **"Contribution"** means any original work of authorship, including any
  modifications or additions to an existing work, that You intentionally submit
  to the Project (via pull request, patch, or otherwise) for inclusion in, or
  documentation of, Evidara.
- **"the Project Owner"** means the copyright holder of Evidara identified above.

### 2. Copyright license grant

You grant to the Project Owner, and to recipients of software distributed by the
Project Owner, a perpetual, worldwide, non-exclusive, royalty-free,
irrevocable copyright license to reproduce, prepare derivative works of,
publicly display, publicly perform, sublicense, and distribute Your
Contributions and such derivative works.

You further grant the Project Owner the right to **license and sublicense Your
Contributions under any license terms**, including the AGPL-3.0, other
open-source licenses, and separate proprietary or commercial license terms. This
is the grant that makes dual-licensing (ADR-0028 §3) possible. You retain all
right, title, and interest in and to Your Contributions; this is a license, not
an assignment.

### 3. Patent license grant

You grant to the Project Owner and to recipients of software distributed by the
Project Owner a perpetual, worldwide, non-exclusive, royalty-free, irrevocable
(except as stated in this section) patent license to make, have made, use, offer
to sell, sell, import, and otherwise transfer Your Contributions, where such
license applies only to those patent claims licensable by You that are
necessarily infringed by Your Contribution alone or by combination of Your
Contribution with the work to which it was submitted. If any entity institutes
patent litigation against You or any other entity alleging that Your
Contribution, or the work to which You contributed, constitutes direct or
contributory patent infringement, then any patent licenses granted under this
CLA for that Contribution or work terminate as of the date such litigation is
filed.

### 4. Your representations

You represent that:

- Each of Your Contributions is Your original creation, or You have sufficient
  rights to grant the licenses in §2 and §3.
- Your Contribution does not knowingly violate any third party's copyright,
  patent, trademark, trade secret, or other intellectual-property right.
- If Your employer has rights to intellectual property You create, You have
  received permission to make the Contributions on behalf of that employer, or
  Your employer has waived such rights, or Your employer has signed the entity
  version of this CLA.
- You will notify the Project if any statement above becomes inaccurate.

### 5. Third-party work

If You submit work that is not Your original creation, You must submit it
separately from any original Contribution, clearly identify it as such
(including its source and license), and mark it conspicuously (e.g.
`[third-party]`) so the Project can evaluate it.

### 6. No obligation

You understand that the decision to include Your Contribution in any product or
source repository is entirely that of the Project Owner, and this CLA does not
obligate the Project Owner to use or incorporate Your Contribution.

### 7. Disclaimer

Unless required by applicable law or agreed to in writing, You provide Your
Contributions on an "AS IS" basis, without warranties or conditions of any kind,
either express or implied.

## How to sign

Contributions to Evidara require agreement to this CLA:

1. **Automated (preferred).** The repository uses a CLA bot
   ([CLA Assistant](https://github.com/cla-assistant/cla-assistant) or an
   equivalent GitHub Action). On your first pull request, the bot posts a
   comment; agreeing there (a one-time click / signed comment) records your
   signature against your GitHub identity for all future PRs.
2. **Manual fallback.** If the bot is unavailable, add a line to your pull
   request description:

   ```text
   I have read and agree to the Evidara CLA (CLA.md).
   Signed: <Your full legal name>, <email>, <GitHub username>, <date>
   ```

Entities (companies contributing via employees) should contact the Project Owner
to sign the entity version of this agreement before their employees contribute.

## Setting up CLA Assistant (maintainer note)

To enforce this on pull requests:

- **Hosted:** authorize <https://cla-assistant.io> against this repository and
  point it at this `CLA.md`. It blocks PR merge until the author has signed.
- **Self-hosted / Action:** add the
  [`contributor-assistant/github-action`](https://github.com/contributor-assistant/github-action)
  workflow under `.github/workflows/`, storing signatures in a
  `signatures/` file or a dedicated branch. Configure the required status check
  in the branch-protection rules for `main` (see `docs/setup/branch-rules.md`).

Until the bot is wired up, accept external PRs only with the manual §"How to
sign" attestation in the PR description.
