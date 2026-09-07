/**
 * A JSON value, rendered as scrollable monospace text.
 *
 * Promoted here from `resources/runs/runCells.tsx` when `resources/sources`
 * needed it too (see `AcquisitionSpecPanel`). It carries no run semantics and
 * duplicating six lines of `<pre>` into a second resource folder is exactly the
 * parallel abstraction AGENTS.md says to avoid. `runCells` re-exports it, so
 * every existing import keeps working.
 *
 * Rendered as TEXT, never as markup: some payloads this shows are captured
 * third-party web content, and `dangerouslySetInnerHTML` here would execute
 * scraped script inside an authenticated operator session.
 */
export const formatJson = (value: unknown): string => JSON.stringify(value, null, 2);

export function CodeBlock({ value }: { value: unknown }) {
  return (
    <pre className="mt-1 overflow-x-auto rounded-[8px] bg-[var(--brand-wash-6)] px-3 py-2 text-[12px] leading-[1.4] text-[var(--foreground)]">
      {formatJson(value)}
    </pre>
  );
}
