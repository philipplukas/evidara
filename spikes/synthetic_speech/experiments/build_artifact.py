"""Render the results as a single self-contained HTML page.

Reads the same JSON the markdown report reads, embeds each figure as a data URI, and
writes ``results/synthetic_speech_report.html``. Nothing is hand-typed: if a number
changes in an experiment, it changes here on the next build.

Design plan (kept here so it can be argued with rather than guessed at):

  Colour    A cool instrument-panel neutral, biased slightly blue so it belongs to the
            same world as the figures. The accent is the deep step of the figures' own
            blue ramp -- the palette is a constraint inherited from the plots, not a
            free choice. Verdict colours (green / amber / red) are semantic and never
            reused as accents.
  Type      A text serif for headings and body, because this is a paper; a monospace
            for eyebrows, verdict chips and every number, because those are readings.
            System stacks only -- the artifact CSP blocks font CDNs and a linked
            webfont would fall back silently.
  Layout    One measured column at ~66ch for prose, with figures and tables breaking
            out into a wider band. The 01..09 numbering is kept because the experiments
            really are a dependency chain: detect the effect, then its rank, then its
            kernel, then invert, then the dynamics, then what is identifiable at all.
"""

from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.recording import results_dir  # noqa: E402
from experiments.build_report import EXPECTED  # noqa: E402

VERDICT_CLASS = {
    "IDENTIFIABLE": "yes",
    "PARTIALLY IDENTIFIABLE": "part",
    "NON-IDENTIFIABLE": "no",
    "MIS-SPECIFIED": "no",
    "NO EFFECT (as designed)": "flat",
    "NO EFFECT (negative result)": "flat",
    "UNEXPECTED SIGNAL": "no",
}

FIGURE_FOR = {
    "01_temporal_effect": ["temporal_effect.png", "temporal_effect_conditions.png"],
    "02_temporal_rank": ["temporal_rank.png"],
    "03_kernel_recovery": ["kernel_recovery.png"],
    "04_jacobian_recovery": ["jacobian_recovery.png"],
    "05_dynamics_identification": ["dynamics_recovery.png"],
    "06_identifiability": ["identifiability.png"],
    "07_speaker_variation": ["group_vs_groupoid.png"],
    "08_asr_comparison": ["asr_sample_efficiency.png", "asr_unseen_transition.png",
                          "asr_unseen_speaker.png"],
    "09_assumption_stress_test": ["assumption_stress_test.png"],
}

BLURB = {
    "01_temporal_effect": "Does a following phone leave a trace before it arrives?",
    "02_temporal_rank": "How many temporal degrees of freedom does that trace have?",
    "03_kernel_recovery": "What shape is the trace, and which family does it belong to?",
    "04_jacobian_recovery": "Can the articulation behind the acoustics be recovered?",
    "05_dynamics_identification": "Can the equations of motion be recovered?",
    "06_identifiability": "What is recoverable at all, and what is a choice of coordinates?",
    "07_speaker_variation": "Is one chart per speaker enough, or does the chart depend on the phone?",
    "08_asr_comparison": "Does the structure buy anything a generic model cannot get?",
    "09_assumption_stress_test": "When each assumption is wrong, how does it fail?",
}


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def compact(value, limit: int = 190) -> str:
    if value is None:
        return "—"
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return esc(text if len(text) <= limit else text[: limit - 1] + "…")


def fmt_error(f: dict) -> str:
    if f.get("error") is None:
        return "—"
    return f"{f['error']:.4g}"


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def chip(status: str) -> str:
    return f'<span class="chip {VERDICT_CLASS.get(status, "flat")}">{esc(status)}</span>'


