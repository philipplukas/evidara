/**
 * Busy/error announcement coverage for the shared `DataTable`.
 *
 * The table renders "Loading…" and "Failed to load records." as plain cells.
 * Sighted operators see them; assistive tech was told nothing — the admin
 * surface had no `aria-busy`, `aria-live`, or `role="status"` anywhere. These
 * lock in the two signals that survive the mount/unmount lifecycle of those
 * cells: `aria-busy` on the persistent <table>, and `role="alert"` on the
 * error node (which announces on insertion).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DataTable } from "./DataTable";

type Row = { id: string; name: string };

const COLUMNS = [{ key: "name", header: "Name", render: (r: Row) => r.name }];

function renderTable(props: Partial<Parameters<typeof DataTable<Row>>[0]> = {}) {
  return render(
    <DataTable<Row> records={[]} columns={COLUMNS} getRowId={(r) => r.id} {...props} />,
  );
}

describe("DataTable busy + error announcements", () => {
  it("marks the table busy while loading", () => {
    renderTable({ isLoading: true });

    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
  });

  it("clears busy once records arrive", () => {
    renderTable({ isLoading: false, records: [{ id: "1", name: "Fedlex" }] });

    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "false");
  });

  it("announces a load failure via an alert", () => {
    renderTable({ error: new Error("boom") });

    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load records.");
  });

  it("does not announce an alert on the empty state", () => {
    // "No records." is a resting state, not an error — announcing it would be
    // noise every time an operator filters a list down to nothing.
    renderTable({ records: [] });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "false");
  });
});

/**
 * #624 — row-click was the only path to a record's detail on the canonical v2
 * pages, and it was a bare `onClick` on a `<tr>`: no tab stop, no key handler.
 * A keyboard-only operator could not open any record. Same defect on the sort
 * headers, which were an `onClick` on the `<th>`.
 */
describe("DataTable keyboard activation", () => {
  const RECORDS: Row[] = [{ id: "1", name: "Fedlex" }];

  it("makes an activatable row a tab stop", () => {
    renderTable({ records: RECORDS, onRowClick: () => {} });

    expect(screen.getByRole("row", { name: /Fedlex/ })).toHaveAttribute("tabindex", "0");
  });

  it("leaves rows out of the tab order when they are not activatable", () => {
    renderTable({ records: RECORDS });

    expect(screen.getByRole("row", { name: /Fedlex/ })).not.toHaveAttribute("tabindex");
  });

  it("opens the record on Enter", () => {
    const onRowClick = vi.fn();
    renderTable({ records: RECORDS, onRowClick });

    const row = screen.getByRole("row", { name: /Fedlex/ });
    row.focus();
    fireEvent.keyDown(row, { key: "Enter" });

    expect(onRowClick).toHaveBeenCalledWith(RECORDS[0]);
  });

  it("opens the record on Space", () => {
    const onRowClick = vi.fn();
    renderTable({ records: RECORDS, onRowClick });

    const row = screen.getByRole("row", { name: /Fedlex/ });
    row.focus();
    fireEvent.keyDown(row, { key: " " });

    expect(onRowClick).toHaveBeenCalledWith(RECORDS[0]);
  });

  it("names the row from getRowLabel when supplied", () => {
    renderTable({
      records: RECORDS,
      onRowClick: () => {},
      getRowLabel: (r) => `Open source ${r.name}`,
    });

    expect(screen.getByRole("row", { name: "Open source Fedlex" })).toBeInTheDocument();
  });

  // A real <button> is keyboard-activatable for free; the point of the
  // assertion is that the control exists at all, not that React fires it.
  it("exposes a sortable header as a real button rather than a click handler on the th", () => {
    const onSort = vi.fn();
    renderTable({
      records: RECORDS,
      columns: [{ key: "name", header: "Name", sortField: "name", render: (r: Row) => r.name }],
      onSort,
    });

    const header = screen.getByRole("button", { name: /Name/ });
    header.focus();
    fireEvent.click(header);

    expect(onSort).toHaveBeenCalledWith("name", "ASC");
  });
});
