/**
 * Horizontal-overflow coverage for the shared `DataTable`.
 *
 * The run queue carries enough columns that at desktop widths the rightmost
 * column used to clip: the table was `w-full`, so it crammed every column into
 * 100% of the container instead of scrolling. AGENTS.md / CLAUDE.md require
 * wide content to scroll inside its own `overflow-x: auto` container. These
 * lock in the two structural pieces of that contract — the scroll wrapper, and
 * a `min-w-full` (not fixed `w-full`) table that grows past the container so
 * the wrapper actually scrolls. jsdom has no layout engine, so this asserts the
 * mechanism (classes/structure), which is what determines the behaviour.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataTable } from "./DataTable";

type Row = { id: string; name: string };

const COLUMNS = [{ key: "name", header: "Name", render: (r: Row) => r.name }];

function renderTable() {
  return render(
    <DataTable<Row>
      records={[{ id: "1", name: "Fedlex" }]}
      columns={COLUMNS}
      getRowId={(r) => r.id}
    />,
  );
}

describe("DataTable horizontal overflow", () => {
  it("wraps the table in an overflow-x-auto scroll container", () => {
    renderTable();

    const scroller = screen.getByRole("table").parentElement;
    expect(scroller).not.toBeNull();
    expect(scroller).toHaveClass("overflow-x-auto");
  });

  it("lets the table grow past the container instead of cramming to fit", () => {
    renderTable();

    const table = screen.getByRole("table");
    // `min-w-full` grows to content width and scrolls; fixed `w-full` would
    // squeeze columns and clip the rightmost one.
    expect(table).toHaveClass("min-w-full");
    expect(table).not.toHaveClass("w-full");
  });
});
