import { cookies } from "next/headers";
import { computeShowControlPlaneEntry, EVIDARA_UI_PROFILE_COOKIE } from "@/lib/control-plane-entry";

export async function resolveShowControlPlaneEntry(): Promise<boolean> {
  const jar = await cookies();
  const cookieProfile = jar.get(EVIDARA_UI_PROFILE_COOKIE)?.value;
  return computeShowControlPlaneEntry({
    controlPanelUrl: process.env.NEXT_PUBLIC_CONTROL_PANEL_URL,
    cookieProfile,
    envDefaultProfile: process.env.NEXT_PUBLIC_DEFAULT_UI_PROFILE,
  });
}
