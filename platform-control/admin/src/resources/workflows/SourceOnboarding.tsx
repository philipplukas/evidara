"use client";

/**
 * `SourceOnboarding` — the WORKFLOWS surface, backed by `/v1/wizard`.
 *
 * Replaces three sidebar links that were deep links to `/sources/create`,
 * `/authorities/create` and `/jurisdictions/create`. Those were not workflows:
 * they were the same routes as three resource pages, colliding badly enough that
 * `resourceLinkIsActive` exists to suppress the dual nav highlight. The real
 * cross-cutting task — scope → discovery plan → pilot → decision → scale — spans
 * every nav group and no resource page owns it. `routers/wizard.py` has had nine
 * endpoints and a run ledger for it since ADR-0021, and nothing called them.
 *
 * Deliberately NOT an index. `GET /v1/wizard/projects` does not exist (405,
 * verified 2026-09-06) — only `GET /projects/{id}`. So this page either starts a
 * project or resumes one by id, and the id lives in the URL. Listing projects
 * needs a contract change; faking an index client-side would mean inventing a
 * collection the server cannot enumerate.
 */

import { useNotify } from "ra-core";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  controlPlaneActions,
  type WizardProject,
  type WizardRunStatus,
} from "../../lib/admin/dataProvider";
import { ConfirmButton } from "../shared/ConfirmButton";
import {
  describeRunState,
  isTerminal,
  resolveStepStatuses,
  STEPS,
  type StepStatus,
} from "./wizardSteps";

/** Where the last project id is remembered, so "resume" is one click. */
const LAST_PROJECT_KEY = "evidara.admin.wizard.lastProjectId";

function readLastProjectId(): string | null {
  try {
    return window.localStorage.getItem(LAST_PROJECT_KEY);
  } catch {
    // Private windows and blocked site data throw on access, not just return
    // null. A remembered id is a convenience; never let it break the page.
    return null;
  }
}

function rememberProjectId(id: string): void {
  try {
    window.localStorage.setItem(LAST_PROJECT_KEY, id);
  } catch {
    /* non-fatal, see readLastProjectId */
  }
}

const STEP_DOT: Record<StepStatus, string> = {
  done: "bg-[var(--accent-core)] text-[var(--admin-on-brand,white)]",
  current:
    "bg-[var(--accent-core-subtle)] text-[var(--accent-core)] ring-2 ring-[var(--accent-core)]",
  pending: "bg-[var(--interactive-accent-subtle)] text-[var(--text-meta)]",
  blocked: "bg-[var(--danger-subtle,#fde8e8)] text-[var(--danger,#b42318)]",
};

