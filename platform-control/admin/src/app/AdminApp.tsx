"use client";

import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import {
  alpha,
  Box,
  Button,
  Chip,
  Divider,
  GlobalStyles,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";
import { createTheme } from "@mui/material/styles";
import { useEffect, useState } from "react";
import {
  Admin,
  AppBar,
  type AppBarProps,
  Layout,
  type LayoutProps,
  Menu,
  Resource,
  TitlePortal,
} from "react-admin";
import { controlPlaneDataProvider } from "../lib/admin/dataProvider";
import {
  ACCENT_CORE,
  ACCENT_CORE_MUTED,
  ACCENT_CORE_SUBTLE,
  MOTION_DURATION_MEDIUM,
  MOTION_EASING_STANDARD,
  SHADOW_CARD,
  SHADOW_CARD_HOVER,
} from "../lib/admin/designTokens";
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
      main: "#5c6b7e",
      light: "#e5ebf2",
      contrastText: "#1d293d",
    },
    background: {
      default: "#eef2f6",
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
          background: "linear-gradient(120deg, rgba(13, 58, 98, 0.98), rgba(9, 48, 83, 0.95))",
          color: "#fffdf8",
          borderBottom: "1px solid rgba(255, 253, 248, 0.12)",
          boxShadow: "0 18px 40px rgba(15, 76, 129, 0.12)",
          backdropFilter: "blur(16px)",
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          textTransform: "none",
          fontWeight: 600,
          "&:focus-visible": {
            outline: "2px solid rgba(15, 76, 129, 0.24)",
            outlineOffset: 2,
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 999,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: 0,
        },
        sizeSmall: {
          height: 24,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 20,
          background: "rgba(255, 253, 248, 0.9)",
          border: "1px solid rgba(29, 41, 61, 0.08)",
          boxShadow: "0 18px 44px rgba(29, 41, 61, 0.08)",
          backdropFilter: "blur(14px)",
        },
      },
    },
    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: "rgba(29, 41, 61, 0.12)",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backdropFilter: "blur(14px)",
          border: "1px solid rgba(29, 41, 61, 0.08)",
          backgroundImage: "none",
          // Sprint 1 — default Paper surfaces to the shared card elevation
          // + motion so admin Show/List tiles lift the same way legal-search
          // cards do. `MuiAppBar` has its own style override below and is
          // unaffected by this (styleOverrides merge per-component-root, and
          // AppBar's root wins its own boxShadow).
          boxShadow: SHADOW_CARD,
          transition: `box-shadow ${MOTION_DURATION_MEDIUM} ${MOTION_EASING_STANDARD}`,
          "@media (hover: hover)": {
            "&:hover": {
              boxShadow: SHADOW_CARD_HOVER,
            },
          },
          "@media (prefers-reduced-motion: reduce)": {
            transition: "none",
          },
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          width: 288,
          background:
            "linear-gradient(180deg, rgba(255, 253, 248, 0.98), rgba(248, 243, 235, 0.92))",
          borderRight: "1px solid rgba(29, 41, 61, 0.08)",
          backdropFilter: "blur(14px)",
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          margin: "4px 10px",
          borderRadius: 14,
          minHeight: 44,
          paddingTop: 10,
          paddingBottom: 10,
          paddingLeft: 14,
          paddingRight: 14,
          transition: `background-color ${MOTION_DURATION_MEDIUM} ${MOTION_EASING_STANDARD}, transform ${MOTION_DURATION_MEDIUM} ${MOTION_EASING_STANDARD}`,
          "&:hover": {
            backgroundColor: alpha("#0f4c81", 0.08),
          },
          // Selected nav item uses the Evidara violet accent — admin analogue
          // of legal-search's active detail tab indicator (Sprint 1, TAR-244).
          // Hover-while-selected bumps to ACCENT_CORE_MUTED. The bar chrome
          // itself stays brand-navy so "where am I" (identity) and "which row
          // am I on" (state) stay distinct.
          "&.Mui-selected": {
            backgroundColor: ACCENT_CORE_SUBTLE,
            boxShadow: `inset 0 0 0 1px ${alpha(ACCENT_CORE, 0.22)}`,
            color: ACCENT_CORE,
            "& .MuiListItemIcon-root": {
              color: ACCENT_CORE,
            },
          },
          "&.Mui-selected:hover": {
            backgroundColor: ACCENT_CORE_MUTED,
          },
          "&:focus-visible": {
            outline: "2px solid rgba(15, 76, 129, 0.24)",
            outlineOffset: 2,
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
    MuiListItemText: {
      styleOverrides: {
        primary: {
          fontWeight: 600,
          lineHeight: 1.2,
        },
        secondary: {
          color: "rgba(29, 41, 61, 0.62)",
          fontSize: 12,
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: "1px solid rgba(29, 41, 61, 0.08)",
          paddingTop: 14,
          paddingBottom: 14,
        },
        head: {
          background: "rgba(244, 239, 231, 0.72)",
          color: "rgba(29, 41, 61, 0.7)",
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        },
      },
    },
    MuiToolbar: {
      styleOverrides: {
        root: {
          minHeight: 72,
          alignItems: "stretch",
        },
      },
    },
  },
});

