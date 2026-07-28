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
import BlueprintTemplateList from "../resources/blueprints/BlueprintTemplateList";
import { CommentaryInsightList } from "../resources/corrections/CommentaryInsightList";
import { CommentaryInsightShow } from "../resources/corrections/CommentaryInsightShow";
import { CorrectionShow } from "../resources/corrections/CorrectionShow";
import { CorrectionsList } from "../resources/corrections/CorrectionsList";
import { AcquisitionCoverageList } from "../resources/coverage/AcquisitionCoverageList";
import { Dashboard } from "../resources/dashboard/Dashboard";
import AuthorityCreate from "../resources/reference-data/AuthorityCreate";
import AuthorityEdit from "../resources/reference-data/AuthorityEdit";
import { AuthorityList } from "../resources/reference-data/AuthorityList";
import JurisdictionCreate from "../resources/reference-data/JurisdictionCreate";
import JurisdictionEdit from "../resources/reference-data/JurisdictionEdit";
import { JurisdictionList } from "../resources/reference-data/JurisdictionList";
import PreviewReviewListV2 from "../resources/runs/PreviewReviewListV2";
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
 * `<Admin>` mounts MUI's `<Notification>` by default. `<AppShell>` already
 * mounts `<ToastAdapter>`, so the two rendered the *same* failure twice in two
 * different styles — a dark bottom-centre snackbar with no dismiss alongside the
 * bottom-right toast (#671). Worse, both drain the same `takeNotification()`
 * queue, so which surface a given notification landed on was a race. Rendering
 * nothing here leaves `ToastAdapter` as the single notification surface.
 */
function NoNotification() {
  return null;
}

/**
 * Redirects the retired `/runs-v2/:id` preview detail route to the canonical
 * `runs` resource show route, preserving the record id (#520 consolidation).
 */
function RunsV2DetailRedirect() {
  const { id } = useParams();
  return <Navigate to={id ? `/runs/${encodeURIComponent(id)}/show` : "/runs"} replace />;
}

/**
 * Same treatment for the retired `/preview-review-v2/:id` route, now that the
 * v2 preview list/detail are the canonical `preview-review` resource pages.
 */
function PreviewReviewV2DetailRedirect() {
  const { id } = useParams();
  return (
    <Navigate
      to={id ? `/preview-review/${encodeURIComponent(id)}/show` : "/preview-review"}
      replace
    />
  );
}

export default function AdminApp() {
  return (
    <Admin
      dataProvider={controlPlaneDataProvider}
      dashboard={Dashboard}
      disableTelemetry
      layout={AdminLayout}
      notification={NoNotification}
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
      {/*
       * The coverage inventory (#668). Sits next to Sources because it is the
       * screen an operator reads *before* creating one: it says which templates
       * are live, which are inert, and which key is shut. It is also the only
       * place the ADR-0030 config key can be flipped from the panel.
       */}
      <Resource
        name={ResourceName.BlueprintTemplates}
        list={BlueprintTemplateList}
        recordRepresentation="provider_template_id"
        options={{ label: "Blueprints" }}
      />
      <Resource
        name={ResourceName.PreviewReview}
        list={PreviewReviewListV2}
        show={PreviewReviewShowV2}
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
        name={ResourceName.AcquisitionCoverage}
        list={AcquisitionCoverageList}
        recordRepresentation="jurisdiction_id"
        options={{ label: "Coverage" }}
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
       * keep resolving to the single runs experience.
       *
       * Preview review graduated the same way: `PreviewReviewListV2` /
       * `PreviewReviewShowV2` are the canonical `preview-review` list/show, and
       * `/preview-review-v2*` are redirects. The MUI v1 pages were deleted.
       */}
      <CustomRoutes>
        <Route path="/runs-v2" element={<Navigate to="/runs" replace />} />
        <Route path="/runs-v2/:id" element={<RunsV2DetailRedirect />} />
        <Route path="/preview-review-v2" element={<Navigate to="/preview-review" replace />} />
        <Route path="/preview-review-v2/:id" element={<PreviewReviewV2DetailRedirect />} />
      </CustomRoutes>
    </Admin>
  );
}
