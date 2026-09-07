"use client";

import { useMemo, useState } from "react";
import {
  extractArtifactContent,
  remainingPayload,
  summarizeArtifactPayload,
} from "./artifactPayload";
import { CodeBlock } from "./runCells";

/**
 * A raw artifact's payload, made readable.
 *
 * Replaces a single `JSON.stringify` dump with: the facts an operator reads
 * first as labelled rows, the document body in a scrollable block, and
 * everything not already shown as JSON underneath.
 *
 * SECURITY: the body is captured third-party web content and is rendered as
 * TEXT — inside `<pre>`, via a React child, never `dangerouslySetInnerHTML`.
 * `rawHtml` and `html` are among the keys this can select, so rendering it as
 * markup would execute arbitrary scraped script in the operator's authenticated
 * admin session. Showing markup as text is the whole point; it is not a
 * rendering limitation to be "fixed" later.
 */
export function ArtifactPayloadPanel({ payload }: { payload: unknown }) {
  const [showRaw, setShowRaw] = useState(false);
  const fields = useMemo(() => summarizeArtifactPayload(payload), [payload]);
  const content = useMemo(() => extractArtifactContent(payload), [payload]);
  const rest = useMemo(() => remainingPayload(payload), [payload]);

  // Nothing recognisable — fall back to exactly the old behaviour rather than
  // rendering an empty panel that implies the payload was empty.
  if (fields.length === 0 && !content && !rest) {
    return <CodeBlock value={payload} />;
  }

  return (
    <div className="mt-1 space-y-2">
      {fields.length > 0 ? (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[12px]">
          {fields.map((field) => (
            <div key={field.label} className="contents">
              <dt className="text-[var(--foreground-subtle)]">{field.label}</dt>
              <dd className="break-all font-mono text-[var(--foreground)]">{field.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {content ? (
        <details open>
          <summary className="cursor-pointer text-[12px] font-semibold text-[var(--foreground)]">
            Body{" "}
            <span className="font-normal text-[var(--foreground-subtle)]">({content.key})</span>
          </summary>
          <pre className="mt-1 max-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-[8px] bg-[var(--brand-wash-6)] px-3 py-2 text-[12px] leading-[1.4] text-[var(--foreground)]">
            {content.value}
          </pre>
        </details>
      ) : null}

      {rest ? (
        <div>
          <button
            type="button"
            onClick={() => setShowRaw((previous) => !previous)}
            className="text-[12px] font-semibold text-[var(--brand)] underline-offset-2 hover:underline"
          >
            {showRaw ? "Hide" : "Show"} remaining fields
          </button>
          {showRaw ? <CodeBlock value={rest} /> : null}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pipeline Health (expanded banner, not inside an accordion — matches v1).
// ---------------------------------------------------------------------------
