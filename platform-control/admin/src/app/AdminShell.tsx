"use client";

import dynamic from "next/dynamic";

const AdminApp = dynamic(() => import("./AdminApp"), {
  loading: () => null,
  ssr: false,
});

export default function AdminShell() {
  return <AdminApp />;
}
