/**
 * CommentaryResultCard + dispatch tests (#431).
 *
 * Covers the commentary variant of the result card: visual marker
 * ("Commentary on:" block), source-document links, and the dispatch
 * helper that ResultList uses to choose between ResultCard and
 * CommentaryResultCard. Mixed result lists (one of each variant) keep
 * existing rendering working.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  CommentaryResultCard,
  isCommentaryResult,
} from "@/components/results/CommentaryResultCard";
import { ResultList } from "@/components/results/ResultList";
import type { SearchResultViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

const baseProps = {
  isSelected: false,
  onFocus: vi.fn(),
  isPinned: false,
};

const commentaryResult: SearchResultViewModel = {
  id: "ins_01jq7c1ny0ffv8qdr1xwbejqb6",
  title: "Article 754 OR — director liability.",
  subtitle: "Switzerland · Commentary",
  snippet: "Lehre als Haftungsnorm fuer Organe.",
  type: "commentary",
  recordKind: "commentary_insight",
  sourceDocumentIds: ["doc_01jq7bdptzqv3xs0c41xpw1ybg", "doc_01jq7bdptzqv3xs0c41xpw1ybh"],
  badges: [{ label: "Commentary", colorKey: "amber" }],
  metadataRows: [],
  relatedCounts: [],
  actions: [{ label: "Open commentary", icon: "book-open" }],
};

const documentResult: SearchResultViewModel = {
  id: "doc_01jq7bdptzqv3xs0c41xpw1ybg",
  title: "Art. 754 OR",
  subtitle: "Switzerland · Federal law",
  snippet: "Die Mitglieder des Verwaltungsrates...",
  type: "law",
  recordKind: "legal_document",
  badges: [{ label: "Law", colorKey: "blue" }],
  metadataRows: [],
  relatedCounts: [],
  actions: [],
};

describe("isCommentaryResult", () => {
  it("returns true when recordKind is commentary_insight", () => {
    expect(
      isCommentaryResult({
        ...documentResult,
        recordKind: "commentary_insight",
      }),
    ).toBe(true);
  });

  it("returns true when type is 'commentary' (back-compat fallback)", () => {
    expect(
      isCommentaryResult({
        ...documentResult,
        recordKind: undefined,
        type: "commentary",
      }),
    ).toBe(true);
  });

  it("returns false for legal_document", () => {
    expect(isCommentaryResult(documentResult)).toBe(false);
  });

  it("returns false when both signals are absent", () => {
    expect(
      isCommentaryResult({
        ...documentResult,
        recordKind: undefined,
        type: "law",
      }),
    ).toBe(false);
  });
});

describe("CommentaryResultCard", () => {
  it("renders the kind marker and source-document block", () => {
    renderWithProviders(<CommentaryResultCard result={commentaryResult} {...baseProps} />);

    // Kind marker visible at the top of the card so the variant is
    // unambiguous in dense lists. ("Kommentar" appears multiple times —
    // kind marker + badge + action; assert at least one match.)
    expect(screen.getAllByText(/Kommentar|Commentary|Commentaire/i).length).toBeGreaterThan(0);

    // Title + snippet + subtitle still rendered.
    expect(screen.getByText("Article 754 OR — director liability.")).toBeInTheDocument();
    expect(screen.getByText("Lehre als Haftungsnorm fuer Organe.")).toBeInTheDocument();

    // Source-document links rendered with /documents/{id} hrefs so the
    // operator can pivot to the primary statute.
    const link1 = screen.getByRole("link", { name: /doc_01jq7bdptzqv3xs0c41xpw1ybg/ });
    expect(link1).toHaveAttribute("href", "/documents/doc_01jq7bdptzqv3xs0c41xpw1ybg");
    const link2 = screen.getByRole("link", { name: /doc_01jq7bdptzqv3xs0c41xpw1ybh/ });
    expect(link2).toHaveAttribute("href", "/documents/doc_01jq7bdptzqv3xs0c41xpw1ybh");
  });

  it("omits the source-document block when sourceDocumentIds is empty", () => {
    renderWithProviders(
      <CommentaryResultCard
        result={{ ...commentaryResult, sourceDocumentIds: [] }}
        {...baseProps}
      />,
    );

    expect(screen.queryByRole("link")).toBeNull();
  });

  it("carries the data-record-kind attribute so visual regression tests can pin the variant", () => {
    const { container } = renderWithProviders(
      <CommentaryResultCard result={commentaryResult} {...baseProps} />,
    );
    expect(container.querySelector('[data-record-kind="commentary_insight"]')).not.toBeNull();
  });
});

describe("ResultList dispatch", () => {
  it("renders the commentary variant for commentary results and the default for documents in mixed lists", () => {
    const { container } = renderWithProviders(
      <ResultList
        results={[documentResult, commentaryResult]}
        selectedId={null}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        pinnedIds={new Set()}
      />,
    );

    // Commentary variant marked with the data-record-kind attribute.
    const commentaryArticle = container.querySelector('[data-record-kind="commentary_insight"]');
    expect(commentaryArticle).not.toBeNull();

    // Default ResultCard for the legal document carries no record-kind
    // attribute. Both rows are present in the same list.
    expect(screen.getByText("Art. 754 OR")).toBeInTheDocument();
    expect(screen.getByText("Article 754 OR — director liability.")).toBeInTheDocument();
  });
});
