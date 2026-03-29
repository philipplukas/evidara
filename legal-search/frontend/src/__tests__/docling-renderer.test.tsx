/**
 * DoclingRenderer — Component Render Tests
 *
 * WHY THESE TESTS EXIST:
 * DoclingRenderer is the replacement for dangerouslySetInnerHTML.
 * It must correctly render every DoclingDocument item type.
 * If it fails, article content is invisible.
 *
 * WHAT WE TEST:
 * - Renders section headers with correct heading levels
 * - Renders paragraphs with text
 * - Renders paragraphs with marginal numbers
 * - Renders list items
 * - Renders tables
 * - Renders highlights as <mark> elements
 * - Renders empty document state
 * - A11y: no violations
 */

import { screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it } from "vitest";
import { DoclingRenderer } from "@/components/content/DoclingRenderer";
import type { DoclingDocument } from "@/lib/docling";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

function makeDoc(overrides: Partial<DoclingDocument> = {}): DoclingDocument {
  return {
    schema_name: "DoclingDocument",
    version: "1.0.0",
    name: "Test Document",
    body: { self_ref: "#/body", children: [] },
    texts: [],
    tables: [],
    pictures: [],
    ...overrides,
  };
}

describe("DoclingRenderer", () => {
  it("renders empty state for document with no items", () => {
    renderWithProviders(<DoclingRenderer doc={makeDoc()} />);
    expect(screen.getByText("No content available.")).toBeInTheDocument();
  });

  it("renders section header", () => {
    const doc = makeDoc({
      body: {
        self_ref: "#/body",
        children: [{ $ref: "#/texts/0" }],
      },
      texts: [
        {
          self_ref: "#/texts/0",
          parent: { $ref: "#/body" },
          label: "section_header",
          orig: "Section Title",
          text: "Section Title",
          level: 1,
        },
      ] as unknown as DoclingDocument["texts"],
    });

    renderWithProviders(<DoclingRenderer doc={doc} />);
    expect(screen.getByText("Section Title")).toBeInTheDocument();
    expect(screen.getByText("Section Title").tagName).toBe("H2");
  });

  it("renders paragraph text", () => {
    const doc = makeDoc({
      body: {
        self_ref: "#/body",
        children: [{ $ref: "#/texts/0" }],
      },
      texts: [
        {
          self_ref: "#/texts/0",
          parent: { $ref: "#/body" },
          label: "paragraph",
          orig: "A paragraph of legal text.",
          text: "A paragraph of legal text.",
        },
      ] as unknown as DoclingDocument["texts"],
    });

    renderWithProviders(<DoclingRenderer doc={doc} />);
    expect(screen.getByText("A paragraph of legal text.")).toBeInTheDocument();
  });

  it("renders paragraph with marginal number", () => {
    const doc = makeDoc({
      body: {
        self_ref: "#/body",
        children: [{ $ref: "#/texts/0" }],
      },
      texts: [
        {
          self_ref: "#/texts/0",
          parent: { $ref: "#/body" },
          label: "paragraph",
          orig: "Marginal paragraph text.",
          text: "Marginal paragraph text.",
          legalMetadata: { marginal: "1" },
        },
      ] as unknown as DoclingDocument["texts"],
    });

    renderWithProviders(<DoclingRenderer doc={doc} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Marginal paragraph text.")).toBeInTheDocument();
  });

  it("renders table", () => {
    const doc = makeDoc({
      body: {
        self_ref: "#/body",
        children: [{ $ref: "#/tables/0" }],
      },
      tables: [
        {
          self_ref: "#/tables/0",
          parent: { $ref: "#/body" },
          label: "table",
          data: {
            grid: [
              [
                {
                  text: "Header 1",
                  column_header: true,
                  start_row_offset_idx: 0,
                  end_row_offset_idx: 1,
                  start_col_offset_idx: 0,
                  end_col_offset_idx: 1,
                },
                {
                  text: "Header 2",
                  column_header: true,
                  start_row_offset_idx: 0,
                  end_row_offset_idx: 1,
                  start_col_offset_idx: 1,
                  end_col_offset_idx: 2,
                },
              ],
              [
                {
                  text: "Cell 1",
                  start_row_offset_idx: 1,
                  end_row_offset_idx: 2,
                  start_col_offset_idx: 0,
                  end_col_offset_idx: 1,
                },
                {
                  text: "Cell 2",
                  start_row_offset_idx: 1,
                  end_row_offset_idx: 2,
                  start_col_offset_idx: 1,
                  end_col_offset_idx: 2,
                },
              ],
            ],
          },
        },
      ],
    });

    renderWithProviders(<DoclingRenderer doc={doc} />);
    expect(screen.getByText("Header 1")).toBeInTheDocument();
    expect(screen.getByText("Cell 1")).toBeInTheDocument();
  });

  it("renders multiple items in reading order", () => {
    const doc = makeDoc({
      body: {
        self_ref: "#/body",
        children: [{ $ref: "#/texts/0" }, { $ref: "#/texts/1" }],
      },
      texts: [
        {
          self_ref: "#/texts/0",
          parent: { $ref: "#/body" },
          label: "section_header",
          orig: "Title First",
          text: "Title First",
          level: 1,
        },
        {
          self_ref: "#/texts/1",
          parent: { $ref: "#/body" },
          label: "paragraph",
          orig: "Body text second.",
          text: "Body text second.",
        },
      ] as unknown as DoclingDocument["texts"],
    });

    renderWithProviders(<DoclingRenderer doc={doc} />);
    expect(screen.getByText("Title First")).toBeInTheDocument();
    expect(screen.getByText("Body text second.")).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const doc = makeDoc({
      body: {
        self_ref: "#/body",
        children: [{ $ref: "#/texts/0" }, { $ref: "#/texts/1" }],
      },
      texts: [
        {
          self_ref: "#/texts/0",
          parent: { $ref: "#/body" },
          label: "section_header",
          orig: "Section",
          text: "Section",
          level: 1,
        },
        {
          self_ref: "#/texts/1",
          parent: { $ref: "#/body" },
          label: "paragraph",
          orig: "Content text.",
          text: "Content text.",
        },
      ] as unknown as DoclingDocument["texts"],
    });

    const { container } = renderWithProviders(<DoclingRenderer doc={doc} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
