import Link from "next/link";

const docsBase =
  typeof process.env.NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL === "string"
    ? process.env.NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL.replace(/\/$/, "")
    : "";

/**
 * Operator-facing documentation entry (walkthrough parity with other surfaces).
 * Set NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL to a hosted MkDocs (or similar) root in deploy envs.
 */
export default function DocsPage() {
  return (
    <main className="mx-auto flex min-h-full max-w-2xl flex-col gap-6 px-6 py-12 text-foreground">
      <header className="space-y-2">
        <h1 className="font-[family-name:var(--font-serif)] text-2xl font-semibold text-foreground">
          Dokumentation
        </h1>
        <p className="text-muted-foreground text-sm leading-relaxed">
          Architektur-, Betriebs- und Freigabe-Dokumentation liegt im Evidara-Monorepo unter{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">docs/</code>. Diese Seite
          verlinkt die gebündelte Anzeige, falls für Ihre Umgebung konfiguriert.
        </p>
      </header>

      {docsBase ? (
        <a
          href={`${docsBase}/`}
          className="text-primary hover:text-primary/80 inline-flex w-fit text-sm font-medium underline-offset-4 hover:underline"
          rel="noreferrer"
        >
          Vollständige Dokumentation öffnen
        </a>
      ) : (
        <p className="text-muted-foreground text-sm">
          Für Staging/Produktion: setzen Sie{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
            NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL
          </code>{" "}
          auf die Wurzel der veröffentlichten Docs-Site (z. B. MkDocs).
        </p>
      )}

      <section className="space-y-2 border-border border-t pt-6">
        <h2 className="text-foreground text-sm font-semibold">Relevante Runbooks (Repo-Pfade)</h2>
        <ul className="text-muted-foreground list-inside list-disc space-y-1 text-sm">
          <li>
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              docs/runbooks/metadata-quality-plan-status.md
            </code>
          </li>
          <li>
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              docs/runbooks/m5-evidence-checklist.md
            </code>
          </li>
          <li>
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              docs/runbooks/mvp-acceptance-scenario-pack.md
            </code>
          </li>
        </ul>
      </section>

      <p className="text-muted-foreground text-sm">
        <Link
          href="/"
          className="text-primary hover:text-primary/80 underline-offset-4 hover:underline"
        >
          Zurück zur Suche
        </Link>
      </p>
    </main>
  );
}
