"use client";

/**
 * `AdminApp` — P4a cutover: MUI `<Layout>`/`<AppBar>`/`<Menu>`/`<Notification>`
 * swapped for Tailwind `<AppShell>` / `<AppBar>` / `<SidebarMenu>` /
 * `<ToastAdapter>`. The outer chrome (header, sidebar, notification surface)
 * is now fully Tailwind-rendered via the new shell.
 *
 * V1 MUI resource pages (SourceList, RunShow, AuthorityEdit, Dashboard, …)
 * keep importing `@mui/material` internally — only the surrounding shell
 * flipped. Dropping the MUI packages from `package.json` is P4b (after
 * every v1 page ports).
 *
 * Layout pattern: `<Admin>` from `react-admin` + `layout={AdminLayout}` with
 * a thin adapter that renders `<AppShell>{children}</AppShell>`. We tried
 * `<CoreAdmin>` from `ra-core` first (lighter, fewer deps) but MUI-rendered
 * v1 pages crash without react-admin's ThemeProvider + CssBaseline that
 * `<Admin>` sets up internally. Keeping `<Admin>` is the documented fallback
 * in ADR-0026 P4a; swap to `<CoreAdmin>` as part of P4b once v1 pages are gone.
 */

import { CustomRoutes } from "ra-core";
import type { ReactNode } from "react";
import { Admin, Resource } from "react-admin";
import { Navigate, Route, useParams } from "react-router-dom";
import { ResourceName } from "../domain/resourceNames";
import { controlPlaneDataProvider } from "../lib/admin/dataProvider";
import { adminMuiTheme } from "../lib/admin/muiTheme";
import { CommentaryInsightList } from "../resources/corrections/CommentaryInsightList";
import { CommentaryInsightShow } from "../resources/corrections/CommentaryInsightShow";
import { CorrectionShow } from "../resources/corrections/CorrectionShow";
import { CorrectionsList } from "../resources/corrections/CorrectionsList";
import { Dashboard } from "../resources/dashboard/Dashboard";
import AuthorityCreate from "../resources/reference-data/AuthorityCreate";
import AuthorityEdit from "../resources/reference-data/AuthorityEdit";
import { AuthorityList } from "../resources/reference-data/AuthorityList";
import JurisdictionCreate from "../resources/reference-data/JurisdictionCreate";
import JurisdictionEdit from "../resources/reference-data/JurisdictionEdit";
import { JurisdictionList } from "../resources/reference-data/JurisdictionList";
import { PreviewReviewList } from "../resources/runs/PreviewReviewList";
import PreviewReviewListV2 from "../resources/runs/PreviewReviewListV2";
import { PreviewReviewShow } from "../resources/runs/PreviewReviewShow";
import PreviewReviewShowV2 from "../resources/runs/PreviewReviewShowV2";
import RunListV2 from "../resources/runs/RunListV2";
import RunShowV2 from "../resources/runs/RunShowV2";
import SourceCreate from "../resources/sources/SourceCreate";
import SourceList from "../resources/sources/SourceList";
import SourceShow from "../resources/sources/SourceShow";
import { AppShell } from "../ui/shell";

/** Thin adapter — ra-core's `LayoutComponent` contract takes `{ children }`. */
function AdminLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}

/**
 * Redirects the retired `/runs-v2/:id` preview detail route to the canonical
 * `runs` resource show route, preserving the record id (#520 consolidation).
 */
function RunsV2DetailRedirect() {
  const { id } = useParams();
  return <Navigate to={id ? `/runs/${encodeURIComponent(id)}/show` : "/runs"} replace />;
}

export default function AdminApp() {
  return (
    <Admin
      dataProvider={controlPlaneDataProvider}
      dashboard={Dashboard}
      disableTelemetry
      layout={AdminLayout}
      theme={adminMuiTheme}
    >
      <Resource
        name={ResourceName.Jurisdictions}
        list={JurisdictionList}
        create={JurisdictionCreate}
        edit={JurisdictionEdit}
        recordRepresentation="name"
        options={{ label: "Jurisdictions" }}
      />
      <Resource
        name={ResourceName.Authorities}
        list={AuthorityList}
        create={AuthorityCreate}
        edit={AuthorityEdit}
        recordRepresentation="name"
        options={{ label: "Authorities" }}
      />
      <Resource
        name={ResourceName.Sources}
        list={SourceList}
        create={SourceCreate}
        show={SourceShow}
        recordRepresentation="name"
        options={{ label: "Sources" }}
      />
      <Resource
        name={ResourceName.PreviewReview}
        list={PreviewReviewList}
        show={PreviewReviewShow}
        recordRepresentation="run_id"
        options={{ label: "Preview approvals" }}
      />
      <Resource
        name={ResourceName.Runs}
        list={RunListV2}
        show={RunShowV2}
        recordRepresentation="run_id"
        options={{ label: "Runs" }}
      />
      <Resource
        name={ResourceName.Corrections}
        list={CorrectionsList}
        show={CorrectionShow}
        recordRepresentation="correction_id"
        options={{ label: "Corrections" }}
      />
      <Resource
        name={ResourceName.CommentaryInsights}
        list={CommentaryInsightList}
        show={CommentaryInsightShow}
        recordRepresentation="insight_id"
        options={{ label: "Commentary insights" }}
      />
      {/*
       * Tailwind + ra-core v2 previews (coexistence window, see ADR-0026).
       * Reference-data forms (authorities, jurisdictions) graduated to the
       * canonical resource `create`/`edit` routes above (#501 pattern).
       *
       * Runs graduated too (#520): the v2 table/detail are now the canonical
       * `runs` resource `list`/`show` above. The legacy `/runs-v2` routes stay
       * as thin redirects so existing deep links (and legal-search handoffs)
       * keep resolving to the single runs experience. Only preview-review still
       * coexists with its MUI resource.
       */}
      <CustomRoutes>
        <Route path="/runs-v2" element={<Navigate to="/runs" replace />} />
        <Route path="/runs-v2/:id" element={<RunsV2DetailRedirect />} />
        <Route path="/preview-review-v2" element={<PreviewReviewListV2 />} />
        <Route path="/preview-review-v2/:id" element={<PreviewReviewShowV2 />} />
      </CustomRoutes>
    </Admin>
  );
}