function EvidaraAdminAppBar(props: AppBarProps) {
  const [handoff, setHandoff] = useState(() => resolveLegalSearchHandoff(null, LEGAL_SEARCH_URL));
  const handoffLabel = describeLegalSearchHandoff(handoff);
  const selectedItemLabel = handoff.selectedId ? `Selected item: ${handoff.selectedId}` : null;

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
              background: "linear-gradient(135deg, #0f4c81, #0b3d68)",
              color: "#fffdf8",
              border: "1px solid rgba(255, 253, 248, 0.16)",
              boxShadow: "0 12px 24px rgba(7, 23, 40, 0.16)",
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
              Control plane
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
          <Chip
            label="Operator · Control plane"
            size="small"
            sx={{
              height: 22,
              backgroundColor: "rgba(255, 253, 248, 0.08)",
              color: "rgba(255, 253, 248, 0.7)",
              border: "1px solid rgba(255, 253, 248, 0.10)",
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: "0.06em",
            }}
          />
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
              {handoff.selectedId ? (
                <Chip
                  label={selectedItemLabel}
                  size="small"
                  sx={{
                    height: 24,
                    backgroundColor: alpha("#fffdf8", 0.16),
                    color: "#fffdf8",
                    border: "1px solid rgba(255, 253, 248, 0.2)",
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

function EvidaraAdminMenu() {
  const [handoff, setHandoff] = useState(() => resolveLegalSearchHandoff(null, LEGAL_SEARCH_URL));

  useEffect(() => {
    setHandoff(
      resolveLegalSearchHandoff(new URLSearchParams(window.location.search), LEGAL_SEARCH_URL),
    );
  }, []);

  const footerLabel =
    handoff.hasOrigin && handoff.query ? "Return to active search" : "Back to legal search";

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        minHeight: "calc(100vh - 96px)",
      }}
    >
      <Box sx={{ flexShrink: 0 }}>
        <Menu />
      </Box>
      <Box
        sx={{
          mt: "auto",
          pt: 1,
          pb: 1.25,
          background:
            "linear-gradient(180deg, rgba(248, 243, 235, 0), rgba(248, 243, 235, 0.92) 40%, rgba(248, 243, 235, 0.98))",
          backdropFilter: "blur(8px)",
        }}
      >
        <Divider sx={{ mx: 2, mb: 1 }} />
        <ListItemButton
          component="a"
          href={handoff.returnToUrl}
          sx={{
            mx: 1.25,
            my: 0,
            borderRadius: 14,
            color: "#0f4c81",
          }}
        >
          <ListItemIcon>
            <ArrowBackIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary={footerLabel}
            secondary="Open operator search"
            primaryTypographyProps={{ fontWeight: 600 }}
          />
        </ListItemButton>
      </Box>
    </Box>
  );
}

function EvidaraAdminLayout(props: LayoutProps) {
  return (
    <Layout
      {...props}
      appBar={EvidaraAdminAppBar}
      menu={EvidaraAdminMenu}
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
        "& .RaLayout-contentWithSidebar": {
          background: "transparent",
        },
        "& .RaSidebar-paper, & .RaLayout-sidebar .MuiDrawer-paper": {
          background: "transparent",
          paddingTop: { xs: "72px", sm: "80px" },
          boxSizing: "border-box",
          minHeight: "100vh",
        },
        "& .RaSidebar-fixed": {
          height: "100%",
          minHeight: 0,
        },
        "& .RaLayout-content": {
          backgroundColor: "transparent",
          paddingTop: { xs: 1.75, sm: 2.5 },
          paddingBottom: { xs: 3, sm: 4 },
          width: "100%",
          maxWidth: "1600px",
          marginInline: "auto",
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
            outline: "2px solid rgba(15, 76, 129, 0.24)",
            outlineOffset: 2,
          },
          ".RaSidebar-drawerPaper, .RaSidebar-fixed, .RaLayout-sidebar": {
            background: "transparent",
          },
          ".RaMenuItemLink-root": {
            borderRadius: 14,
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
