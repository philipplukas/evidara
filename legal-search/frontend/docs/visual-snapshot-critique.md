# Visual Snapshot & Screenshot-Pack Critique

Scope: `legal-search/frontend/e2e/visual.spec.ts-snapshots/` (4 Playwright baselines) and `legal-search/frontend/screenshot-pack/` (5 showcase PNGs + brand design SVGs).

Read top-to-bottom: brand impression → structural critique → per-surface notes → bugs & follow-ups.

---

## 1. Overall aesthetic impression

Evidara is presenting an unusually warm, editorial take on a legal-research tool. The canvas is a soft cream (`≈ #FBF6EC`), not the white or cool grey most competitors (Westlaw, Lexis+, Manz, Swisslex) default to. The identity is carried by a navy primary (`#0F4C81`-range) and a saturated violet (`#6246D9`) as the sole interactive accent. Serif headings (Source Serif 4) sit on top of Inter body — a mature, publishing-adjacent pairing that signals "read carefully, not dashboard-scan".

What this does well:

- **Tonal differentiation.** Against Westlaw's clinical blue/white, Evidara reads as a *workspace* you'd want to spend time in, not a database you're punished to use.
- **Clear interactive model.** Exactly one accent color (violet) for actionable state — search button, active tabs, focus ring. A user never has to ask "what can I click?"
- **Domain cues without theming.** The Swiss-flag cross inside the `COURT DECISION` badge is a small, precise signifier. It avoids the trap of wrapping the whole UI in red/white.

What it risks:

- **Two visual languages.** The user-facing workspace is warm, editorial, and spacious. The `admin-*-v2` control plane is cool, information-dense, and Retool-flavored. Consistent enough to feel same-company, different enough to read as two products. Deliberate split is fine — **document it**, otherwise it looks like drift.
- **Warm cream + pale grey secondary text.** Secondary metadata ("Date", "Docket", "Court:") sits right at the edge of WCAG AA on a cream background. Flag for an accessibility pass.
- **Playful mark vs. serious domain.** Current lockup is a plain "E" avatar tile. The brand playbook (`screenshot-pack/design/brand-decision-playbook.md`) flags that direction isn't locked yet. Until the mark lands, the app header reads "placeholder" rather than "brand".

---

## 2. Information architecture & layout patterns

### The header is a two-card lockup

Both mobile and desktop repeat the same pattern: a branded pill ("E Evidara") on the left, and a utility pill on the right carrying `PROFIL: OPERATOR`, language switch `DE | FR`, and an avatar.

Evaluation:

- **Desktop (1600w):** The two cards read as "workspace chrome" — there's enough whitespace that they float cleanly. Good.
- **Mobile (430w):** The same two cards eat ~14% of vertical space before the user sees anything actionable. The right card crams role-label + language + avatar + (dark-mode toggle + share link in the expanded state) into one container. This is the single most crowded zone in the mobile view.

Recommendations:

1. Keep the left brand card stable. On mobile, collapse the right card to just the avatar and tuck role + language inside a sheet behind the avatar.
2. The `PROFIL: OPERATOR` chip is valuable — it tells power users the app knows they're an operator — but it's more of a status marker than a header ornament. Consider moving it into a persistent "mode ribbon" under the header on admin routes only.

### Search bar is the real hero

Across every user-facing snapshot the search bar is the visual anchor: oversized, centered, with a violet `Suchen` button. This is correct for this product — search *is* the interface, and the hierarchy honors that.

Nits:

- On mobile, the search-input chevron/clear/submit cluster on the right is three interactive targets packed into ~90px. At thumb size they're reachable but spatially ambiguous — consider 4px more gap between clear `×` and the violet submit.
- The search placeholder row on desktop has no visible label; screen readers will rely on accessible name. Confirm `aria-label="Suche"` or similar is set.

### Filter + tool row below the search bar

`Filter · Verlauf · Merkliste · Kontrollbereich` on desktop; `Filter · Verlauf · Merkliste · [toggle]` on mobile. Clean, iconographic, consistent. One oddity: on desktop these read as pill *chips* (tertiary), but `Kontrollbereich` renders as a near-active tab. If "Kontrollbereich" is a mode switch, lift it out — it doesn't belong in a chip row with history and pins.

