/**
 * Render coverage for the Tailwind + ra-core `AuthorityList` (ADR-0026 port).
 *
 * The MUI version had no Tailwind total and no reachable pages (the admin side
 * of #616). This proves the `useListController` → `DataTable` wiring resolves
 * the fixture rows, renders the columns (including the "Global" fallback for a
 * jurisdiction-less authority), and surfaces the total via the table caption.
 * `CoreAdminContext` supplies a default router so `useNavigate` resolves
 * without an explicit `<Router>` wrapper.
 */
import { QueryClient } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { CoreAdminContext, testDataProvider } from "ra-core";
import { describe, expect, it } from "vitest";
import type { AuthorityRecord } from "../../lib/admin/dataProvider";
import { AuthorityList } from "./AuthorityList";

const authorities: AuthorityRecord[] = [
  {
    id: "auth_fedlex",
    authority_id: "auth_fedlex",
    jurisdiction_id: "jur_ch_federal",
    name: "Fedlex",
    slug: "fedlex",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-05-01T09:00:00Z",
  },
  {
    id: "auth_global",
    authority_id: "auth_global",
    jurisdiction_id: null,
    name: "Global Authority",
    slug: "global",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-05-02T09:00:00Z",
  },
];

function renderList(total = authorities.length) {
  const dataProvider = testDataProvider({
    getList: (async () => ({
      data: authorities,
      total,
    })) as unknown as ReturnType<typeof testDataProvider>["getList"],
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <CoreAdminContext dataProvider={dataProvider} queryClient={queryClient}>
      <AuthorityList />
    </CoreAdminContext>,
  );
}

describe("AuthorityList", () => {
  it("renders authority rows, including the Global jurisdiction fallback", async () => {
    const { container } = renderList();

    await waitFor(
      () => {
        expect(container.textContent).toContain("auth_fedlex");
      },
      { timeout: 5000 },
    );

    expect(container.textContent).toContain("Fedlex");
    expect(container.textContent).toContain("Global");
  });

  it("surfaces the total authority count in the caption", async () => {
    const { container } = renderList(42);

    await waitFor(
      () => {
        expect(container.textContent).toContain("auth_fedlex");
      },
      { timeout: 5000 },
    );

    expect(container.textContent).toContain("42 authorities");
  });
});
