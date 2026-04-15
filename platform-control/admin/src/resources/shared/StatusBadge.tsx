"use client";

import type { SvgIconComponent } from "@mui/icons-material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Chip } from "@mui/material";

/**
 * Semantic status levels aligned with legal-search `StatusLevel` / ADR-0016 (MUI implementation).
 */
export type AdminStatusLevel = "healthy" | "degraded" | "critical" | "neutral" | "info";

const LEVEL_META: Record<
  AdminStatusLevel,
  { Icon: SvgIconComponent; border: string; bg: string; color: string }
> = {
  healthy: {
    Icon: CheckCircleOutlineIcon,
    border: "rgba(46, 125, 50, 0.35)",
    bg: "rgba(46, 125, 50, 0.08)",
    color: "#1b5e20",
  },
  degraded: {
    Icon: WarningAmberIcon,
    border: "rgba(237, 108, 2, 0.4)",
    bg: "rgba(237, 108, 2, 0.1)",
    color: "#e65100",
  },
  critical: {
    Icon: ErrorOutlineIcon,
    border: "rgba(198, 40, 40, 0.4)",
    bg: "rgba(198, 40, 40, 0.08)",
    color: "#b71c1c",
  },
  neutral: {
    Icon: RemoveCircleOutlineIcon,
    border: "rgba(29, 41, 61, 0.2)",
    bg: "rgba(29, 41, 61, 0.06)",
    color: "rgba(29, 41, 61, 0.75)",
  },
  info: {
    Icon: InfoOutlinedIcon,
    border: "rgba(2, 136, 209, 0.35)",
    bg: "rgba(2, 136, 209, 0.08)",
    color: "#01579b",
  },
};

export function runRecordStatusToLevel(status: string): AdminStatusLevel {
  switch (status) {
    case "completed":
      return "healthy";
    case "failed":
      return "critical";
    case "running":
      return "info";
    case "pending":
      return "degraded";
    default:
      return "neutral";
  }
}

export function runModeToLevel(mode: string): AdminStatusLevel {
  return mode === "production" ? "healthy" : "info";
}

export function pipelineHealthToLevel(status: string): AdminStatusLevel {
  switch (status) {
    case "ok":
      return "healthy";
    case "blocked":
      return "degraded";
    case "failed":
      return "critical";
    case "in_progress":
      return "info";
    default:
      return "neutral";
  }
}

export function sourceVersionStatusToLevel(status: string): AdminStatusLevel {
  switch (status) {
    case "approved":
      return "healthy";
    case "pending_approval":
      return "info";
    case "draft":
      return "neutral";
    case "rejected":
      return "critical";
    case "superseded":
      return "neutral";
    default:
      return "neutral";
  }
}

export function sourceStatusToLevel(status: string): AdminStatusLevel {
  switch (status) {
    case "active":
      return "healthy";
    case "inactive":
      return "degraded";
    case "archived":
      return "neutral";
    default:
      return "neutral";
  }
}

interface StatusBadgeProps {
  level: AdminStatusLevel;
  label: string;
  size?: "small" | "medium";
  /** Lighter surface for secondary cues (e.g. pipeline health next to run status). */
  emphasis?: "default" | "subtle";
}

export function StatusBadge({
  level,
  label,
  size = "small",
  emphasis = "default",
}: StatusBadgeProps) {
  const { Icon, border, bg, color } = LEVEL_META[level];
  const isSubtle = emphasis === "subtle";

  return (
    <Chip
      variant="outlined"
      size={size}
      icon={<Icon sx={{ fontSize: size === "small" ? 16 : 18 }} />}
      label={label}
      sx={{
        fontWeight: 600,
        borderColor: border,
        backgroundColor: isSubtle ? "transparent" : bg,
        color: isSubtle ? "text.primary" : color,
        "& .MuiChip-icon": {
          color: isSubtle ? "text.secondary" : color,
        },
        "& .MuiChip-label": { px: 0.25 },
      }}
    />
  );
}
