import { resolveControlPlaneEntryConfig } from "@/lib/control-plane-entry-server";
import HomeClient from "./HomeClient";

export const dynamic = "force-dynamic";

export default async function Home() {
  const controlPlaneEntry = await resolveControlPlaneEntryConfig();
  return (
    <HomeClient
      showControlPlaneEntry={controlPlaneEntry.showControlPlaneEntry}
      controlPanelUrl={controlPlaneEntry.controlPanelUrl}
    />
  );
}
