/**
 * One fetch of `GET /v1/runs/{run_id}/pipeline-health` per run detail page.
 *
 * Lifted out of `RunDetailSectionsV2`'s banner because two surfaces now read it —
 * the stall diagnosis on the overview and the stage list below — and two fetches
 * of one endpoint can disagree with each other mid-render. `run-decision-support`
 * and `runDiagnosis` then derive from the same snapshot, so the page cannot say
 * "publish path disabled" in one panel and show processing events in another.
 *
 * `error` is surfaced rather than swallowed: a failed health read must degrade the
 * stall diagnosis to `unknown`, never to a confident cause derived from zeros.
 */
"use client";

import { useEffect, useState } from "react";
import { controlPlaneActions, type RunPipelineHealth } from "../../lib/admin/dataProvider";

export interface RunPipelineHealthState {
  health: RunPipelineHealth | null;
  isPending: boolean;
  error: unknown;
}

export function useRunPipelineHealth(runId: string | undefined): RunPipelineHealthState {
  const [state, setState] = useState<RunPipelineHealthState>({
    health: null,
    isPending: true,
    error: null,
  });

  useEffect(() => {
    if (!runId) {
      setState({ health: null, isPending: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ health: null, isPending: true, error: null });

    void controlPlaneActions
      .getRunPipelineHealth(runId)
      .then((health) => {
        if (!cancelled) {
          setState({ health, isPending: false, error: null });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ health: null, isPending: false, error });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [runId]);

  return state;
}
