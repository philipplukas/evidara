"use client";

import { Box } from "@mui/material";
import type { ReactNode } from "react";

interface PageContextBarProps {
  children: ReactNode;
}

/**
 * Sticky operator context strip for long show pages (run/source detail).
 */
export function PageContextBar({ children }: PageContextBarProps) {
  return (
    <Box
      sx={{
        position: "sticky",
        top: 0,
        zIndex: 3,
        mb: 2,
        py: 1.75,
        px: { xs: 0, sm: 0.25 },
        mx: { xs: -0.5, sm: 0 },
        backgroundColor: "rgba(255, 253, 248, 0.96)",
        backdropFilter: "blur(10px)",
        borderBottom: "1px solid",
        borderColor: "rgba(29, 41, 61, 0.12)",
      }}
    >
      {children}
    </Box>
  );
}
