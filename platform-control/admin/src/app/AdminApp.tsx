"use client";

import { createTheme } from "@mui/material/styles";
import { Admin, Resource } from "react-admin";
import { controlPlaneDataProvider } from "../lib/admin/dataProvider";
import { AuthorityCreate } from "../resources/reference-data/AuthorityCreate";
import { AuthorityEdit } from "../resources/reference-data/AuthorityEdit";
import { AuthorityList } from "../resources/reference-data/AuthorityList";
import { JurisdictionCreate } from "../resources/reference-data/JurisdictionCreate";
import { JurisdictionEdit } from "../resources/reference-data/JurisdictionEdit";
import { JurisdictionList } from "../resources/reference-data/JurisdictionList";
import { PreviewReviewList } from "../resources/runs/PreviewReviewList";
import { PreviewReviewShow } from "../resources/runs/PreviewReviewShow";
import { RunList } from "../resources/runs/RunList";
import { RunShow } from "../resources/runs/RunShow";
import { SourceCreate } from "../resources/sources/SourceCreate";
import { SourceList } from "../resources/sources/SourceList";
import { SourceShow } from "../resources/sources/SourceShow";

const adminTheme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#0f4c81",
    },
    secondary: {
      main: "#8a5a2b",
    },
    background: {
      default: "#f4efe7",
      paper: "#fffdf8",
    },
  },
  shape: {
    borderRadius: 16,
  },
  typography: {
    fontFamily: "var(--font-admin-sans), system-ui, sans-serif",
    h4: {
      fontFamily: "var(--font-admin-serif), Georgia, serif",
      fontWeight: 600,
      letterSpacing: "-0.02em",
    },
    h5: {
      fontFamily: "var(--font-admin-serif), Georgia, serif",
      fontWeight: 600,
    },
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        colorPrimary: {
          background: "linear-gradient(120deg, rgba(15, 76, 129, 0.95), rgba(25, 93, 136, 0.88))",
          color: "#fffdf8",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backdropFilter: "blur(14px)",
          border: "1px solid rgba(29, 41, 61, 0.08)",
          boxShadow: "0 22px 50px rgba(29, 41, 61, 0.08)",
        },
      },
    },
  },
});

export default function AdminApp() {
  return (
    <Admin
      dataProvider={controlPlaneDataProvider}
      theme={adminTheme}
      title="Evidara Control Plane"
      disableTelemetry
    >
      <Resource
        name="jurisdictions"
        list={JurisdictionList}
        create={JurisdictionCreate}
        edit={JurisdictionEdit}
        recordRepresentation="name"
        options={{ label: "Jurisdictions" }}
      />
      <Resource
        name="authorities"
        list={AuthorityList}
        create={AuthorityCreate}
        edit={AuthorityEdit}
        recordRepresentation="name"
        options={{ label: "Authorities" }}
      />
      <Resource
        name="sources"
        list={SourceList}
        create={SourceCreate}
        show={SourceShow}
        recordRepresentation="name"
        options={{ label: "Sources" }}
      />
      <Resource
        name="preview-review"
        list={PreviewReviewList}
        show={PreviewReviewShow}
        recordRepresentation="run_id"
        options={{ label: "Preview Review" }}
      />
      <Resource name="runs" list={RunList} show={RunShow} recordRepresentation="run_id" />
    </Admin>
  );
}
