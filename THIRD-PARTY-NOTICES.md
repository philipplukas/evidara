# Third-party notices

This repository stores copies of material authored by third parties. Their licences require that
the notices below travel with those copies. **These obligations come from the third parties'
licences, not from this project's own** — they hold regardless of what this repository is licensed
under, and are unaffected by it. (That licence is now [AGPL-3.0-only](LICENSE) as of 2026-09-19;
it was Apache-2.0 from 2026-09-16, and before that the repository carried no licence at all. See
[LICENSE-HISTORY.md](LICENSE-HISTORY.md). Nothing in this file changed as a result: relicensing our
own work cannot and does not relicense anyone else's.)

Scope: material **copied into this tree**, and **data redistributed in this tree**. Dependencies
that are merely installed from a registry are not listed here; their obligations attach to a built
artifact (container image, static export, bundle), not to this source.

---

## 1. Material copied into this repository

### circle-flags

- `legal-search/frontend/public/flags/ch.svg`
- `legal-search/frontend/public/flags/at.svg`

Copied verbatim from [circle-flags](https://github.com/HatScripts/circle-flags) by HatScripts.
Both files are byte-identical to the published `circle-flags@2.8.2` package:

```text
f45a7dbf12930ac8ef8e9db2123feda5  legal-search/frontend/public/flags/ch.svg
f45a7dbf12930ac8ef8e9db2123feda5  node_modules/circle-flags/flags/ch.svg

33d39054f5c40c9e8c404101ccbc2aa6  legal-search/frontend/public/flags/at.svg
33d39054f5c40c9e8c404101ccbc2aa6  node_modules/circle-flags/flags/at.svg
```

`circle-flags@2.8.2` is pinned in `legal-search/frontend/package-lock.json` with integrity
`sha512-FWWHTnTOjX0Ncf9ZcUIuhKb/LsnuSyxu9O4uUTE6WKauT2ewCdoaE+qLYDK/aHMY2NkDHn3bO9zvmMlMWJuJlA==`,
so the comparison above is against the upstream project's own published artifact. Licence text
reproduced from that package's `LICENSE.md`:

```text
MIT License

Copyright (c) 2026 HatScripts

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### shadcn/ui

`legal-search/frontend/src/components/ui/` holds components written into this repository by the
shadcn CLI — that is shadcn/ui's distribution model: the CLI copies component source into the
consuming project, which then owns and edits it. The registry configuration is
`legal-search/frontend/components.json` (`"$schema": "https://ui.shadcn.com/schema.json"`,
`"style": "radix-nova"`).

Twenty of the twenty-four files in that directory originate from the shadcn/ui registry and have
since been modified (in several cases heavily — `button.tsx`, for example, carries a bespoke
`ConsequenceTier` confirm-dialog wrapper that is not upstream):

`badge.tsx`, `button.tsx`, `button-variants.ts`, `checkbox.tsx`, `command.tsx`, `dialog.tsx`,
`input.tsx`, `input-group.tsx`, `popover.tsx`, `resizable-panels.tsx`, `scroll-area.tsx`,
`separator.tsx`, `sheet.tsx`, `tabs.tsx`, `textarea.tsx`, `toast.tsx`, `toaster.tsx`,
`toggle.tsx`, `toggle-group.tsx`, `tooltip.tsx`.

The remaining four — `confirm-button.tsx`, `EmptyState.tsx`, `error-state.tsx`, `ShareButton.tsx` —
are first-party components that happen to live in the same directory. They carry none of the
registry's signatures (no `data-slot` attributes, no Radix primitive re-export) and are not covered
by this notice.

Origin: [shadcn-ui/ui](https://github.com/shadcn-ui/ui). Licence text reproduced from
`node_modules/shadcn/LICENSE.md` (`shadcn@4.1.1`, whose `repository` field is
`https://github.com/shadcn-ui/ui.git`, directory `packages/shadcn` — the same monorepo the registry
is published from):

```text
MIT License

Copyright (c) 2023 shadcn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 2. Data redistributed in this repository

### Swiss municipality registry — BFS

`country-overlays/ch/municipalities.yaml` (2,110 communes) is generated by
`scripts/load_ch_gemeindeverzeichnis.py` from
`https://www.agvchapp.bfs.admin.ch/de/state/results?SnapshotDate=01.01.2026`
(`scripts/load_ch_gemeindeverzeichnis.py:104`). The generated
`jur_ch_gemeinde_*` block of
`platform-control/src/platform_control/seeds/reference/jurisdictions.yaml` derives from the same
snapshot.

Terms, established from the catalogue entry rather than assumed (fetched 2026-09-03):
opendata.swiss lists that exact resource URL — "Gemeindestand (de)" — under the dataset
[`historisiertes-gemeindeverzeichnis-der-schweiz`](https://opendata.swiss/de/dataset/historisiertes-gemeindeverzeichnis-der-schweiz),
publisher BFS/OFS, with
`license: https://opendata.swiss/terms-of-use#terms_open` on every resource.

`terms_open` is the opendata.swiss tier **"Freie Nutzung"**: non-commercial and commercial use are
both permitted, and *"eine Quellenangabe wird empfohlen (Autor, Titel und Link zum Datensatz)"* —
a source citation is **recommended, not mandatory**. It is specifically *not* the `terms_by` tier
("Freie Nutzung. Quellenangabe ist Pflicht"), under which attribution would be an obligation.

The source line is therefore recorded voluntarily, in the header of the generated file itself and
in the generator that writes it, so that it survives regeneration:

> Quelle: Bundesamt für Statistik (BFS) — Amtliches Gemeindeverzeichnis der Schweiz,
> Stand 01.01.2026. opendata.swiss: Freie Nutzung (`terms_open`).

**Not verified, and flagged rather than asserted:** BFS's general site-wide legal notice
([bfs.admin.ch … rechtliche-hinweise.html](https://www.bfs.admin.ch/bfs/de/home/bfs/bundesamt-statistik/rechtliche-hinweise.html),
fetched 2026-09-03) is more restrictive than the catalogue entry — *"Für die Reproduktion jeglicher
Elemente ist die schriftliche Zustimmung der Urheberrechtsträger im Voraus einzuholen. Grundsätzlich
ist immer die Quelle des Inhalts (der statistischen Ergebnisse) anzugeben."* Which of the two
governs a dataset published on opendata.swiss under an explicit `terms_open` declaration is a legal
question this repository does not answer. Recording the source line satisfies the stricter reading's
attribution sentence either way; the "schriftliche Zustimmung" sentence is left open, and should be
settled before the file is published outside this repository.

### Other data already reasoned about elsewhere

- `document-intelligence/tests/fixtures/zh_as_554_510.pdf` — the sole tracked PDF; an official
  Kanton Zürich enactment. Basis already recorded in the code that uses it
  (`document-intelligence/tests/test_marginalia.py:10`): Swiss official texts carry no copyright,
  Art. 5 URG (SR 231.1).
- `eval/documents.csv` — Austrian RIS metadata. The programme's required attribution string is
  already carried verbatim at
  `platform-control/src/platform_control/seeds/reference/compliance_policies.yaml:55`.

---

## 3. Same-owner vendored content

`vendor/platform-contract.yaml` is a pinned copy of `clusters/prod/platform-contract.yaml` from
[`philipplukas/MacConfig`](https://github.com/philipplukas/MacConfig), documented in `README.md`
and version-pinned by `scripts/check_platform_contract_vendor.py`. Same copyright holder, so no
third-party obligation arises.

---

## Removed rather than attributed

`legal-search/frontend/public/` used to hold five unreferenced `create-next-app` scaffold assets:
`next.svg` (the Next.js wordmark), `vercel.svg` (the Vercel logo), `file.svg`, `window.svg` and
`globe.svg`. A repository-wide search found zero references to any of them, in `src/`, `e2e/`,
configuration, or any web-app manifest or metadata. Two of them are third-party **trademarks**,
which no licence grant makes safe to redistribute, so they were deleted rather than listed here.
