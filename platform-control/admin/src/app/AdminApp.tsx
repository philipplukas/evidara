"use client";

import { alpha, Box, Button, Chip, GlobalStyles, Stack, Typography } from "@mui/material";
import { createTheme } from "@mui/material/styles";
import { useEffect, useState } from "react";
import {
  Admin,
  AppBar,
  type AppBarProps,
  Layout,
  type LayoutProps,
  Resource,
  TitlePortal,
} from "react-admin";
import { controlPlaneDataProvider } from "../lib/admin/dataProvider";
import {
  describeLegalSearchHandoff,
  resolveLegalSearchHandoff,
} from "../lib/admin/navigationContext";
import { Dashboard } from "../resources/dashboard/Dashboard";
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

const LEGAL_SEARCH_URL =
  process.env.NEXT_PUBLIC_LEGAL_SEARCH_URL?.trim() || "http://localhost:3101";

const adminTheme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#0f4c81",
      dark: "#0b3d68",
      light: "#dce8f3",
      contrastText: "#fffdf8",
    },
    secondary: {
      main: "#9a7a4a",
      light: "#f1e6d6",
      contrastText: "#1d293d",
    },
    background: {
      default: "#f4efe7",
      paper: "#fffdf8",
    },
    text: {
      primary: "#1d293d",
      secondary: "rgba(29, 41, 61, 0.72)",
    },
    divider: "rgba(29, 41, 61, 0.12)",
  },
  shape: {
    borderRadius: 18,
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
          background: "linear-gradient(120deg, rgba(15, 76, 129, 0.98), rgba(11, 61, 104, 0.94))",
          color: "#fffdf8",
          borderBottom: "1px solid rgba(255, 253, 248, 0.12)",
          boxShadow: "0 18px 40px rgba(15, 76, 129, 0.14)",
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 999,
          textTransform: "none",
          fontWeight: 600,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 999,
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
    MuiDrawer: {
      styleOverrides: {
        paper: {
          background:
            "linear-gradient(180deg, rgba(255, 253, 248, 0.98), rgba(248, 243, 235, 0.94))",
          borderRight: "1px solid rgba(29, 41, 61, 0.08)",
          backdropFilter: "blur(14px)",
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          margin: "4px 8px",
          borderRadius: 14,
          transition: "background-color 160ms ease, transform 160ms ease",
          "&.Mui-selected": {
            backgroundColor: alpha("#0f4c81", 0.08),
            boxShadow: `inset 0 0 0 1px ${alpha("#0f4c81", 0.14)}`,
          },
          "&.Mui-selected:hover": {
            backgroundColor: alpha("#0f4c81", 0.12),
          },
        },
      },
    },
    MuiListItemIcon: {
      styleOverrides: {
        root: {
          minWidth: 36,
          color: "#0f4c81",
        },
      },
    },
    MuiToolbar: {
      styleOverrides: {
        root: {
          minHeight: 76,
          alignItems: "stretch",
        },
      },
    },
  },
});

