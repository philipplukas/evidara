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
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