### Results region

The results container (`AUSGANGSSUCHE` badge + `Results for "…"` title + result cards) uses a subtle border and cream-tinted background against the slightly darker canvas. The inverted warmth is a nice trick — the results literally look like a piece of paper on a desk.

A real issue lives here, however → see §4.

---

## 3. Per-surface notes

### `workspace-desktop-linux.png` (1600×900)

- Strong horizontal rhythm: header · search · toolbar · results. Vertical whitespace between sections is generous.
- **Bug:** the `AUSGANGSSUCHE · Results for "Art. 754 OR Verantwortlichkeit"` block renders twice, stacked, at two different sizes. Either the component is mounting twice (state/reducer bug) or the baseline was captured mid-regression and got committed. This is the top item in §5.
- "1 result · Search for 'Art. 754 OR Verantwortlichkeit'" is quieter than the sort pill ("NACH RELEVANZ SORTIERT"). Swap weights — the result count is informational and the sort is a control.
- A single result card is well-composed: domain chips (`OBLIGATIONENRECHT · GESELLSCHAFTSRECHT`), serif headline, court line, body, footnote row (Date · Docket · Court), action row. Good editorial rhythm.

### `workspace-mobile-linux.png` (430×932)

- Overall: holds together well at this width. Serif title, paragraph body, meta, actions — all breathable.
- The filter bar collapses to a single `Filter 2` chip + an `Alles zurücksetzen` link centered below. On desktop that reset link is right-aligned and tertiary; on mobile it's a center-aligned link block. **Inconsistency**: same action, two different visual roles. Pick one.
- Actions row (`Anheften`, `Open decision`) uses secondary pill styling side-by-side. With more actions (Pin, Share, Open, Cite), this row will grow into a scroll tray. Budget for that now.
- Dark-mode toggle appears only in the mobile profile card (in the expanded state visible in `screenshot-pack/mobile-search-home.png`), not desktop. If the toggle exists, it should exist everywhere.

### `app-header-linux.png`

- Works well isolated. The empty middle region reads as "space is the brand" rather than "unused space" — this is where a breadcrumb or current-corpus indicator could live later without breaking the composition.

### `results-control-region-linux.png` (rich facets)

- `CSV EXPORTIEREN` is introduced as a secondary pill. Reasonable placement.
- `NACH RELEVANZ SORTIERT` is styled identically to `CSV EXPORTIEREN`, but semantically one is a *state control* (sort order) and the other is an *action*. They should look subtly different — e.g. sort = filled chip with caret, export = ghost with icon.

### `screenshot-pack/mobile-detail-sheet.png`

- Best composition in the set. Breadcrumb `Schweiz › Bundesgericht › decision-1` sets context immediately. Title uses serif + line break in the right place. Metadata table is scannable. Tabs (`Details · Related 1 · References 1`) show counts inline — excellent.
- Violet focus ring on the close button is visible and clearly keyboard-origin. Good accessibility signal.
- "1 weitere Felder anzeigen" disclosure: label wording is off (German grammar — should be "Ein weiteres Feld anzeigen" if `count=1`, "N weitere Felder anzeigen" if `count>1`). Pluralization bug likely hiding in an i18n string.

### `screenshot-pack/admin-runs-list-v2.png` & `admin-run-detail-v2.png`

- Enterprise-operator aesthetic: compact left nav, table with sortable headers, state pills, timestamps. Consistent with Retool/Linear admin patterns. Reads competent.
- The run detail is a *wall* of equally-weighted cards ("Decision support", "Pipeline health", individual stage sections). Four quadrant cards on "Decision support" with identical weight means the user's eye has no entry point. Consider: one lead question (largest, left), three supporting answers (smaller, right) — or collapse three of the four behind a disclosure on first load.
- The orange "Open attention run · Swiss Federal Court" CTA in the runs list is the only warm-accent element in an otherwise cool admin palette. It works as an alert color — keep it reserved for that meaning.

### `screenshot-pack/design/*` (brand exploration)

