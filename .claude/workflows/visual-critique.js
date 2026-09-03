// Visual critique — read the committed visual baselines as images and critique what they actually
// show, against an explicit rubric, with every finding cross-checked against the source.
//
// ── WHY THIS IS NOT AN OPINION GENERATOR ─────────────────────────────────────
// Design review is the one place the "evidence or silence" rule needs a different anchor, because
// an agent reading source cannot see the product. So this workflow never reads source to form an
// aesthetic view. Its evidence is the RENDERED OUTPUT already committed to the repo:
// legal-search/frontend/e2e/visual.spec.ts-snapshots/ holds ~19 PNGs — workspace, filter panel,
// detail panel and sheet, multi-result, and — the valuable ones — empty-state and error-state, at
// desktop and mobile widths, plus two admin views. Every finding must name an image and a region
// in it, and every finding that makes a claim about a token, a string or a component must be
// cross-checked in the source before it is reported.
//
// ── THE DEFECT CLASS IT EXISTS FOR ───────────────────────────────────────────
// A baseline is an assertion about what the product looks like, and nothing checks whether that
// assertion is any good. The repo's own ledger records three occasions where a baseline captured a
// live bug and shipped it as the definition of correct — a filter rail ~260px too narrow for ~3.5
// months, a retired brand tile for ~3 months, a wrong filter badge blessed five minutes after the
// fix landed (visual.spec.ts-snapshots/PROVENANCE.md). None failed CI, because a
// maxDiffPixelRatio of 0.06 licensed ~86,000 pixels of drift on a 1600x900 shot.
//
// The tolerance is gone and the provenance ledger now gates changes to these files. But both check
// that a baseline is STABLE and ACCOUNTED FOR. Neither checks that it is RIGHT. A hand-written
// critique of these same images (legal-search/frontend/docs/visual-snapshot-critique.md) found a
// results region rendering twice at two different sizes — a real bug, sitting in a green baseline.
// That is this workflow's job, done repeatably.
//
// ── WHAT IT CANNOT SEE, AND WILL SAY SO ──────────────────────────────────────
// A static PNG cannot show focus rings, keyboard reachability, hover and transition states, or
// screen-reader output. It also cannot show theme parity: the committed baselines are suffixed by
// PLATFORM (-linux / -darwin), not by theme, so there is no dark-mode baseline to critique. Those
// are reported as NOT ASSESSABLE, never guessed. Closing that gap needs captures from a running
// app — see README.md.
//
// Reads images and source. Never captures, never runs the app, never writes a baseline.

export const meta = {
  name: 'visual-critique',
  description:
    'Critique the committed visual baselines as images against an explicit rubric, cross-checking every claim against source — a green baseline is not a correct one',
  whenToUse:
    'When you want a design/UX read that is anchored in rendered output rather than in source. Not a replacement for capturing new routes; it can only see what is committed.',
  phases: [
    { title: 'Census', detail: 'inventory the baselines, their provenance and the token set' },
    { title: 'Critique', detail: 'one agent per image group, reading the PNGs against the rubric' },
    { title: 'Verify', detail: 'an independent agent checks each claim against the image and the source' },
    { title: 'Report', detail: 'ranked findings plus an explicit list of what a PNG cannot show' },
  ],
}

const A = args || {}
const ROOT = A.snapshotDir || 'legal-search/frontend/e2e/visual.spec.ts-snapshots'
// Image groups. Default 4 keeps a full run at 10 agents.
const GROUPS = Math.max(1, Math.min(6, A.groups || 4))
const TOP_N = A.topN || 8

