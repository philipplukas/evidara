"use client";

import type { SvgIconComponent } from "@mui/icons-material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Chip } from "@mui/material";
import type { AdminStatusLevel } from "./statusLevels";

/**
 * Semantic status levels aligned with legal-search `StatusLevel` / ADR-0016 (MUI implementation).
 */
export type { AdminStatusLevel } from "./statusLevels";

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

export {
  adminLevelBorder,
  pipelineHealthToLevel,
  runModeToLevel,
  runRecordStatusToLevel,
  sourceStatusToLevel,
  sourceVersionStatusToLevel,
} from "./statusLevels";

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