def main() -> None:
    out_dir = results_dir()
    payloads = {}
    for name, _, _ in EXPECTED:
        path = out_dir / f"{name}.json"
        if path.exists():
            payloads[name] = json.loads(path.read_text())

    counts: dict[str, int] = {}
    for p in payloads.values():
        for f in p["findings"]:
            counts[f["status"]] = counts.get(f["status"], 0) + 1
    n_findings = sum(counts.values())

    parts: list[str] = []
    parts.append("<title>Synthetic Speech Dynamics</title>")
    parts.append(f"<style>{STYLE}</style>")

    missing = [n for n, _, _ in EXPECTED if n not in payloads]
    parts.append(f"""
<header class="hero">
  <p class="eyebrow">a controlled laboratory</p>
  <h1>Synthetic Speech Dynamics</h1>
  <p class="lede">A world where the whole generative mechanism is known — phone sequence to
  transition target to articulatory dynamics to a nonlinear acoustic map to correlated noise —
  built so that the latent variables can be hidden and then asked for back.</p>
  <p class="chain"><span>q</span><span>θ<sub>q→r</sub></span><span>𝓕<sub>t</sub></span>
     <span>u(t)</span><span>Φ</span><span>S(t) + ε</span></p>
  <dl class="tally">
    <div><dt>questions asked</dt><dd>{n_findings}</dd></div>
    <div><dt>experiments</dt><dd>{len(payloads)} of {len(EXPECTED)}</dd></div>
    <div><dt>figures</dt><dd>{len(list(out_dir.glob("*.pdf")))}</dd></div>
  </dl>
  {"<p class='warn'>Incomplete run: " + esc(", ".join(missing)) + " have not been executed.</p>" if missing else ""}
</header>
""")

    # ---- headline table ----------------------------------------------------------------
    rows = []
    for name, _, _ in EXPECTED:
        p = payloads.get(name)
        if not p:
            continue
        for f in p["findings"]:
            rows.append(
                f"<tr><td class='q'>{esc(f['question'])}</td>"
                f"<td class='num'>{esc(fmt_error(f))}</td>"
                f"<td class='lbl'>{esc(f.get('error_label', ''))}</td>"
                f"<td>{chip(f['status'])}</td></tr>"
            )
    parts.append(f"""
<section class="band">
  <h2>Every question, and its verdict</h2>
  <p class="note">Each row is a parameter the laboratory could ask for back. The verdict says
  whether the estimate matched ground truth outright, only up to an equivalence, or not at all.</p>
  <div class="scroll">
    <table class="summary">
      <thead><tr><th>Question</th><th class="num">Error</th><th>Measured as</th><th>Verdict</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
</section>
""")

    # ---- hypotheses --------------------------------------------------------------------
    parts.append(hypotheses_block(payloads))

    # ---- per experiment ----------------------------------------------------------------
    for idx, (name, topic, _) in enumerate(EXPECTED, start=1):
        p = payloads.get(name)
        if not p:
            continue
        figs = []
        for fig in FIGURE_FOR.get(name, []):
            path = out_dir / fig
            if path.exists():
                figs.append(
                    f'<figure><img alt="{esc(fig)}" src="{data_uri(path)}">'
                    f"<figcaption>{esc(fig)}</figcaption></figure>"
                )
        findings = []
        for f in p["findings"]:
            bits = [f"<p class='fq'>{esc(f['question'])} {chip(f['status'])}</p>"]
            bits.append(
                "<dl class='kv'>"
                f"<div><dt>ground truth</dt><dd>{compact(f['ground_truth'], 320)}</dd></div>"
                f"<div><dt>estimate</dt><dd>{compact(f['estimate'], 320)}</dd></div>"
                f"<div><dt>error</dt><dd><span class='num'>{esc(fmt_error(f))}</span> "
                f"<span class='lbl'>{esc(f.get('error_label', ''))}</span></dd></div>"
                + (f"<div><dt>control</dt><dd>{compact(f['control'], 320)}</dd></div>" if f.get("control") else "")
                + "</dl>"
            )
            if f.get("notes"):
                bits.append(f"<p class='fnote'>{esc(f['notes'])}</p>")
            findings.append(f"<li>{''.join(bits)}</li>")
        scalars = "".join(
            f"<div><dt>{esc(k)}</dt><dd class='num'>{compact(v, 150)}</dd></div>"
            for k, v in list(p["scalars"].items())[:8]
        )
        parts.append(f"""
<section class="exp" id="{esc(name)}">
  <p class="eyebrow">{idx:02d} · {esc(topic)}</p>
  <h2>{esc(p["title"].split("--", 1)[-1].strip())}</h2>
  <p class="blurb">{esc(BLURB.get(name, ""))}</p>
  {"<div class='figs'>" + "".join(figs) + "</div>" if figs else ""}
  {"<dl class='scalars'>" + scalars + "</dl>" if scalars else ""}
  <ol class="findings">{"".join(findings)}</ol>
</section>
""")

    parts.append("""
<footer>
  <p>Generated from <code>results/*.json</code> by <code>experiments/build_artifact.py</code>.
  The full numbers, including every sweep table, are in
  <code>results/SYNTHETIC_SPEECH_REPORT.md</code>; the code that produced them is in
  <code>spikes/synthetic_speech/</code>.</p>
</footer>
""")

    target = out_dir / "synthetic_speech_report.html"
    target.write_text("\n".join(parts))
    print(f"wrote {target} ({target.stat().st_size / 1e6:.1f} MB)")


