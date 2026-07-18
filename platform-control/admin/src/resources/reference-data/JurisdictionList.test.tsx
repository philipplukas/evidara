/**
 * Render coverage for the Tailwind + ra-core `JurisdictionList` (ADR-0026 port).
 *
 * The MUI version scrolled all rows with no total and no pager (the admin side
 * of #616). This proves the `useListController` → `DataTable` wiring resolves
 * the fixture rows, renders the columns, and — the point of the fix — surfaces
 * the total count via the table caption. `CoreAdminContext` supplies a default
 * router so `useNavigate` resolves without an explicit `<Router>` wrapper.
 */
import { QueryClient } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { CoreAdminContext, testDataProvider } from "ra-core";
import { describe, expect, it } from "vitest";
import type { JurisdictionRecord } from "../../lib/admin/dataProvider";
import { JurisdictionList } from "./JurisdictionList";

const jurisdictions: JurisdictionRecord[] = [
  {
    id: "jur_ch_federal",
    jurisdiction_id: "jur_ch_federal",
    name: "Switzerland (Federal)",
    slug: "ch-federal",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-05-01T09:00:00Z",
  },
  {
    id: "jur_ch_zurich",
    jurisdiction_id: "jur_ch_zurich",
    name: "Canton of Zürich",
    slug: "ch-zh",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-05-02T09:00:00Z",
  },
];

function renderList(total = jurisdictions.length) {
  const dataProvider = testDataProvider({
    getList: (async () => ({
      data: jurisdictions,
      total,
    })) as unknown as ReturnType<typeof testDataProvider>["getList"],
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <CoreAdminContext dataProvider={dataProvider} queryClient={queryClient}>
      <JurisdictionList />
    </CoreAdminContext>,
  );
}

describe("JurisdictionList", () => {
  it("renders jurisdiction rows from the list controller", async () => {
    const { container } = renderList();

    await waitFor(
      () => {
        expect(container.textContent).toContain("jur_ch_federal");
      },
      { timeout: 5000 },
    );

    expect(container.textContent).toContain("Switzerland (Federal)");
    expect(container.textContent).toContain("ch-zh");
  });

  it("surfaces the total jurisdiction count in the caption", async () => {
    // Total exceeds the page size — the count comes from the controller's
    // `total`, not the number of rows on the page (the #616 regression).
    const { container } = renderList(2169);

    await waitFor(
      () => {
        expect(container.textContent).toContain("jur_ch_federal");
      },
      { timeout: 5000 },
    );

    expect(container.textContent).toContain("2169 jurisdictions");
  });
});