function EvidaraAdminAppBar(props: AppBarProps) {
  const [handoff, setHandoff] = useState(() => resolveLegalSearchHandoff(null, LEGAL_SEARCH_URL));
  const handoffLabel = describeLegalSearchHandoff(handoff);

  useEffect(() => {
    setHandoff(
      resolveLegalSearchHandoff(new URLSearchParams(window.location.search), LEGAL_SEARCH_URL),
    );
  }, []);

  return (
    <AppBar {...props} userMenu={false}>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={{ xs: 1.5, md: 2 }}
        sx={{
          alignItems: { xs: "stretch", md: "center" },
          justifyContent: "space-between",
          width: "100%",
          minHeight: 76,
          px: { xs: 1.25, sm: 2.25 },
          py: { xs: 1, md: 1.25 },
        }}
      >
        <Stack direction="row" spacing={1.5} sx={{ minWidth: 0, alignItems: "center", flex: 1 }}>
          <Box
            aria-hidden
            sx={{
              width: 42,
              height: 42,
              borderRadius: 3,
              display: "grid",
              placeItems: "center",
              background:
                "linear-gradient(135deg, rgba(255, 253, 248, 0.98), rgba(255, 253, 248, 0.72))",
              color: "#0f4c81",
              border: "1px solid rgba(255, 253, 248, 0.2)",
              boxShadow: "0 12px 24px rgba(7, 23, 40, 0.12)",
              fontFamily: "var(--font-admin-serif), Georgia, serif",
              fontSize: 18,
              fontWeight: 700,
              lineHeight: 1,
            }}
          >
            E
          </Box>
          <Stack spacing={0.2} sx={{ minWidth: 0 }}>
            <Typography
              variant="overline"
              sx={{
                color: "rgba(255, 253, 248, 0.8)",
                letterSpacing: "0.16em",
                lineHeight: 1.15,
              }}
            >
              Evidara
            </Typography>
            <Typography
              variant="body2"
              sx={{
                color: "rgba(255, 253, 248, 0.78)",
                fontWeight: 500,
                lineHeight: 1.3,
              }}
            >
              Platform control
            </Typography>
          </Stack>
        </Stack>

        <Stack
          spacing={0.35}
          sx={{
            minWidth: 0,
            flex: 1,
            alignItems: { xs: "flex-start", md: "center" },
            textAlign: { xs: "left", md: "center" },
          }}
        >
          <Stack
            direction="row"
            spacing={0.75}
            useFlexGap
            flexWrap="wrap"
            sx={{ justifyContent: { xs: "flex-start", md: "center" } }}
          >
            <Chip
              label="Control plane"
              size="small"
              sx={{
                height: 24,
                backgroundColor: "rgba(255, 253, 248, 0.08)",
                color: "rgba(255, 253, 248, 0.9)",
                border: "1px solid rgba(255, 253, 248, 0.14)",
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            />
            <Chip
              label="Operator only"
              size="small"
              sx={{
                height: 24,
                backgroundColor: alpha("#fffdf8", 0.14),
                color: "#fffdf8",
                border: "1px solid rgba(255, 253, 248, 0.16)",
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            />
          </Stack>
          <TitlePortal
            variant="h6"
            sx={{
              color: "inherit",
              fontFamily: "var(--font-admin-serif), Georgia, serif",
              fontWeight: 600,
              lineHeight: 1.1,
            }}
          />
          <Typography
            variant="body2"
            sx={{
              color: alpha("#fffdf8", 0.74),
              lineHeight: 1.35,
            }}
          >
            {handoff.hasOrigin
              ? `Entered from legal search. ${handoffLabel}.`
              : "Source lifecycle, approval state, and run operations."}
          </Typography>
          {handoff.hasOrigin ? (
            <Stack
              direction="row"
              spacing={0.75}
              useFlexGap
              flexWrap="wrap"
              sx={{ justifyContent: { xs: "flex-start", md: "center" }, pt: 0.4 }}
            >
              {handoff.query ? (
                <Chip
                  label={`Search: ${handoff.query}`}
                  size="small"
                  sx={{
                    height: 24,
                    backgroundColor: alpha("#fffdf8", 0.12),
                    color: "#fffdf8",
                    border: "1px solid rgba(255, 253, 248, 0.18)",
                  }}
                />
              ) : null}
              {handoff.scopeLabel ? (
                <Chip
                  label={handoff.scopeLabel}
                  size="small"
                  sx={{
                    height: 24,
                    backgroundColor: "rgba(255, 253, 248, 0.08)",
                    color: "rgba(255, 253, 248, 0.88)",
                    border: "1px solid rgba(255, 253, 248, 0.14)",
                  }}
                />
              ) : null}
            </Stack>
          ) : null}
        </Stack>

        <Button
          href={handoff.returnToUrl}
          color="inherit"
          variant="outlined"
          startIcon={<span aria-hidden="true">↗</span>}
          sx={{
            alignSelf: { xs: "stretch", md: "center" },
            borderColor: "rgba(255, 253, 248, 0.28)",
            color: "inherit",
            backgroundColor: "rgba(255, 253, 248, 0.08)",
            px: 2,
            py: 1.1,
            whiteSpace: "nowrap",
            "&:hover": {
              borderColor: "rgba(255, 253, 248, 0.42)",
              backgroundColor: "rgba(255, 253, 248, 0.16)",
            },
          }}
        >
          {handoff.query ? "Return to active search" : "Back to legal search"}
        </Button>
      </Stack>
    </AppBar>
  );
}

function EvidaraAdminLayout(props: LayoutProps) {
  return (
    <Layout
      {...props}
      appBar={EvidaraAdminAppBar}
      sx={{
        "& .RaLayout-appFrame": {
          minHeight: "100vh",
          background: "transparent",
          position: "relative",
          isolation: "isolate",
          "&::before": {
            content: '""',
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            background:
              "radial-gradient(circle at top left, rgba(15, 76, 129, 0.08), transparent 34%), radial-gradient(circle at bottom right, rgba(154, 122, 74, 0.07), transparent 30%)",
            zIndex: -1,
          },
        },
        "& .RaLayout-content": {
          backgroundColor: "transparent",
          paddingTop: { xs: 2, sm: 3 },
          paddingBottom: { xs: 3, sm: 4 },
        },
      }}
    />
  );
}

export default function AdminApp() {
  return (
    <Admin
      dataProvider={controlPlaneDataProvider}
      theme={adminTheme}
      title="Evidara Control Plane"
      dashboard={Dashboard}
      disableTelemetry
      layout={EvidaraAdminLayout}
    >
      <GlobalStyles
        styles={{
          html: {
            backgroundColor: "#f4efe7",
          },
          body: {
            backgroundColor: "#f4efe7",
          },
          "::selection": {
            backgroundColor: "rgba(15, 76, 129, 0.18)",
            color: "#1d293d",
          },
          "*:focus-visible": {
            outline: "2px solid rgba(15, 76, 129, 0.42)",
            outlineOffset: 2,
          },
        }}
      />
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
