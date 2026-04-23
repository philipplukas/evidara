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
    border: "color-mix(in srgb, var(--status-healthy) 35%, transparent)",
    bg: "var(--status-healthy-subtle)",
    color: "var(--status-healthy)",
  },
  degraded: {
    Icon: WarningAmberIcon,
    border: "color-mix(in srgb, var(--status-degraded) 40%, transparent)",
    bg: "var(--status-degraded-subtle)",
    color: "var(--status-degraded)",
  },
  critical: {
    Icon: ErrorOutlineIcon,
    border: "color-mix(in srgb, var(--status-critical) 40%, transparent)",
    bg: "var(--status-critical-subtle)",
    color: "var(--status-critical)",
  },
  neutral: {
    Icon: RemoveCircleOutlineIcon,
    border: "var(--border-strong)",
    bg: "var(--status-neutral-subtle)",
    color: "var(--status-neutral)",
  },
  info: {
    Icon: InfoOutlinedIcon,
    border: "color-mix(in srgb, var(--status-info) 35%, transparent)",
    bg: "var(--status-info-subtle)",
    color: "var(--status-info)",
  },
};

/** Border color aligned with `StatusBadge` (for cards, rails, and other non-chip accents). */
export function adminLevelBorder(level: AdminStatusLevel): string {
  return LEVEL_META[level].border;
}

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