const HOUSE = `
GROUND RULES (.claude/workflows/_house-rules.md), adapted for a visual review:

1. THE IMAGE IS THE EVIDENCE. Every finding names the PNG file and the region of it you are talking
   about ("the utility pill at top right", "the results container, second block"). A finding you
   cannot point at in an image is not a finding here. Use the Read tool on the .png path — it
   renders the image for you. If you cannot actually see an image, say so; do not reason about it
   from its filename.

2. CROSS-CHECK EVERY SOURCE CLAIM. If you say a colour should be a token, name the token and its
   value from styles/tokens/tokens.css or the surface's globals.css, and name the file:line where
   the hardcoded value is used. If you say a string is wrong, quote it from the source. If you say
   a component renders twice, find the component. An image tells you WHAT; only the source tells
   you WHY, and a critique without the why is not actionable.

3. NO TASTE-ONLY FINDINGS. "Feels cramped", "could be more modern", "consider a different
   typeface" are dropped. A finding must be one of:
     - a VIOLATION of a stated rule (a hardcoded colour where AGENTS.md requires var(--token); a
       contrast ratio below WCAG AA, with the two hex values and the computed ratio);
     - a DEFECT visible in the render (duplicated region, clipped text, overlapping elements,
       misaligned rail, wrong or placeholder content, a state that renders as if it were another
       state);
     - a STATE GAP (a state the product can reach that no baseline covers);
     - an INCONSISTENCY between two images that should agree (the same component at two widths, or
       the workspace surface versus the admin surface).
   Everything else is an opinion. Opinions are worse than an empty report.

4. SAY WHAT YOU CANNOT SEE. A static PNG cannot show focus rings, keyboard reachability, hover,
   transitions, screen-reader output, or dark mode (the committed baselines are suffixed by
   PLATFORM, -linux / -darwin, not by theme). Never infer any of these from an image. Put them in
   NOT ASSESSABLE.

5. A BASELINE CAN BE WRONG. These images are assertions, not ground truth, and this repo has
   shipped bugs inside green baselines three times (see the PROVENANCE.md ledger). Treat every
   image as a claim to be checked, not as the definition of correct.

6. READ-ONLY. Never write, update or delete a baseline. Never run the app, the Playwright suite, or
   any capture script. Never contact a public-sector host. Never merge a PR, push, delete a branch,
   comment on a PR, or open a PR — this report is returned to the caller and a human acts on it.
`

const RUBRIC = `
RUBRIC — apply every dimension to every image you are given, and say which you could not apply.

R1 TOKEN CONFORMANCE. AGENTS.md: design tokens live in globals.css as CSS custom properties, "use
   var(--token) everywhere, never hardcoded colors", and the review guidance flags hardcoded
   tokens. From the image, identify the distinct colours in use. Then in source, find where each is
   set. Report: a colour set as a literal where a token exists (fix: use the token); a colour with
   NO token (fix: add one, or a finding about the token set); two visually identical colours coming
   from different definitions. Shared tokens: styles/tokens/tokens.css. Surface-local:
   legal-search/frontend/src/app/globals.css, platform-control/admin/src/app/globals.css,
   marketing/src/app/globals.css (ADR-0027: two products, shared brand).

R2 RENDER DEFECTS. Look at the pixels, not at the intent. Duplicated regions; text clipped or
   overflowing; overlapping or colliding elements; a rail, column or gutter that is visibly the
   wrong width; placeholder or lorem content; a control rendered in a state that contradicts its
   label; an image or icon that failed to load. The hand-written critique of these same baselines
   found a results block rendering TWICE at two different sizes — look for that class of thing.

R3 HIERARCHY. Is the most important thing on the screen the most prominent thing? Name the element
   you believe should lead and the element that actually does, and point at both in the image. Then
   check whether a control and an informational label have their weights swapped. State it as an
   observation about the image, not as a preference.

R4 STATE COVERAGE. Which states does this surface have baselines for — populated, empty, error,
   loading, very long content, many results, one result? Compare the file list against the states
   the components can actually reach (check the source for the branches that render). A reachable
   state with no baseline is a STATE GAP finding, and it is one of the most valuable outputs here,
   because an uncovered state is where visual bugs live.

R5 CONTRAST. For every text/background pair you can identify, get both colour values FROM SOURCE
   (the token definitions), compute the WCAG contrast ratio, and compare against AA (4.5:1 for body
   text, 3:1 for large text and UI boundaries). Report the two hex values and the computed ratio.
   Do not eyeball a ratio and do not report one you did not compute. Secondary metadata on the warm
   canvas has been flagged before as sitting near the AA boundary — compute it, do not repeat it.

R6 CROSS-SURFACE CONSISTENCY. Compare the same component across widths (desktop vs mobile) and the
   user-facing workspace against the admin control plane. A deliberate split is fine — ADR-0027
   makes one — but an UNDOCUMENTED divergence is a finding. Check ADR-0027 before calling it drift.

R7 BASELINE HEALTH. Is this baseline current? Read
   legal-search/frontend/e2e/visual.spec.ts-snapshots/PROVENANCE.md for its ledger entry, and check whether the
   component it shows still exists in source with the same shape. A baseline showing a component
   that has since been replaced is a finding about the baseline, not about the design.
`

const CRITIQUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['images_read', 'findings', 'not_assessable'],
  properties: {
    images_read: {
      type: 'array',
      description: 'The PNG paths you actually opened and saw. If you could not see one, do not list it.',
      items: { type: 'string' },
    },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['rubric', 'title', 'image', 'region', 'source_anchor', 'blast_radius'],
        properties: {
          rubric: { type: 'string', enum: ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7'] },
          title: { type: 'string' },
          image: { type: 'string', description: 'The PNG path.' },
          region: { type: 'string', description: 'Where in the image. Required.' },
          source_anchor: {
            type: 'string',
            description: 'file:line in source that explains or causes it, or NONE if you could not find it.',
          },
          measurement: { type: 'string', description: 'For R5: both hex values and the computed ratio.' },
          blast_radius: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low'] },
          fix: { type: 'string' },
        },
      },
    },
    not_assessable: {
      type: 'array',
      description: 'Rubric dimensions you could not apply, and why. Required — this is half the value.',
      items: { type: 'string' },
    },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'image', 'region', 'refuted', 'reason'],
        properties: {
          title: { type: 'string' },
          image: { type: 'string', description: "Echo the finding's image path VERBATIM — verdicts are matched back on image+region." },
          region: { type: 'string', description: "Echo the finding's region VERBATIM." },
          refuted: { type: 'boolean' },
          reason: { type: 'string' },
          corrected_source_anchor: { type: 'string' },
          severity_after_check: { type: 'string', enum: ['ship-blocker', 'high', 'medium', 'low', 'none'] },
        },
      },
    },
  },
}

const SEVERITY = ['ship-blocker', 'high', 'medium', 'low', 'none']
// Sort key for blast radius. `indexOf` returns -1 for a missing or unrecognised value, which
// would sort an unlabelled finding ABOVE a ship-blocker; 99 puts it last instead.
const rank = (s) => (SEVERITY.indexOf(s) + 1 || 99)

// ── run ──────────────────────────────────────────────────────────────────────
phase('Census')

const census = await agent(
  `${HOUSE}

Take a census. Do NOT critique anything yet.

1. List every image under ${ROOT} with its size in pixels (\`file\` or \`identify\` if available, else
   read the header). Group them by what they show and by width — the suffixes -linux / -darwin are
   PLATFORM, not theme, so a -linux and a -darwin of the same view are the same design at two
   renderers, not light and dark.
2. Read ${ROOT}/PROVENANCE.md. Summarise the ledger: which baselines have entries, when each was
   last regenerated and why. Flag any PNG with no ledger entry, and any entry whose stated reason
   no longer matches what the source does.
3. Run \`python scripts/check_visual_baseline_provenance.py\` (read-only) and report its real output.
   If it fails, say so — it means the ledger and the images already disagree, and every critique
   below is about images of unknown provenance.
4. Locate the token definitions: styles/tokens/tokens.css, styles/tokens/tokens.ts, and each
   surface's globals.css. List the colour tokens with their values. The critique agents will need
   this to check R1 and to compute R5, so be complete about colours and skip everything else.
5. List the states the frontend can actually render (empty, error, loading, no-results, long
   content, many results, ...) by reading the source branches, not by guessing. This is the
   reference for R4's state-gap check.
6. Split the images into exactly ${GROUPS} balanced groups, keeping views that should be compared
   with each other (same view at two widths; workspace vs admin) in the SAME group, because R6 needs
   both in one agent's hands.

Return ONLY a JSON object:
  {"groups": [["<png path>", ...], ...], "tokens": "<colour tokens and values>",
   "provenance": "<summary + the check script's real output>", "states": ["..."]}
with exactly ${GROUPS} groups.`,
  { label: 'baseline census' },
)