def hypotheses_block(payloads: dict) -> str:
    def find(exp: str, needle: str) -> dict | None:
        p = payloads.get(exp)
        if not p:
            return None
        return next((f for f in p["findings"] if needle.lower() in f["question"].lower()), None)

    cards = []
    h1 = find("02_temporal_rank", "low-dimensional")
    h1b = find("02_temporal_rank", "detectable above the noise floor")
    if h1:
        cards.append((
            "Temporal variation is low-dimensional",
            h1["status"],
            (h1.get("notes") or "") + (" " + (h1b.get("notes") or "") if h1b else ""),
        ))
    h2 = find("06_identifiability", "latent coordinates themselves")
    h2b = find("06_identifiability", "IS invariant")
    if h2:
        cards.append((
            "Dynamics are identifiable only up to a change of latent coordinates",
            h2["status"],
            (h2.get("notes") or "") + (" " + (h2b.get("notes") or "") if h2b else ""),
        ))
    h3 = find("08_asr_comparison", "ABLATION")
    h3b = find("08_asr_comparison", "unseen transition")
    if h3:
        cards.append((
            "Explicit dynamics help where statistical models struggle",
            h3["status"],
            ((h3b.get("notes") if h3b else "") or "") + " " + (h3.get("notes") or ""),
        ))
    if not cards:
        return ""
    body = "".join(
        f"<article><p class='eyebrow'>hypothesis {i}</p><h3>{esc(t)}</h3>{chip(s)}"
        f"<p>{esc(n)}</p></article>"
        for i, (t, s, n) in enumerate(cards, start=1)
    )
    return f"""
<section class="band hyp">
  <h2>The three claims under test</h2>
  <div class="cards">{body}</div>
</section>
"""


