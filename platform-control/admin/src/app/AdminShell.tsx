"use client";

import { BrandMark } from "@evidara/shell";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { publicConfig } from "../config/publicConfig";
import { isRoleAuthorized, normalizeRole, resolveUserRole } from "../lib/admin/accessControl";
import { resolveLegalSearchHandoff } from "../lib/admin/navigationContext";

const AdminApp = dynamic(() => import("./AdminApp"), {
  loading: () => (
    <main className="evidara-shell">
      <section className="evidara-shell__panel" aria-label="Loading Control Plane">
        <header className="evidara-shell__header">
          <div className="evidara-shell__brand">
            <div className="evidara-shell__mark">
              <BrandMark size={42} />
            </div>
            <div>
              <div className="evidara-shell__eyebrow">Evidara</div>
              <div className="evidara-shell__title">Platform control</div>
            </div>
          </div>
          <span className="evidara-shell__badge">Loading</span>
        </header>
        <div className="evidara-shell__body">
          <div className="evidara-shell__spinner" />
          <div className="evidara-shell__meta">
            <p className="evidara-shell__copy">Loading control plane...</p>
            <p className="evidara-shell__fineprint">
              Preparing operator navigation, status surfaces, and active records.
            </p>
          </div>
        </div>
      </section>
    </main>
  ),
  ssr: false,
});

export default function AdminShell() {
  const fallbackRole = normalizeRole(publicConfig.defaultUserRole);
  const [userRole, setUserRole] = useState(fallbackRole);
  const [isRoleResolved, setIsRoleResolved] = useState(false);
  const allowedRoles = publicConfig.adminAllowedRoles;
  const effectiveAllowedRoles = allowedRoles.length > 0 ? [...allowedRoles] : ["admin"];
  const [handoff, setHandoff] = useState(() =>
    resolveLegalSearchHandoff(null, publicConfig.legalSearchBaseUrl),
  );

  useEffect(() => {
    setUserRole(resolveUserRole(fallbackRole));
    setIsRoleResolved(true);
  }, [fallbackRole]);

  useEffect(() => {
    setHandoff(
      resolveLegalSearchHandoff(
        new URLSearchParams(window.location.search),
        publicConfig.legalSearchBaseUrl,
      ),
    );
  }, []);

  if (!isRoleResolved) {
    return null;
  }

  if (!isRoleAuthorized(userRole, effectiveAllowedRoles)) {
    return (
      <main className="evidara-shell">
        <section className="evidara-shell__panel" aria-labelledby="access-denied-title">
          <header className="evidara-shell__header">
            <div className="evidara-shell__brand">
              <div className="evidara-shell__mark">
                <BrandMark size={42} />
              </div>
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
            <p className="evidara-shell__copy">
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
