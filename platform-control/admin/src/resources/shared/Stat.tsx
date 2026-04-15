"use client";

import { Card, CardContent, Typography } from "@mui/material";
import { type AdminStatusLevel, adminLevelBorder } from "./StatusBadge";

export type StatTone = "success" | "error" | "warning" | "info" | "default";

function statToneToAdminLevel(tone: StatTone): AdminStatusLevel {
  switch (tone) {
    case "success":
      return "healthy";
    case "error":
      return "critical";
    case "warning":
      return "degraded";
    case "info":
      return "info";
    default:
      return "neutral";
  }
}

/** Top-border accent for dashboard stats/cards — same borders as `StatusBadge` levels. */
export function statToneBorder(tone: StatTone): string {
  return adminLevelBorder(statToneToAdminLevel(tone));
}

/**
 * Derives dashboard card accent for a success-rate string like "85%" or "-".
 * Aligns with design-system plan F2: warn below 95%, critical below 80%.
 */
export function successRateTone(successRate: string): StatTone {
  if (successRate === "-") return "default";
  const n = Number.parseInt(successRate.replace(/%/g, ""), 10);
  if (Number.isNaN(n)) return "default";
  if (n < 80) return "error";
  if (n < 95) return "warning";
  return "success";
}

export function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: StatTone;
}) {
  return (
    <Card
      sx={{
        flex: 1,
        minWidth: 160,
        borderTop: "4px solid",
        borderTopColor: statToneBorder(tone),
      }}
    >
      <CardContent
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          gap: 0.75,
          py: 2.5,
        }}
      >
        <Typography
          variant="overline"
          sx={{ letterSpacing: "0.14em", color: "text.secondary", lineHeight: 1.1 }}
        >
          {label}
        </Typography>
        <Typography variant="h4" sx={{ fontWeight: 700, lineHeight: 1 }}>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.45 }}>
          At a glance
        </Typography>
      </CardContent>
    </Card>
  );
}