let cen = null
try {
  const m = String(census).match(/\{[\s\S]*\}/)
  cen = m ? JSON.parse(m[0]) : null
} catch (e) {
  cen = null
}
if (!cen || !Array.isArray(cen.groups) || cen.groups.length === 0) {
  log('⚠ could not parse the census — aborting rather than critiquing images blind')
  return `Baseline census could not be parsed, so no critique was performed. Raw census follows.\n\n${census}`
}
// Cap: GROUPS is asked for in the prompt, not enforced by it.
const groups = cen.groups.filter((g) => g && g.length).slice(0, GROUPS)
if (cen.groups.length > groups.length) {
  log(`⚠ census returned ${cen.groups.length} groups; capped to ${GROUPS}. Those images were NOT critiqued.`)
}
log(`${groups.length} image group(s); ~${groups.length * 2 + 2} agents`)

const results = await pipeline(
  groups,

  (group, _o, idx) =>
    agent(
      `${HOUSE}

Critique image group ${idx + 1} of ${groups.length}:
${JSON.stringify(group, null, 2)}

OPEN EVERY ONE OF THESE with the Read tool — they are PNGs and Read renders them. List in
\`images_read\` only the ones you actually saw. If a Read fails, say so and do not critique that
image from its name.

TOKENS (from the census — verify any value you rely on by opening the file yourself):
${cen.tokens || '(none reported — read styles/tokens/tokens.css yourself)'}

BASELINE PROVENANCE:
${cen.provenance || '(none reported — read PROVENANCE.md yourself)'}

STATES THE PRODUCT CAN REACH (for R4):
${JSON.stringify(cen.states || [], null, 2)}

${RUBRIC}

Return at most 6 findings, ranked by blast radius, and fill \`not_assessable\` honestly — a reader
needs to know that focus visibility, keyboard reachability, hover states and dark mode were NOT
checked, because a report that is silent about them reads as if they were fine.`,
      { phase: 'Critique', label: `critique group ${idx + 1}`, schema: CRITIQUE_SCHEMA },
    ),

  async (crit, group, idx) => {
    if (!crit || !crit.findings || crit.findings.length === 0) {
      return { survivors: [], killed: 0, not_assessable: (crit && crit.not_assessable) || [], images: (crit && crit.images_read) || [] }
    }
    const panel = await agent(
      `${HOUSE}

You are the verifier for image group ${idx + 1}. YOUR JOB IS TO KILL THESE CLAIMS.

${JSON.stringify(crit.findings, null, 2)}

For each:
  - OPEN THE IMAGE YOURSELF and look at the named region. Is the thing described actually visible?
    A critique agent that has not really looked produces confident descriptions of things that are
    not there — that is the dominant failure mode here, and it is what you are for.
  - Open the source anchor. Does it say what is claimed? Is the line current?
  - R1: does the "hardcoded" colour actually appear as a literal in source, and does a token for it
    exist? Quote both. A colour with no token is a different, lesser finding than a colour that
    ignores one.
  - R5: RECOMPUTE the contrast ratio from the two hex values yourself. A wrong ratio is a wrong
    finding. Check whether the pair is body text (4.5:1) or large text / UI boundary (3:1) before
    calling it a failure.
  - R4: is the "missing" state really unreachable in a baseline, or is it covered by a differently
    named file, or by a unit test rather than a screenshot?
  - R6: is the divergence documented? ADR-0027 deliberately makes the workspace and the admin
    control plane two visual languages under one brand. A divergence that ADR covers is not drift.
  - Kill anything that is taste: if the finding reduces to a preference once you look, refute it.

refuted = true unless you personally saw it in the image AND confirmed it in source. DEFAULT TO
refuted = true WHEN UNCERTAIN.

Return ONE verdict per finding, and echo each finding's \`image\` and \`region\` VERBATIM — the
verdicts are matched back on those two fields, and a paraphrase leaves the finding unverified.`,
      { phase: 'Verify', label: `verify group ${idx + 1}`, schema: VERIFY_SCHEMA },
    )
    const verdicts = (panel && panel.verdicts) || []
    const survivors = []
    let killed = 0
    crit.findings.forEach((f) => {
      // Match on image+region first: a verifier that paraphrases the title would otherwise leave
      // every finding UNVERIFIED. Title is the fallback.
      const v =
        verdicts.find((x) => x.image === f.image && x.region === f.region) ||
        verdicts.find((x) => x.title === f.title)
      if (!v) {
        survivors.push({ ...f, status: 'UNVERIFIED — no verifier verdict' })
        return
      }
      if (v.refuted) {
        killed++
        return
      }
      survivors.push({
        ...f,
        status: 'SURVIVED',
        blast_radius: v.severity_after_check && v.severity_after_check !== 'none' ? v.severity_after_check : f.blast_radius,
        source_anchor: v.corrected_source_anchor || f.source_anchor,
        verifier_note: v.reason,
      })
    })
    log(`group ${idx + 1}: ${survivors.length} survived, ${killed} refuted`)
    return { survivors, killed, not_assessable: crit.not_assessable || [], images: crit.images_read || [] }
  },
)

