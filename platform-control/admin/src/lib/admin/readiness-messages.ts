/**
 * Single source for run-readiness / preflight codes shown in the admin UI.
 * Add new backend codes here so launch surfaces stay consistent.
 */
export const READINESS_DETAIL_BY_CODE: Record<string, { title: string; action: string }> = {
  source_exists: {
    title: "Source not found",
    action: "Select an existing source from the catalog.",
  },
  source_version_exists: {
    title: "Version not found",
    action: "Select a source version for the chosen source.",
  },
  source_version_belongs_to_source: {
    title: "Source and version mismatch",
    action: "The selected version does not belong to the selected source. Choose a matching pair.",
  },
  mode_compatible_with_version_status: {
    title: "Version not approved for production",
    action:
      "Production runs require an approved version. Approve the selected version or switch to Preview mode.",
  },
  acquisition_seed_present: {
    title: "No acquisition seed configured",
    action: "Add at least one seed URL to the acquisition spec before launching.",
  },
};

export function describeReadinessDetail(code: string): { title: string; action: string } {
  return (
    READINESS_DETAIL_BY_CODE[code] ?? {
      title: "Preflight check failed",
      action: "Review the selected source/version pair and retry.",
    }
  );
}