Not rendered surfaces but worth one note: per `brand-decision-playbook.md` there are 27 design artifacts, 5 exploration SVGs, and no locked decision. Everything above is evaluated against *the current shipped system*, which per `tokens.css` is already mature (navy / violet / Inter / Source Serif 4). Don't let open brand exploration mask that the product UI is further along than the brand.

---

## 4. Typography, color, spacing — measured observations

| Dimension | What's there | Comment |
|---|---|---|
| Primary font | Inter (UI), Source Serif 4 (headings) | Excellent pairing for a read-heavy domain. |
| Hierarchy levels | Display serif → Section sans bold → Body sans → Meta uppercase tracked | 4 levels is enough. Do not add a 5th. |
| Primary color | Navy `~#0F4C81` | Good identity anchor. Conservative but not sterile. |
| Accent / interactive | Violet `#6246D9` | Used exclusively for "clickable primary". Strong rule, keep it. |
| Canvas | Cream `~#FBF6EC` | Differentiator. Test on OLED/mobile in sunlight. |
| Secondary text | Warm grey on cream | Check AA ratio, likely 4.2–4.4 at meta size. Add 5–10% darkness on labels like "Date", "Docket", "Court:". |
| Radius | ~12px on cards, ~20px on pills | Consistent and "soft workspace" — matches the warm palette. |
| Focus ring | Violet 2px outline with offset | Visible, WCAG-friendly. Good. |
| Iconography | Lucide-style 1.5px strokes | Consistent. |

---

## 5. Bugs, regressions, and open questions

1. **Duplicate header block** in `workspace-desktop-linux.png` — the `AUSGANGSSUCHE Results for "Art. 754 OR Verantwortlichkeit"` block renders twice at two different sizes. This baseline needs a diff check against the previous commit; either fix the component and re-baseline, or revert the baseline commit.
2. **Reset-link inconsistency** — `Alles zurücksetzen` is a right-aligned tertiary link on desktop but a center-aligned button on mobile. Pick one affordance.
3. **Sort vs. export look identical** in the results control region. Differentiate control vs. action.
4. **German pluralization** in `"1 weitere Felder anzeigen"` — wrong plural.
5. **Dark-mode toggle surfaces only on mobile** per the screenshot-pack capture. If it exists, put it in a single global place (profile menu).
6. **Admin vs. workspace look drift** — palette is shared but density, card treatment, and accent usage diverge. Decide: is the control plane a *mode* of the same product, or a *separate product*? Design language should follow that decision.
7. **Baseline coverage is thin.** Four visual baselines cover: full desktop, full mobile, header, results region. Missing: empty state, error state, detail sheet, filter panel open, multi-result page. If Playwright visual regressions are a real gate, expand the matrix.
8. **Mobile header density.** The right-side profile card holds role + language + avatar + toggles. Split or collapse for <480px.

---

## 6. Concrete next steps (ranked)

1. Fix the duplicated results-header block and re-baseline `workspace-desktop-linux.png`.
2. Accessibility pass on secondary text contrast on the cream canvas.
3. Unify `Alles zurücksetzen` styling across breakpoints.
4. Differentiate sort controls from export/action pills in the results toolbar.
5. Expand the Playwright visual matrix to cover detail sheet, empty/error states, filter panel open.
6. Write a one-page design doc declaring the relationship between `workspace` and `admin` surfaces so the two languages don't drift further.
7. Park brand-mark exploration until positioning is locked (per `brand-decision-playbook.md` Stage 1) — don't ship new chrome on a placeholder mark.

---

## 7. What I'd keep exactly as-is

- Cream canvas + navy + violet palette. This is the differentiator; don't dilute it.
- Serif headings + Inter body for long-form legal content.
- Single-accent interactive rule.
- Swiss-flag cross badge on `COURT DECISION`. Small, precise, on-brand.
- Breadcrumb + serif title + metadata table pattern in the detail sheet — the best-composed surface in the pack.

---

*Source snapshots reviewed:*

- `e2e/visual.spec.ts-snapshots/{workspace-desktop,workspace-mobile,app-header,results-control-region}-linux.png`
- `screenshot-pack/{mobile-search-home,mobile-result-list,mobile-detail-sheet,admin-runs-list-v2,admin-run-detail-v2}.png`
- `screenshot-pack/design/brand-decision-playbook.md`
