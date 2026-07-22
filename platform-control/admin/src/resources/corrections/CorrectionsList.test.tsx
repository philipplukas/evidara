/**
 * Render coverage for the Tailwind + ra-core `CorrectionsList` (ADR-0026 port).
 *
 * Proves the `useListController` → `DataTable` wiring resolves the fixture rows
 * and renders the correction id, status pill, and rationale — i.e. the MUI
 * `<List>`/`<Datagrid>` scaffolding was replaced without losing the columns.
 * `CoreAdminContext` supplies a default router, so `useNavigate` resolves
 * without an explicit `<Router>` wrapper.
 */
import { QueryClient } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { CoreAdminContext, testDataProvider } from "ra-core";
import { describe, expect, it } from "vitest";
import type { CorrectionRecord } from "../../lib/admin/dataProvider";
import { CorrectionsList, describeActiveCorrectionFilters } from "./CorrectionsList";

const corrections: CorrectionRecord[] = [
  {
    id: "cor_pending",
    correction_id: "cor_pending",
    target_entity_type: "commentary_insight",
    target_entity_id: "ins_01",
    correction_type: "field_edit",
    payload: { field: "claim", value: "Revised claim." },
    original_snapshot: { claim: "Original claim." },
    operator_id: "op_alice",
    pipeline_run_id: null,
    rationale: "Claim contradicted the cited article.",
    status: "pending",
    created_at: "2026-05-01T09:00:00Z",
    applied_at: null,
  },
];

function renderList() {
  const dataProvider = testDataProvider({
    getList: (async () => ({
      data: corrections,
      total: corrections.length,
    })) as unknown as ReturnType<typeof testDataProvider>["getList"],
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <CoreAdminContext dataProvider={dataProvider} queryClient={queryClient}>
      <CorrectionsList />
    </CoreAdminContext>,
  );
}

describe("CorrectionsList", () => {
  it("renders correction rows from the list controller", async () => {
    const { container } = renderList();

    await waitFor(
      () => {
        expect(container.textContent).toContain("cor_pending");
      },
      { timeout: 5000 },
    );

    expect(container.textContent).toContain("pending");
    expect(container.textContent).toContain("Claim contradicted the cited article.");
  });
});

/**
 * #674: the queue defaults to `status=pending`, so "No corrections match the
 * current filter." was equally true of an empty database and of a database full
 * of applied corrections. The empty state now names the filters in force, which
 * is what makes the two distinguishable.
 */
describe("describeActiveCorrectionFilters", () => {
  it("names nothing when no filter is applied", () => {
    expect(describeActiveCorrectionFilters({})).toEqual([]);
  });

  it("names the default pending filter with its preset label", () => {
    expect(describeActiveCorrectionFilters({ status: "pending" })).toEqual(["status: Pending"]);
  });

  it("names every applied filter", () => {
    expect(
      describeActiveCorrectionFilters({
        status: "applied",
        correction_type: "rescore_request",
        target_entity_type: "commentary_insight",
      }),
    ).toEqual(["status: Applied", "type: Rescore request", "target: Commentary insight"]);
  });
});
