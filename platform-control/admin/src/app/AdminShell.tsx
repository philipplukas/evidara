"use client";

import dynamic from "next/dynamic";
import {
  isRoleAuthorized,
  normalizeRole,
  parseAllowedRoles,
  resolveUserRole,
} from "../lib/admin/accessControl";

const AdminApp = dynamic(() => import("./AdminApp"), {
  loading: () => null,
  ssr: false,
});

export default function AdminShell() {
  const fallbackRole = normalizeRole(process.env.NEXT_PUBLIC_USER_ROLE);
  const userRole = resolveUserRole(fallbackRole);
  const allowedRoles = parseAllowedRoles(process.env.NEXT_PUBLIC_ADMIN_ALLOWED_ROLES ?? "admin");
  const legalSearchUrl =
    process.env.NEXT_PUBLIC_LEGAL_SEARCH_URL?.trim() || "http://localhost:3000";

  if (!isRoleAuthorized(userRole, allowedRoles)) {
    return (
      <main className="min-h-screen bg-slate-50 text-slate-900 flex items-center justify-center px-6">
        <section className="max-w-xl w-full rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
            403 Forbidden
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">Access denied</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            This control-panel surface is restricted to authorized operators. If you believe you
            should have access, contact your administrator.
          </p>
          <div className="mt-6">
            <a
              href={legalSearchUrl}
              className="inline-flex items-center rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              Return to legal search
            </a>
          </div>
        </section>
      </main>
    );
  }

  return <AdminApp />;
}
