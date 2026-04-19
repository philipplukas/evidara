import { cookies } from "next/headers";
import { publicConfig } from "@/config/publicConfig";
import { computeShowControlPlaneEntry, EVIDARA_UI_PROFILE_COOKIE } from "@/lib/control-plane-entry";

export type ControlPlaneEntryConfig = {
  showControlPlaneEntry: boolean;
  controlPanelUrl?: string;
};

export async function resolveControlPlaneEntryConfig(): Promise<ControlPlaneEntryConfig> {
  const jar = await cookies();
  const cookieProfile = jar.get(EVIDARA_UI_PROFILE_COOKIE)?.value;
  const controlPanelUrl = publicConfig.controlPanelBaseUrl;
  const showControlPlaneEntry = computeShowControlPlaneEntry({
    controlPanelUrl,
    cookieProfile,
    envDefaultProfile: publicConfig.defaultUiProfile,
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
