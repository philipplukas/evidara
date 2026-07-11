"use client";

/**
 * `AdminApp` — P4a cutover: MUI `<Layout>`/`<AppBar>`/`<Menu>`/`<Notification>`
 * swapped for Tailwind `<AppShell>` / `<AppBar>` / `<SidebarMenu>` /
 * `<ToastAdapter>`. The outer chrome (header, sidebar, notification surface)
 * is now fully Tailwind-rendered via the new shell.
 *
 * Remaining v1 MUI resource pages (AuthorityList/Edit, JurisdictionList/Edit,
 * CorrectionsList, CommentaryInsightList, Dashboard) keep importing
 * `@mui/material` internally — only the surrounding shell flipped. Dropping the
 * MUI packages from `package.json` is P4b (after every v1 page ports).
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
import { Route } from "react-router-dom";
import { ResourceName } from "../domain/resourceNames";
import { controlPlaneDataProvider } from "../lib/admin/dataProvider";
import { adminMuiTheme } from "../lib/admin/muiTheme";
import { CommentaryInsightList } from "../resources/corrections/CommentaryInsightList";
import { CommentaryInsightShow } from "../resources/corrections/CommentaryInsightShow";
import { CorrectionShow } from "../resources/corrections/CorrectionShow";
import { CorrectionsList } from "../resources/corrections/CorrectionsList";
import { Dashboard } from "../resources/dashboard/Dashboard";
import { AuthorityCreate } from "../resources/reference-data/AuthorityCreate";
import AuthorityCreateV2 from "../resources/reference-data/AuthorityCreateV2";
import { AuthorityEdit } from "../resources/reference-data/AuthorityEdit";
import AuthorityEditV2 from "../resources/reference-data/AuthorityEditV2";
import { AuthorityList } from "../resources/reference-data/AuthorityList";
import { JurisdictionCreate } from "../resources/reference-data/JurisdictionCreate";
import JurisdictionCreateV2 from "../resources/reference-data/JurisdictionCreateV2";
import { JurisdictionEdit } from "../resources/reference-data/JurisdictionEdit";
import JurisdictionEditV2 from "../resources/reference-data/JurisdictionEditV2";
import { JurisdictionList } from "../resources/reference-data/JurisdictionList";
import PreviewReviewList from "../resources/runs/PreviewReviewList";
import PreviewReviewShow from "../resources/runs/PreviewReviewShow";
import RunList from "../resources/runs/RunList";
import RunShow from "../resources/runs/RunShow";
import SourceCreate from "../resources/sources/SourceCreate";
import SourceList from "../resources/sources/SourceList";
import SourceShow from "../resources/sources/SourceShow";
import { AppShell } from "../ui/shell";

/** Thin adapter — ra-core's `LayoutComponent` contract takes `{ children }`. */
function AdminLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
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
        list={RunList}
        show={RunShow}
        recordRepresentation="run_id"
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
       * Each pair lives alongside the MUI canonical page until the
       * corresponding v1 file is deleted.
       */}
      <CustomRoutes>
        <Route path="/authorities-v2/create" element={<AuthorityCreateV2 />} />
        <Route path="/authorities-v2/:id/edit" element={<AuthorityEditV2 />} />
        <Route path="/jurisdictions-v2/create" element={<JurisdictionCreateV2 />} />
        <Route path="/jurisdictions-v2/:id/edit" element={<JurisdictionEditV2 />} />
      </CustomRoutes>
    </Admin>
  );
}