STYLE = """
:root {
  --ground: #eef2f4;
  --surface: #ffffff;
  --surface-2: #f6f9fa;
  --ink: #0d1418;
  --ink-2: #4b5b65;
  --ink-3: #7d8d97;
  --rule: #d5dee3;
  --accent: #1c5cab;
  --accent-soft: #e2ecf9;
  --yes: #0d6d51;
  --part: #96620a;
  --no: #a8322c;
  --flat: #5a6a74;
  --chip-bg: #eef2f4;
  --serif: "Iowan Old Style", "Charter", "Palatino Linotype", Palatino, "Source Serif 4", Georgia, serif;
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  --measure: 66ch;
  --page: 1120px;
  --pad: clamp(1rem, 4vw, 2.5rem);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #0e1418;
    --surface: #151d23;
    --surface-2: #19232a;
    --ink: #e7eef2;
    --ink-2: #a5b4be;
    --ink-3: #77858f;
    --rule: #26323a;
    --accent: #5fa0ee;
    --accent-soft: #17293e;
    --yes: #4fbf9a;
    --part: #dda63a;
    --no: #ef7a72;
    --flat: #94a3ad;
    --chip-bg: #1c262d;
  }
}
:root[data-theme="dark"] {
  --ground: #0e1418;
  --surface: #151d23;
  --surface-2: #19232a;
  --ink: #e7eef2;
  --ink-2: #a5b4be;
  --ink-3: #77858f;
  --rule: #26323a;
  --accent: #5fa0ee;
  --accent-soft: #17293e;
  --yes: #4fbf9a;
  --part: #dda63a;
  --no: #ef7a72;
  --flat: #94a3ad;
  --chip-bg: #1c262d;
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--serif);
  font-size: 17px;
  line-height: 1.62;
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3 { line-height: 1.18; text-wrap: balance; margin: 0; font-weight: 600; }
h1 { font-size: clamp(2.1rem, 5vw, 3.1rem); letter-spacing: -0.015em; }
h2 { font-size: clamp(1.35rem, 2.6vw, 1.75rem); letter-spacing: -0.008em; }
h3 { font-size: 1.06rem; }
p { margin: 0; }
code { font-family: var(--mono); font-size: 0.86em; }

.eyebrow {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 0.86em; }
.lbl { font-family: var(--mono); font-size: 0.74rem; color: var(--ink-3); }

header.hero,
section,
footer {
  max-width: var(--page);
  margin: 0 auto;
  padding: 0 var(--pad);
}
header.hero {
  display: flex;
  flex-direction: column;
  gap: 1.05rem;
  padding-top: clamp(3rem, 8vw, 5.5rem);
  padding-bottom: 2.5rem;
}
.lede { max-width: var(--measure); color: var(--ink-2); font-size: 1.09rem; }
.chain {
  display: flex; flex-wrap: wrap; gap: 0.4rem 0.75rem;
  font-family: var(--mono); font-size: 0.78rem; color: var(--ink-2);
  padding: 0.7rem 0; border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule);
}
.chain span { display: inline-flex; align-items: center; gap: 0.75rem; }
.chain span + span::before { content: "→"; color: var(--ink-3); }
.tally { display: flex; flex-wrap: wrap; gap: 2.2rem; margin: 0.35rem 0 0; }
.tally dt { font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.12em;
            text-transform: uppercase; color: var(--ink-3); }
.tally dd { margin: 0.1rem 0 0; font-size: 1.5rem; font-variant-numeric: tabular-nums; }
.warn { color: var(--no); font-family: var(--mono); font-size: 0.8rem; }

section { padding-top: 2.6rem; padding-bottom: 2.6rem; }
section.band { background: var(--surface); border-block: 1px solid var(--rule); max-width: none; }
/* the band goes full bleed, so its children re-create the page measure themselves */
section.band > * { max-width: calc(var(--page) - 2 * var(--pad)); margin-inline: auto; }
.note, .blurb { max-width: var(--measure); color: var(--ink-2); margin-top: 0.5rem; }
.blurb { font-style: italic; }

.scroll { overflow-x: auto; margin-top: 1.4rem; }
table.summary { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
table.summary th {
  text-align: left; font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--ink-3); font-weight: 500;
  padding: 0 0.9rem 0.55rem 0; border-bottom: 1px solid var(--rule); white-space: nowrap;
}
table.summary td { padding: 0.62rem 0.9rem 0.62rem 0; border-bottom: 1px solid var(--rule);
                   vertical-align: top; }
table.summary td.q { min-width: 26rem; }
table.summary th.num, table.summary td.num { text-align: right; white-space: nowrap; }
table.summary tbody tr:hover { background: var(--surface-2); }

.chip {
  display: inline-block; font-family: var(--mono); font-size: 0.64rem; letter-spacing: 0.08em;
  text-transform: uppercase; padding: 0.18rem 0.5rem; border-radius: 2px;
  background: var(--chip-bg); color: var(--flat); border: 1px solid transparent; white-space: nowrap;
}
.chip.yes { color: var(--yes); border-color: color-mix(in oklab, var(--yes) 35%, transparent); }
.chip.part { color: var(--part); border-color: color-mix(in oklab, var(--part) 35%, transparent); }
.chip.no { color: var(--no); border-color: color-mix(in oklab, var(--no) 35%, transparent); }
.chip.flat { border-color: var(--rule); }

.hyp .cards { display: grid; gap: 1.2rem; margin-top: 1.5rem;
              grid-template-columns: repeat(auto-fit, minmax(19rem, 1fr)); }
.hyp article { background: var(--surface-2); border: 1px solid var(--rule); border-radius: 3px;
               padding: 1.2rem 1.25rem; display: flex; flex-direction: column; gap: 0.6rem; }
.hyp article p:last-child { font-size: 0.87rem; color: var(--ink-2); }
.hyp article .chip { align-self: flex-start; }

section.exp { border-top: 1px solid var(--rule); }
.figs { display: flex; flex-direction: column; gap: 1.6rem; margin-top: 1.8rem; }
figure { margin: 0; background: var(--surface); border: 1px solid var(--rule); border-radius: 3px;
         padding: 0.9rem; overflow-x: auto; }
figure img { display: block; width: 100%; max-width: 100%; height: auto; }
figcaption { font-family: var(--mono); font-size: 0.68rem; color: var(--ink-3);
             margin-top: 0.6rem; letter-spacing: 0.04em; }

dl.scalars { display: grid; gap: 0.45rem 1.6rem; margin: 1.6rem 0 0;
             grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); }
dl.scalars div { display: flex; gap: 0.7rem; justify-content: space-between;
                 border-bottom: 1px dotted var(--rule); padding-bottom: 0.35rem; }
dl.scalars dt { font-family: var(--mono); font-size: 0.72rem; color: var(--ink-3); }
dl.scalars dd { margin: 0; text-align: right; word-break: break-word; }

ol.findings { list-style: none; margin: 1.8rem 0 0; padding: 0;
              display: flex; flex-direction: column; gap: 1.5rem; }
ol.findings > li { border-left: 2px solid var(--accent-soft); padding-left: 1.1rem; }
.fq { font-weight: 600; display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: baseline; }
dl.kv { margin: 0.7rem 0 0; display: flex; flex-direction: column; gap: 0.3rem; }
dl.kv div { display: grid; grid-template-columns: 8.5rem 1fr; gap: 0.9rem; align-items: baseline; }
dl.kv dt { font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.08em;
           text-transform: uppercase; color: var(--ink-3); }
dl.kv dd { margin: 0; font-size: 0.9rem; word-break: break-word; }
.fnote { margin-top: 0.7rem; font-size: 0.9rem; color: var(--ink-2); max-width: var(--measure); }

footer { border-top: 1px solid var(--rule); padding-top: 2rem; padding-bottom: 3.5rem;
         color: var(--ink-3); font-size: 0.86rem; }
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (max-width: 640px) {
  dl.kv div { grid-template-columns: 1fr; gap: 0.15rem; }
  table.summary td.q { min-width: 18rem; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
"""


if __name__ == "__main__":
    main()
