import { resolveShowControlPlaneEntry } from "@/lib/control-plane-entry-server";
import HomeClient from "./HomeClient";

export const dynamic = "force-dynamic";

export default async function Home() {
  const showControlPlaneEntry = await resolveShowControlPlaneEntry();
  return <HomeClient showControlPlaneEntry={showControlPlaneEntry} />;
}
