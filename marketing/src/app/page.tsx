import { BrandMark, RepositoryLink } from "@evidara/shell";
import { WaitlistForm } from "@/components/WaitlistForm";
import { CAPABILITIES, HERO, NOT_YET, THESIS, WAITLIST } from "@/lib/content";

/**
 * The Evidara waitlist page.
 *
 * ── On the absence of a demo link ──
 *
 * There is intentionally no "try it" link anywhere on this page. Search has
 * unmerged correctness fixes (#672, #673, #675) and there is no end-user
 * authentication anywhere in the system — both existing UIs sit behind a
 * single shared BasicAuth password. Sending a stranger to a legal-search tool
 * that silently narrows their results is not a demo, it is a liability.
 * Design-partner and pilot flows come later, gated on ADR-0038 (#676).
 *
 * ── Heading hierarchy ──
 *
 * One <h1> (the hero), <h2> per section, <h3> per card. Nothing skips a
 * level; the visual scale is set independently of the tag so the outline
 * stays navigable.
 */
export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 sm:px-8">
      <header className="flex items-center justify-between py-8">
        <span className="flex items-center gap-3 text-[var(--brand)]">
          <BrandMark size={32} />
          <span className="font-[family-name:var(--font-serif-display)] text-[var(--text-xl)] font-[var(--font-weight-semibold)] text-[var(--foreground)]">
            Evidara
          </span>
        </span>
      </header>

      <main id="main-content" className="flex flex-col gap-[var(--marketing-section-gap)] pb-24">
        {/* ── Hero ─────────────────────────────────────────────── */}
        <section className="grid items-start gap-12 pt-8 lg:grid-cols-[1.15fr_1fr] lg:gap-16 lg:pt-16">
          <div className="flex flex-col gap-6">
            <p className="font-[var(--font-weight-medium)] text-[var(--accent-core)] text-sm tracking-wide uppercase">
              {HERO.eyebrow}
            </p>
            <h1 className="max-w-[18ch] font-[family-name:var(--font-serif-display)] text-4xl leading-tight font-[var(--font-weight-semibold)] text-balance text-[var(--foreground)] sm:text-5xl">
              {HERO.headline}
            </h1>
            <p className="max-w-[var(--marketing-measure)] text-lg leading-relaxed text-[var(--foreground-muted)]">
              {HERO.subhead}
            </p>
          </div>

          <div className="rounded-[var(--marketing-radius-panel)] border border-[var(--border)] bg-[var(--surface-panel)] p-6 shadow-[var(--shadow-panel)] sm:p-8">
            <h2 className="font-[family-name:var(--font-serif-display)] text-2xl font-[var(--font-weight-semibold)] text-[var(--foreground)]">
              {WAITLIST.heading}
            </h2>
            <p className="mt-3 mb-6 text-[var(--foreground-muted)] leading-relaxed">
              {WAITLIST.body}
            </p>
            <WaitlistForm />
          </div>
        </section>

        {/* ── What it does today ───────────────────────────────── */}
        <section className="flex flex-col gap-8">
          <div className="flex flex-col gap-3">
            <h2 className="font-[family-name:var(--font-serif-display)] text-3xl font-[var(--font-weight-semibold)] text-[var(--foreground)]">
              What the platform does today
            </h2>
            <p className="max-w-[var(--marketing-measure)] text-[var(--foreground-muted)] leading-relaxed">
              Each item below is something the system does now, not something planned.
            </p>
          </div>

          <ul className="grid list-none gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {CAPABILITIES.map((claim) => (
              <li
                key={claim.id}
                className="flex flex-col gap-2 rounded-[var(--marketing-radius-panel)] border border-[var(--border-faint)] bg-[var(--surface-panel)] p-6 shadow-[var(--shadow-card)]"
              >
                <h3 className="font-[var(--font-weight-semibold)] text-[var(--foreground)]">
                  {claim.title}
                </h3>
                <p className="text-sm leading-relaxed text-[var(--foreground-muted)]">
                  {claim.body}
                </p>
              </li>
            ))}
          </ul>
        </section>

        {/* ── The thesis ───────────────────────────────────────── */}
        <section className="flex max-w-[var(--marketing-measure)] flex-col gap-5">
          <h2 className="font-[family-name:var(--font-serif-display)] text-3xl font-[var(--font-weight-semibold)] text-[var(--foreground)]">
            {THESIS.heading}
          </h2>
          {THESIS.body.map((paragraph) => (
            <p
              key={paragraph.slice(0, 32)}
              className="text-[var(--foreground-muted)] leading-relaxed"
            >
              {paragraph}
            </p>
          ))}
        </section>

        {/* ── What it does NOT do ──────────────────────────────── */}
        <section className="flex flex-col gap-8">
          <div className="flex flex-col gap-3">
            <h2 className="font-[family-name:var(--font-serif-display)] text-3xl font-[var(--font-weight-semibold)] text-[var(--foreground)]">
              What it does not do yet
            </h2>
            <p className="max-w-[var(--marketing-measure)] text-[var(--foreground-muted)] leading-relaxed">
              A platform that is vague about its limits is asking you to discover them yourself, on
              your own matter. Here are ours.
            </p>
          </div>

          <ul className="grid list-none gap-x-10 gap-y-6 sm:grid-cols-2">
            {NOT_YET.map((claim) => (
              <li
                key={claim.id}
                className="flex flex-col gap-2 border-l-2 border-[var(--border-strong)] pl-5"
              >
                <h3 className="font-[var(--font-weight-semibold)] text-[var(--foreground)]">
                  {claim.title}
                </h3>
                <p className="text-sm leading-relaxed text-[var(--foreground-muted)]">
                  {claim.body}
                </p>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-4 border-t border-[var(--marketing-rule)] py-8 text-sm text-[var(--foreground-subtle)]">
        <p className="max-w-[var(--marketing-measure)]">
          Evidara — legal data infrastructure. This page describes a system under active development
          and is not an offer of legal services or legal advice.
        </p>
        {/*
          AGPL-3.0 section 13. This page is served over a network, so it offers
          its source like every other Evidara surface — see /LICENSE-HISTORY.md.
          It is a source link, not a product link: the page deliberately points
          at no running deployment (see the note at the top of this file), and
          `page.test.tsx` enforces that.
        */}
        <RepositoryLink
          label="Source code on GitHub"
          size={18}
          className="inline-flex items-center justify-center rounded-md p-2 text-[var(--foreground-subtle)] transition-colors hover:text-[var(--foreground)]"
        />
      </footer>
    </div>
  );
}
