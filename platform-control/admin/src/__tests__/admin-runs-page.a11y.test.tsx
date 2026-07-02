/**
 * Resource-page-level axe coverage for the admin surface.
 *
 * Companion to `admin-shell.a11y.test.tsx`: the shell test exercises the
 * outer chrome under axe; this one renders a real resource page
 * (`RunListV2`) so the table, pill, and preset-bar primitives that
 * dominate operator screens are also covered. Together they close the
 * cross-surface a11y asymmetry called out in ADR-0027.
 *
 * Uses `testDataProvider` with deterministic run fixtures so the page
 * renders without network and the snapshot is stable across runs.
 */
import { QueryClient } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { CoreAdminContext, testDataProvider } from "ra-core";
import { describe, expect, it } from "vitest";
import type { RunListRecord } from "../lib/admin/dataProvider";
import RunListV2 from "../resources/runs/RunListV2";
import { AppShell } from "../ui/shell/AppShell";

expect.extend(toHaveNoViolations);

const runs: RunListRecord[] = [
  {
    id: "run_failed",
    run_id: "run_failed",
    source_id: "src_01",
    source_version_id: "sv_01",
    source_name: "Fedlex CC",
    version_label: "2026-04-01",
    mode: "production",
    status: "failed",
    started_at: "2026-04-15T09:00:00Z",
    completed_at: null,
    artifacts_count: 0,
    captured_resources_count: 4,
    failure_reason: "Provider jobs were throttled.",
    created_at: "2026-04-15T08:55:00Z",
    updated_at: "2026-04-15T09:30:00Z",
  },
  {
    id: "run_running",
    run_id: "run_running",
    source_id: "src_01",
    source_version_id: "sv_01",
    source_name: "Fedlex CC",
    version_label: "2026-04-01",
    mode: "preview",
    status: "running",
    started_at: "2026-04-15T09:10:00Z",
    completed_at: null,
    artifacts_count: 2,
    captured_resources_count: 8,
    failure_reason: null,
    created_at: "2026-04-15T09:05:00Z",
    updated_at: "2026-04-15T09:20:00Z",
  },
  {
    id: "run_completed",
    run_id: "run_completed",
    source_id: "src_02",
    source_version_id: "sv_02",
    source_name: "Fedlex Verordnungen",
    version_label: "2026-04-02",
    mode: "production",
    status: "completed",
    started_at: "2026-04-14T08:00:00Z",
    completed_at: "2026-04-14T08:30:00Z",
    artifacts_count: 12,
    captured_resources_count: 40,
    failure_reason: null,
    created_at: "2026-04-14T07:55:00Z",
    updated_at: "2026-04-14T08:30:00Z",
  },
];

function renderRunsPage() {
  // The DataProvider generic methods are parameterised on RecordType; in tests
  // we know the resource is "runs" and the rows are RunListRecord, so cast
  // through `unknown` instead of fighting the generic constraint.
  const dataProvider = testDataProvider({
    getList: (async () => ({ data: runs, total: runs.length })) as unknown as ReturnType<
      typeof testDataProvider
    >["getList"],
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <CoreAdminContext dataProvider={dataProvider} queryClient={queryClient}>
      <AppShell>
        <RunListV2 />
      </AppShell>
    </CoreAdminContext>,
  );
}

describe("RunListV2 route-level accessibility", () => {
  it("has no accessibility violations on the run queue page", async () => {
    const { container } = renderRunsPage();

    // Wait for the controller's getList to resolve and the table to render.
    await waitFor(
      () => {
        expect(container.textContent).toContain("Fedlex CC");
      },
      { timeout: 5000 },
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