function StepList({ statuses }: { statuses: Record<string, StepStatus> }) {
  return (
    <ol className="list-none m-0 p-0 flex flex-col gap-3">
      {STEPS.map((step, index) => {
        const status = statuses[step.id] ?? "pending";
        return (
          <li key={step.id} className="flex gap-3 items-start">
            <span
              className={`shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-full text-[13px] font-semibold ${STEP_DOT[status]}`}
              aria-hidden
            >
              {status === "done" ? "✓" : status === "blocked" ? "!" : index + 1}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-[var(--foreground)]">
                {step.label}
                <span className="sr-only"> — {status}</span>
              </span>
              <span className="block text-[13px] text-[var(--text-meta)]">{step.detail}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export default function SourceOnboarding() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const notify = useNotify();

  const [project, setProject] = useState<WizardProject | null>(null);
  const [run, setRun] = useState<WizardRunStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [resumeId, setResumeId] = useState("");
  const [scopeText, setScopeText] = useState(
    '{\n  "jurisdiction_id": "",\n  "authority_id": ""\n}',
  );
  const [planText, setPlanText] = useState(
    '{\n  "overlay_id": "",\n  "provider_template_id": ""\n}',
  );

  useEffect(() => {
    setResumeId(readLastProjectId() ?? "");
  }, []);

  const loadProject = useCallback(
    async (id: string) => {
      try {
        const loaded = await controlPlaneActions.getWizardProject(id);
        setProject(loaded);
        rememberProjectId(id);
        if (Object.keys(loaded.scope).length > 0) {
          setScopeText(JSON.stringify(loaded.scope, null, 2));
        }
        if (Object.keys(loaded.discovery_plan).length > 0) {
          setPlanText(JSON.stringify(loaded.discovery_plan, null, 2));
        }
      } catch (error) {
        notify(error instanceof Error ? error.message : "Could not load that project.", {
          type: "error",
        });
      }
    },
    [notify],
  );

  useEffect(() => {
    if (projectId) void loadProject(projectId);
  }, [projectId, loadProject]);

  const statuses = resolveStepStatuses(project, run);

  const parseOrNotify = (text: string, what: string): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(text);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        notify(`${what} must be a JSON object.`, { type: "warning" });
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch {
      notify(`${what} is not valid JSON.`, { type: "warning" });
      return null;
    }
  };

  const withBusy = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (error) {
      notify(error instanceof Error ? error.message : "That action failed.", { type: "error" });
    } finally {
      setBusy(false);
    }
  };

  // ---- No project yet: start or resume -----------------------------------
  if (!projectId) {
    return (
      <section className="max-w-[720px]">
        <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-1">Onboard a source</h1>
        <p className="text-sm text-[var(--text-meta)] mt-0 mb-6">
          Scope, plan, pilot, decide, scale — the loop that crosses every section. Backed by the
          wizard run ledger, so each step leaves a record.
        </p>

        <div className="rounded-[14px] border border-[var(--border)] p-4 mb-4">
          <h2 className="text-base font-semibold m-0 mb-3">Start a new one</h2>
          <label className="block text-sm font-medium mb-1" htmlFor="wizard-name">
            Project name
          </label>
          <input
            id="wizard-name"
            className="w-full rounded-[10px] border border-[var(--border)] px-3 py-2 text-sm bg-[var(--surface-panel)] text-[var(--foreground)]"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. ZH cantonal statutes"
          />
          <button
            type="button"
            disabled={busy || name.trim().length === 0}
            className="mt-3 inline-flex items-center rounded-[10px] px-3 py-2 text-sm font-semibold bg-[var(--accent-core)] text-white disabled:opacity-50"
            onClick={() =>
              void withBusy(async () => {
                const created = await controlPlaneActions.createWizardProject(name.trim());
                rememberProjectId(created.wizard_project_id);
                navigate(`/workflows/onboard/${created.wizard_project_id}`);
              })
            }
          >
            Create project
          </button>
        </div>

        <div className="rounded-[14px] border border-[var(--border)] p-4">
          <h2 className="text-base font-semibold m-0 mb-1">Resume one</h2>
          <p className="text-[13px] text-[var(--text-meta)] mt-0 mb-3">
            The API has no endpoint that lists wizard projects, so there is no index to browse —
            paste an id, or use the last one this browser saw.
          </p>
          <input
            aria-label="Wizard project id"
            className="w-full rounded-[10px] border border-[var(--border)] px-3 py-2 text-sm font-mono bg-[var(--surface-panel)] text-[var(--foreground)]"
            value={resumeId}
            onChange={(event) => setResumeId(event.target.value)}
            placeholder="wpr_…"
          />
          <button
            type="button"
            disabled={resumeId.trim().length === 0}
            className="mt-3 inline-flex items-center rounded-[10px] px-3 py-2 text-sm font-semibold border border-[var(--border)] disabled:opacity-50"
            onClick={() => navigate(`/workflows/onboard/${resumeId.trim()}`)}
          >
            Resume
          </button>
        </div>
      </section>
    );
  }

  // ---- A project is open: the stepper ------------------------------------
  return (
    <section className="max-w-[840px]">
      <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-1">
        {project?.name ?? "Onboarding"}
      </h1>
      <p className="text-[13px] font-mono text-[var(--text-meta)] mt-0 mb-6">{projectId}</p>

      <div className="grid gap-6 md:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="rounded-[14px] border border-[var(--border)] p-4 h-fit">
          <StepList statuses={statuses} />
        </aside>

        <div className="min-w-0 flex flex-col gap-4">
          <div className="rounded-[14px] border border-[var(--border)] p-4">
            <h2 className="text-base font-semibold m-0 mb-1">1 · Scope</h2>
            <p className="text-[13px] text-[var(--text-meta)] mt-0 mb-2">
              Which jurisdiction and authority this source belongs to.
            </p>
            <textarea
              aria-label="Scope JSON"
              rows={5}
              className="w-full rounded-[10px] border border-[var(--border)] px-3 py-2 text-[13px] font-mono bg-[var(--surface-panel)] text-[var(--foreground)]"
              value={scopeText}
              onChange={(event) => setScopeText(event.target.value)}
            />
            <button
              type="button"
              disabled={busy}
              className="mt-2 inline-flex items-center rounded-[10px] px-3 py-2 text-sm font-semibold border border-[var(--border)] disabled:opacity-50"
              onClick={() =>
                void withBusy(async () => {
                  const scope = parseOrNotify(scopeText, "Scope");
                  if (!scope) return;
                  setProject(await controlPlaneActions.saveWizardScope(projectId, scope));
                  notify("Scope saved.", { type: "success" });
                })
              }
            >
              Save scope
            </button>
          </div>

          <div className="rounded-[14px] border border-[var(--border)] p-4">
            <h2 className="text-base font-semibold m-0 mb-1">2 · Discovery plan</h2>
            <p className="text-[13px] text-[var(--text-meta)] mt-0 mb-2">
              Which blueprint template to acquire through. A template is a pre-approved provider
              configuration — see Blueprints under BUILD.
            </p>
            <textarea
              aria-label="Discovery plan JSON"
              rows={5}
              className="w-full rounded-[10px] border border-[var(--border)] px-3 py-2 text-[13px] font-mono bg-[var(--surface-panel)] text-[var(--foreground)]"
              value={planText}
              onChange={(event) => setPlanText(event.target.value)}
            />
            <button
              type="button"
              disabled={busy}
              className="mt-2 inline-flex items-center rounded-[10px] px-3 py-2 text-sm font-semibold border border-[var(--border)] disabled:opacity-50"
              onClick={() =>
                void withBusy(async () => {
                  const plan = parseOrNotify(planText, "Discovery plan");
                  if (!plan) return;
                  setProject(await controlPlaneActions.saveWizardDiscoveryPlan(projectId, plan));
                  notify("Discovery plan saved.", { type: "success" });
                })
              }
            >
              Save discovery plan
            </button>
          </div>

          <div className="rounded-[14px] border border-[var(--border)] p-4">
            <h2 className="text-base font-semibold m-0 mb-1">3 · Pilot run</h2>
            <p className="text-[13px] text-[var(--text-meta)] mt-0 mb-2">
              A sample acquisition against the live source. This is evidence for the decision below,
              not production ingest.
            </p>
            <ConfirmButton
              tier="notable"
              confirmTitle="Start a pilot run?"
              confirmDescription="This fetches a sample from the live upstream source. Make sure the scope and discovery plan are right first."
              disabled={busy}
              onConfirm={() =>
                withBusy(async () => {
                  const started = await controlPlaneActions.startWizardPilotRun(projectId, 5);
                  setRun(started);
                  notify("Pilot run started.", { type: "success" });
                })
              }
            >
              Start pilot run
            </ConfirmButton>
            {run ? (
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[13px] m-0">
                <dt className="text-[var(--text-meta)]">Run</dt>
                <dd className="font-mono m-0">{run.wizard_run_id}</dd>
                <dt className="text-[var(--text-meta)]">State</dt>
                <dd className="m-0 font-semibold">{run.state}</dd>
                <dt className="text-[var(--text-meta)]">Processed</dt>
                <dd className="m-0">
                  {run.progress.processed_nodes} / {run.progress.total_nodes}
                </dd>
                <dt className="text-[var(--text-meta)]">Review backlog</dt>
                <dd className="m-0">{run.quality.review_backlog}</dd>
              </dl>
            ) : null}
          </div>

          <div className="rounded-[14px] border border-[var(--border)] p-4">
            <h2 className="text-base font-semibold m-0 mb-1">4 · Decision</h2>
            <p className="text-[13px] text-[var(--text-meta)] mt-0 mb-3">{describeRunState(run)}</p>

            {run && run.state === "HumanGateApproval" ? (
              <div className="flex gap-2 flex-wrap">
                <ConfirmButton
                  tier="notable"
                  confirmTitle="Approve this pilot?"
                  confirmDescription="Approving releases the full run against the live source. Read the pilot's results first."
                  disabled={busy}
                  onConfirm={() =>
                    withBusy(async () => {
                      setRun(await controlPlaneActions.approveWizardRun(run.wizard_run_id));
                      notify("Approved. Scaling.", { type: "success" });
                    })
                  }
                >
                  Approve and scale
                </ConfirmButton>
                <ConfirmButton
                  tier="destructive"
                  confirmTitle="Reject this pilot?"
                  confirmDescription="The run stops here and nothing scales. Restarting means a fresh pilot."
                  disabled={busy}
                  onConfirm={() =>
                    withBusy(async () => {
                      setRun(await controlPlaneActions.rejectWizardRun(run.wizard_run_id));
                      notify("Rejected.", { type: "info" });
                    })
                  }
                >
                  Reject
                </ConfirmButton>
              </div>
            ) : null}

            {isTerminal(run?.state) && run ? (
              <ConfirmButton
                tier="notable"
                confirmTitle="Start a fresh pilot run?"
                confirmDescription="The expired run stays terminal. This starts a NEW run on the same project, keeping the scope and discovery plan."
                disabled={busy}
                onConfirm={() =>
                  withBusy(async () => {
                    // Returns the NEW run — re-point at it, don't keep the old id.
                    setRun(await controlPlaneActions.restartWizardRun(run.wizard_run_id));
                    notify("Fresh pilot run started.", { type: "success" });
                  })
                }
              >
                Restart with a fresh pilot
              </ConfirmButton>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
