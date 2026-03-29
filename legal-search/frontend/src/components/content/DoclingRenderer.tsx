"use client";

import {
  type ContentItem,
  type DoclingDocument,
  type HighlightRange,
  isDoclingDocItem,
  iterateContent,
} from "@/lib/docling";

interface DoclingRendererProps {
  /** DoclingDocument JSON from the BFF */
  doc: DoclingDocument;
  /** Optional callback when a legal reference is clicked */
  onRefClick?: (targetId: string) => void;
}

/**
 * Renders a DoclingDocument as semantic React elements.
 * Replaces dangerouslySetInnerHTML with structured, type-safe rendering.
 */
export function DoclingRenderer({ doc, onRefClick }: DoclingRendererProps) {
  const items = Array.from(iterateContent(doc));

  if (items.length === 0) {
    return <div className="text-sm text-muted-foreground italic py-4">No content available.</div>;
  }

  return (
    <div className="docling-content space-y-2">
      {items.map((contentItem, index) => (
        <ContentBlock
          key={contentItem.item.self_ref || index}
          contentItem={contentItem}
          onRefClick={onRefClick}
        />
      ))}
    </div>
  );
}

function ContentBlock({
  contentItem,
  onRefClick,
}: {
  contentItem: ContentItem;
  onRefClick?: (targetId: string) => void;
}) {
  const { item, level, meta } = contentItem;

  if (isDoclingDocItem.SectionHeaderItem(item)) {
    return <SectionHeading text={item.text} level={item.level ?? level} />;
  }

  if (isDoclingDocItem.TextItem(item)) {
    return (
      <Paragraph
        text={item.text}
        marginal={meta?.marginal}
        highlights={meta?.highlights}
        legalRefs={meta?.legalRefs}
        onRefClick={onRefClick}
      />
    );
  }

  if (isDoclingDocItem.ListItem(item)) {
    return (
      <ListItemBlock
        text={item.text}
        marker={item.marker}
        enumerated={item.enumerated}
        highlights={meta?.highlights}
      />
    );
  }

  if (isDoclingDocItem.TableItem(item)) {
    return <LegalTable data={item.data} />;
  }

  if (isDoclingDocItem.CodeItem(item)) {
    return <CodeBlock text={item.text} language={item.code_language} />;
  }

  // Fallback for unknown item types
  if ("text" in item && typeof (item as Record<string, unknown>).text === "string") {
    return <p className="text-sm text-foreground/80">{(item as { text: string }).text}</p>;
  }

  return null;
}

// ─── Block Components ───

function SectionHeading({ text, level }: { text: string; level: number }) {
  const Tag = level <= 1 ? "h2" : level === 2 ? "h3" : "h4";
  const sizes: Record<string, string> = {
    h2: "text-base font-semibold text-foreground mt-4 mb-1",
    h3: "text-sm font-semibold text-foreground mt-3 mb-1",
    h4: "text-sm font-medium text-foreground/90 mt-2 mb-0.5",
  };

  return <Tag className={sizes[Tag]}>{text}</Tag>;
}

function Paragraph({
  text,
  marginal,
  highlights,
  legalRefs,
  onRefClick,
}: {
  text: string;
  marginal?: string;
  highlights?: HighlightRange[];
  legalRefs?: { targetId: string; label: string }[];
  onRefClick?: (targetId: string) => void;
}) {
  return (
    <p className="text-sm text-foreground/80 leading-relaxed">
      {marginal && (
        <span className="inline-block w-6 text-xs font-medium text-muted-foreground mr-1 shrink-0">
          {marginal}
        </span>
      )}
      <InlineContent
        text={text}
        highlights={highlights}
        legalRefs={legalRefs}
        onRefClick={onRefClick}
      />
    </p>
  );
}

function ListItemBlock({
  text,
  marker,
  enumerated,
  highlights,
}: {
  text: string;
  marker?: string;
  enumerated?: boolean;
  highlights?: HighlightRange[];
}) {
  return (
    <div className="flex gap-2 text-sm text-foreground/80 pl-4">
      <span className="text-muted-foreground shrink-0">{marker || (enumerated ? "•" : "–")}</span>
      <span>
        <InlineContent text={text} highlights={highlights} />
      </span>
    </div>
  );
}

function LegalTable({
  data,
}: {
  data: {
    grid: {
      text: string;
      column_header?: boolean;
      row_header?: boolean;
      row_span?: number;
      col_span?: number;
    }[][];
  };
}) {
  if (!data.grid || data.grid.length === 0) return null;

  return (
    <div className="overflow-x-auto my-2">
      <table className="w-full text-xs border-collapse border border-border">
        <tbody>
          {data.grid.map((row, rowIdx) => (
            <tr key={rowIdx} className={rowIdx === 0 ? "bg-muted/50" : ""}>
              {row.map((cell, colIdx) => {
                const CellTag = cell.column_header || cell.row_header ? "th" : "td";
                return (
                  <CellTag
                    key={colIdx}
                    rowSpan={cell.row_span}
                    colSpan={cell.col_span}
                    className={`border border-border px-2 py-1.5 text-left ${
                      CellTag === "th" ? "font-medium text-foreground" : "text-foreground/80"
                    }`}
                  >
                    {cell.text}
                  </CellTag>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CodeBlock({ text, language }: { text: string; language?: string }) {
  return (
    <pre className="text-xs bg-muted/50 rounded-md p-3 overflow-x-auto my-2 font-mono">
      {language && <span className="text-tiny text-muted-foreground block mb-1">{language}</span>}
      <code>{text}</code>
    </pre>
  );
}

// ─── Inline Content (highlights + legal refs) ───

function InlineContent({
  text,
  highlights,
  legalRefs,
  onRefClick,
}: {
  text: string;
  highlights?: HighlightRange[];
  legalRefs?: { targetId: string; label: string }[];
  onRefClick?: (targetId: string) => void;
}) {
  if (!highlights?.length && !legalRefs?.length) {
    return <>{text}</>;
  }

  // Build segments with highlights
  if (highlights?.length) {
    const sorted = [...highlights].sort((a, b) => a.start - b.start);
    const segments: React.ReactNode[] = [];
    let cursor = 0;

    for (const hl of sorted) {
      if (hl.start > cursor) {
        segments.push(text.slice(cursor, hl.start));
      }
      segments.push(
        <mark key={`hl-${hl.start}`} className="bg-yellow-200/60 px-0.5 rounded-sm">
          {text.slice(hl.start, hl.end)}
        </mark>,
      );
      cursor = hl.end;
    }
    if (cursor < text.length) {
      segments.push(text.slice(cursor));
    }
    return <>{segments}</>;
  }

  return <>{text}</>;
}
