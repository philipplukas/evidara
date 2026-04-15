"use client";

import { Card, CardContent, Typography } from "@mui/material";

export type StatTone = "success" | "error" | "warning" | "info" | "default";

export const TONE_ACCENTS: Record<StatTone, string> = {
  success: "#2e7d32",
  error: "#c62828",
  warning: "#ed6c02",
  info: "#0288d1",
  default: "rgba(29, 41, 61, 0.22)",
};

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
        borderTopColor: TONE_ACCENTS[tone],
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