const ok = results.filter(Boolean)
const lost = groups.length - ok.length
if (lost > 0) log(`⚠ ${lost} image group(s) produced nothing — those images were NOT critiqued`)

const all = ok.flatMap((r) => r.survivors)
all.sort((a, b) => rank(a.blast_radius) - rank(b.blast_radius))
const top = all.slice(0, TOP_N)
if (all.length > top.length) log(`capped at ${TOP_N}: dropped ${all.length - top.length} lower-blast-radius survivors`)

const seen = ok.flatMap((r) => r.images)
const gaps = Array.from(new Set(ok.flatMap((r) => r.not_assessable)))

phase('Report')
const report = await agent(
  `${HOUSE}

Write the visual critique report.

SURVIVING FINDINGS (each already re-checked against the image and the source by an independent
verifier; ${all.length} survived, ${ok.reduce((n, r) => n + r.killed, 0)} refuted):
${JSON.stringify(top, null, 2)}

IMAGES ACTUALLY OPENED AND SEEN (${seen.length}):
${JSON.stringify(seen, null, 2)}

NOT ASSESSABLE, as reported by the critique agents:
${JSON.stringify(gaps, null, 2)}

BASELINE PROVENANCE:
${cen.provenance || '(not established)'}

IMAGE GROUPS THAT PRODUCED NOTHING: ${lost}

Write exactly this and nothing else:

1. HEADLINE — one line: N baselines read, M findings, and whether the provenance check passed. If
   the provenance check failed, that goes FIRST — a critique of images whose provenance is unknown
   is a critique of an unknown product.

2. FINDINGS — numbered, worst first, at most ${TOP_N}. Each in five lines:
     WHAT:   <one sentence>
     WHERE:  <png file> — <region>
     SOURCE: <file:line> (or NONE — could not locate)
     WHY:    <the rule violated, the defect visible, the state uncovered, or the inconsistency>
     FIX:    <the narrowest change>
   For contrast findings, include both hex values and the computed ratio on the WHY line.

3. STATE GAPS — states the product can reach that no baseline covers, as a plain list. This is the
   section that prevents the next bug from shipping inside a green baseline.

4. NOT ASSESSABLE FROM A STATIC PNG — focus rings, keyboard reachability, hover and transition
   states, screen-reader output, and dark mode (the committed baselines are per-PLATFORM, not
   per-theme, so no dark baseline exists to critique). State plainly that this report says NOTHING
   about these, and that closing the gap needs captures from a running app.

5. NOT CRITIQUED — image groups that produced nothing, images no agent could open.

Terse. No preamble, no emoji, no praise for the design. Every finding names an image and a region.
Do not update or delete any baseline, do not run a capture, do not open a PR.`,
  { label: 'visual critique report' },
)

return report
