"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import {
  isRoleAuthorized,
  normalizeRole,
  parseAllowedRoles,
  resolveUserRole,
} from "../lib/admin/accessControl";
import { resolveLegalSearchHandoff } from "../lib/admin/navigationContext";

const AdminApp = dynamic(() => import("./AdminApp"), {
  loading: () => (
    <main className="evidara-shell">
      <section className="evidara-shell__panel" aria-label="Loading Control Plane">
        <header className="evidara-shell__header">
          <div className="evidara-shell__brand">
            <div className="evidara-shell__mark">E</div>
            <div>
              <div className="evidara-shell__eyebrow">Evidara</div>
              <div className="evidara-shell__title">Platform control</div>
            </div>
          </div>
          <span className="evidara-shell__badge">Loading</span>
        </header>
        <div className="evidara-shell__body">
          <div className="evidara-shell__spinner" />
          <p style={{ margin: "16px 0 0", fontSize: 14, color: "var(--foreground-muted)" }}>
            Loading control plane...
          </p>
        </div>
      </section>
    </main>
  ),
  ssr: false,
});

export default function AdminShell() {
  const fallbackRole = normalizeRole(process.env.NEXT_PUBLIC_USER_ROLE);
  const [userRole, setUserRole] = useState(fallbackRole);
  const [isRoleResolved, setIsRoleResolved] = useState(false);
  const allowedRoles = parseAllowedRoles(process.env.NEXT_PUBLIC_ADMIN_ALLOWED_ROLES ?? "admin");
  const effectiveAllowedRoles = allowedRoles.length > 0 ? allowedRoles : ["admin"];
  const legalSearchUrl =
    process.env.NEXT_PUBLIC_LEGAL_SEARCH_URL?.trim() || "http://localhost:3101";
  const [handoff, setHandoff] = useState(() => resolveLegalSearchHandoff(null, legalSearchUrl));

  useEffect(() => {
    setUserRole(resolveUserRole(fallbackRole));
    setIsRoleResolved(true);
  }, [fallbackRole]);

  useEffect(() => {
    setHandoff(
      resolveLegalSearchHandoff(new URLSearchParams(window.location.search), legalSearchUrl),
    );
  }, [legalSearchUrl]);

  if (!isRoleResolved) {
    return null;
  }

  if (!isRoleAuthorized(userRole, effectiveAllowedRoles)) {
    return (
      <main className="evidara-shell">
        <section className="evidara-shell__panel" aria-labelledby="access-denied-title">
          <header className="evidara-shell__header">
            <div className="evidara-shell__brand">
              <div className="evidara-shell__mark">E</div>
              <div>
                <div className="evidara-shell__eyebrow">Evidara</div>
                <div className="evidara-shell__title">Control plane</div>
              </div>
            </div>
            <span className="evidara-shell__badge">403 Forbidden</span>
          </header>
          <div className="evidara-shell__body">
            <h1
              id="access-denied-title"
              style={{ margin: 0, fontSize: 22, fontWeight: 600, color: "var(--foreground)" }}
            >
              Access denied
            </h1>
            <p
              style={{
                margin: "12px 0 0",
                fontSize: 14,
                lineHeight: 1.7,
                color: "var(--foreground-muted)",
              }}
            >
              This control-plane surface is restricted to authorized operators. If you believe you
              should have access, contact your administrator.
            </p>
            <div style={{ marginTop: 24 }}>
              <a href={handoff.returnToUrl} className="evidara-shell__button">
                {handoff.query
                  ? `Return to search for "${handoff.query}"`
                  : "Return to legal search"}
              </a>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return <AdminApp />;
}
