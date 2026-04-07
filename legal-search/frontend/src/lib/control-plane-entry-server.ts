import { cookies } from "next/headers";
import { computeShowControlPlaneEntry, EVIDARA_UI_PROFILE_COOKIE } from "@/lib/control-plane-entry";

export type ControlPlaneEntryConfig = {
  showControlPlaneEntry: boolean;
  controlPanelUrl?: string;
};

export async function resolveControlPlaneEntryConfig(): Promise<ControlPlaneEntryConfig> {
  const jar = await cookies();
  const cookieProfile = jar.get(EVIDARA_UI_PROFILE_COOKIE)?.value;
  const controlPanelUrl = process.env.NEXT_PUBLIC_CONTROL_PANEL_URL?.trim();
  const showControlPlaneEntry = computeShowControlPlaneEntry({
    controlPanelUrl,
    cookieProfile,
    envDefaultProfile: process.env.NEXT_PUBLIC_DEFAULT_UI_PROFILE,
  });
  return {
    showControlPlaneEntry,
    controlPanelUrl,
  };
}

export async function resolveShowControlPlaneEntry(): Promise<boolean> {
  const entry = await resolveControlPlaneEntryConfig();
  return entry.showControlPlaneEntry;
}
