# Evidara — 5-minute demo script

> A beat sheet for a ~5-minute recorded walkthrough (Loom / OBS). The goal is **not** a
> feature tour — it's to make the *judgment* behind the system visible fast, for a hiring
> manager or a design partner who'll give you five minutes. **Narrate the *why*, not the
> *what*.** Record it once; reuse it in applications and interviews.

## Before you record (2-minute checklist)

- Bring the stack up locally: `docker-compose.local.yml` boots GCP-free (see README → Getting Started). Have search + a document detail page loaded and a control-plane view ready in separate tabs.
- Have two files open to screen-share: the architecture diagram / `docs/architecture/system-context.md`, and [ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md).
- Pick **one** real query you know returns a good document (a Swiss federal law in the beta corpus).
- Mic check. One take is fine — polish is not the point; clarity is.

## The beat sheet

| Time | Show on screen | Say (the point — keep it tight) |
|---|---|---|
| **0:00–0:30** | Title slide or the README hook | "Evidara turns official legal sources into data you can *cite*. The hard part isn't search — general AI can 'search' law and hallucinate it. The hard part is **trust**: knowing where a statement came from and whether it's still in force." |
| **0:30–1:15** | Run your query → the result list | "Faceted search over a curated corpus — jurisdiction, document type, language. But the results aren't the interesting part. Watch what's *behind* one." |
| **1:15–2:30** | Open a document → the `content` / `sections` / `citations` / `details` tabs; point at provenance + `lifecycle_status` | "Every document carries its **provenance** — which authority, which jurisdiction, what trust tier — and its **in-force status**: active, superseded, repealed. And it's parsed into a **citation graph**, not a full-text blob, so you can traverse what an article points to. *This* is the product: an answer a lawyer could actually put in a brief." |
| **2:30–3:30** | Switch to the control plane / admin; show a source moving through approval | "None of that trust is automatic. Sources pass an **operator approval lifecycle** before anything publishes — quality is a gated feature, not an accident. Behind this: a canonical processing pipeline that runs *once* per document…" |
| **3:30–4:15** | Architecture diagram; trace platform-control → document-intelligence → legal-search | "…and here's the decision I'd point to. **Canonical truth is separate from the serving projection.** A document becomes canonical structure once; search is a *rebuildable view* of it, not the system of record. Reprocess or re-index anytime and citations stay stable. That's an event-driven boundary — one component emits `artifact_bundle.available`, the next emits `document.processed`." |
| **4:15–5:00** | Open ADR-0029 (scroll the audit table + target mapping) | "One more, because it shows how I make trade-offs. I moved the whole runtime off usage-billed cloud onto a fixed-cost self-hosted stack — driven by a **migration-surface audit** that proved the app was already abstracted from the cloud, so the scary migration was really one concentrated task. Built by one person, so every decision optimized for *one operator* — the lightest broker, not the most powerful one." |

## Landing it (the last 10 seconds)

Close on the honest status — it reads as confidence, not weakness:

> "It's an internal beta — about a dozen Swiss federal laws today. The corpus is thin on
> purpose; what I was proving is the *engine and the architecture*. If you want to judge
> the engineering, ADR-0029 and the boundary-contracts doc are the five-minute version."

## Do / don't

- **Do** speak to *decisions and trade-offs* — that's the senior/staff signal.
- **Do** point reviewers at the two or three artifacts worth their time. Doing their triage for them signals seniority.
- **Don't** narrate UI mechanics ("I click here, then this dropdown…"). Nobody levels you up for a working dropdown.
- **Don't** apologize for the small corpus — *frame* it ("thin on purpose, proving the engine").
- **Don't** exceed five minutes. If it won't fit, cut the control-plane beat (2:30–3:30) before cutting the architecture beat.

## Reuse

- **Applications:** link the recording next to the repo. "5-minute walkthrough" gets watched; "here's my repo" often doesn't.
- **Interviews:** when asked *"tell me about a system you designed,"* this is your answer — and you can go deeper on any beat live (the ADR is the richest thread to pull).
