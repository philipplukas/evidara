#!/usr/bin/env python3
"""Quantify GitHub Actions queue time vs execution time using the gh CLI.

Workflow-level metrics use each run's createdAt → startedAt (queue) and
startedAt → updatedAt (execution). For multi-job workflows this matches GitHub's
run-level timestamps (execution spans the parallel job window).

Requires: gh authenticated (gh auth login).

Examples:
  ./scripts/analyze_github_actions_queue.py
  ./scripts/analyze_github_actions_queue.py -w "Legal Search" -w "Runtime Images" -L 200
  ./scripts/analyze_github_actions_queue.py --csv
  ./scripts/analyze_github_actions_queue.py --per-job --workflow "Legal Search" -L 15
  ./scripts/analyze_github_actions_queue.py -w "Legal Search" -L 50 --aggregate-jobs
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _gh_json(args: list[str]) -> Any:
    proc = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def _default_repo() -> str:
    data = _gh_json(["repo", "view", "--json", "nameWithOwner"])
    nwo = data.get("nameWithOwner") if isinstance(data, dict) else None
    if not isinstance(nwo, str) or "/" not in nwo:
        raise SystemExit("Could not resolve repo; pass --repo OWNER/NAME")
    return nwo


@dataclass
class RunRow:
    database_id: int
    workflow_name: str
    conclusion: str | None
    event: str | None
    head_branch: str | None
    queue_s: float
    run_s: float
    total_s: float


def _fetch_runs(
    repo: str,
    *,
    limit: int,
    status: str | None,
    workflows: list[str],
) -> list[dict[str, Any]]:
    base = [
        "run",
        "list",
        "-R",
        repo,
        "-L",
        str(limit),
        "--json",
        "databaseId,workflowName,conclusion,createdAt,startedAt,updatedAt,event,headBranch,status",
    ]
    if status:
        base.extend(["--status", status])

    if len(workflows) == 1:
        args = [*base, "-w", workflows[0]]
        return _gh_json(args)

    rows: list[dict[str, Any]] = _gh_json(base)
    if workflows:
        wanted = set(workflows)
        rows = [r for r in rows if r.get("workflowName") in wanted]
    return rows


def _runs_to_rows(runs: list[dict[str, Any]]) -> list[RunRow]:
    out: list[RunRow] = []
    for r in runs:
        created = _parse_iso(r.get("createdAt"))
        started = _parse_iso(r.get("startedAt"))
        updated = _parse_iso(r.get("updatedAt"))
        if not started or not updated:
            continue
        q = 0.0
        if created:
            q = max(0.0, (started - created).total_seconds())
        run_s = max(0.0, (updated - started).total_seconds())
        wid = r.get("databaseId")
        if wid is None:
            continue
        out.append(
            RunRow(
                database_id=int(wid),
                workflow_name=str(r.get("workflowName") or "unknown"),
                conclusion=r.get("conclusion"),
                event=r.get("event"),
                head_branch=r.get("headBranch"),
                queue_s=q,
                run_s=run_s,
                total_s=q + run_s,
            )
        )
    return out


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _summarize(rows: list[RunRow]) -> dict[str, dict[str, Any]]:
    by_wf: dict[str, list[RunRow]] = defaultdict(list)
    for row in rows:
        by_wf[row.workflow_name].append(row)
    summary: dict[str, dict[str, Any]] = {}
    for wf, items in sorted(by_wf.items()):
        queues = [r.queue_s for r in items]
        runs = [r.run_s for r in items]
        totals = [r.total_s for r in items]
        succ = sum(1 for r in items if r.conclusion == "success")
        summary[wf] = {
            "n": len(items),
            "success": succ,
            "failure": sum(1 for r in items if r.conclusion == "failure"),
            "queue_median_s": _percentile(queues, 50),
            "queue_p90_s": _percentile(queues, 90),
            "run_median_s": _percentile(runs, 50),
            "run_p90_s": _percentile(runs, 90),
            "total_median_s": _percentile(totals, 50),
            "total_p90_s": _percentile(totals, 90),
        }
    return summary


def _job_queue_run_seconds(job: dict[str, Any]) -> tuple[float, float] | None:
    """Return (queue_s, run_s) for a job, or None if skipped or not finished."""
    if job.get("conclusion") == "skipped":
        return None
    c = _parse_iso(job.get("created_at"))
    st = _parse_iso(job.get("started_at"))
    en = _parse_iso(job.get("completed_at"))
    if not st or not en:
        return None
    jq = max(0.0, (st - c).total_seconds()) if c else 0.0
    jr = max(0.0, (en - st).total_seconds())
    return jq, jr


def _fetch_jobs(repo: str, run_id: int) -> list[dict[str, Any]]:
    data = _gh_json(
        [
            "api",
            f"repos/{repo}/actions/runs/{run_id}/jobs",
            "--paginate",
        ]
    )
    if isinstance(data, dict) and "jobs" in data:
        return list(data["jobs"])
    return []


def _print_per_job(repo: str, rows: list[RunRow]) -> None:
    print("\nPer-job detail (queue = created_at → started_at, run = started → completed):\n")
    for row in rows:
        jobs = _fetch_jobs(repo, row.database_id)
        if not jobs:
            print(f"run {row.database_id} ({row.workflow_name}): no jobs returned")
            continue
        print(
            f"run {row.database_id} {row.workflow_name} "
            f"wf_queue={row.queue_s:.0f}s wf_run={row.run_s:.0f}s "
            f"({row.conclusion})"
        )
        job_rows: list[tuple[float, float, str, str | None]] = []
        for j in jobs:
            name = str(j.get("name") or "?")
            concl = j.get("conclusion")
            parsed = _job_queue_run_seconds(j)
            if not parsed:
                continue
            jq, jr = parsed
            job_rows.append((jq, jr, name, concl))
        job_rows.sort(key=lambda t: -(t[0] + t[1]))
        for jq, jr, name, concl in job_rows[:12]:
            print(f"  {name}: queue={jq:.0f}s run={jr:.0f}s ({concl})")
        if len(job_rows) > 12:
            print(f"  ... {len(job_rows) - 12} more jobs")
        print()


def _print_aggregate_jobs(repo: str, rows: list[RunRow]) -> None:
    """Summarize job-level queue and run seconds across all runs (non-skipped jobs)."""
    by_name: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"queue": [], "run": []}
    )
    per_run_max_queue: list[float] = []
    multi_wf = len({r.workflow_name for r in rows}) > 1

    for row in rows:
        jobs = _fetch_jobs(repo, row.database_id)
        queues_this_run: list[float] = []
        for j in jobs:
            parsed = _job_queue_run_seconds(j)
            if not parsed:
                continue
            jq, jr = parsed
            name = str(j.get("name") or "?")
            key = f"{row.workflow_name} / {name}" if multi_wf else name
            queues_this_run.append(jq)
            by_name[key]["queue"].append(jq)
            by_name[key]["run"].append(jr)
        if queues_this_run:
            per_run_max_queue.append(max(queues_this_run))

    print("\n## Job-level aggregate (non-skipped jobs across sample runs)\n")
    if per_run_max_queue:
        pm = _percentile(per_run_max_queue, 50)
        pp = _percentile(per_run_max_queue, 90)
        print(
            "Per-run max job queue_s (largest queue among jobs in each run): "
            f"median={pm:.0f}  p90={pp:.0f}  (n_runs={len(per_run_max_queue)})\n"
        )

    ranked = []
    for name, buckets in by_name.items():
        qs, rs = buckets["queue"], buckets["run"]
        if not qs:
            continue
        ranked.append(
            (
                -(_percentile(qs, 50) or 0),
                name,
                len(qs),
                _percentile(qs, 50),
                _percentile(qs, 90),
                _percentile(rs, 50),
                _percentile(rs, 90),
            )
        )
    ranked.sort()
    print(f"{'job_name':<48} {'n':>5}  {'q_med':>7} {'q_p90':>7}  {'r_med':>7} {'r_p90':>7}")
    for _, name, n, qm, qp, rm, rp in ranked:
        print(
            f"{name:<48} {n:>5}  "
            f"{qm or 0:>7.0f} {qp or 0:>7.0f}  "
            f"{rm or 0:>7.0f} {rp or 0:>7.0f}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-R",
        "--repo",
        help="OWNER/REPO (default: gh repo view)",
    )
    parser.add_argument(
        "-L",
        "--limit",
        type=int,
        default=100,
        help="Max workflow runs to fetch from gh run list (default 100)",
    )
    parser.add_argument(
        "--status",
        default="completed",
        help='gh run status filter (default: "completed"; use "" for any)',
    )
    parser.add_argument(
        "-w",
        "--workflow",
        action="append",
        dest="workflows",
        metavar="NAME",
        help="Filter to workflow display name (repeatable). Default: all in sample",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Emit one CSV row per run to stdout",
    )
    parser.add_argument(
        "--per-job",
        action="store_true",
        help="After summary, fetch jobs API for each run (extra API calls)",
    )
    parser.add_argument(
        "--aggregate-jobs",
        action="store_true",
        help="After summary, fetch jobs for each run and print per-job queue/run percentiles",
    )
    args = parser.parse_args()
    repo = args.repo or _default_repo()
    status = args.status if args.status else None

    runs = _fetch_runs(
        repo,
        limit=args.limit,
        status=status,
        workflows=list(args.workflows or []),
    )
    rows = _runs_to_rows(runs)

    if args.csv:
        w = csv.writer(sys.stdout)
        w.writerow(
            [
                "database_id",
                "workflow",
                "conclusion",
                "event",
                "head_branch",
                "queue_s",
                "run_s",
                "total_s",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.database_id,
                    r.workflow_name,
                    r.conclusion or "",
                    r.event or "",
                    r.head_branch or "",
                    f"{r.queue_s:.1f}",
                    f"{r.run_s:.1f}",
                    f"{r.total_s:.1f}",
                ]
            )
        if args.per_job or args.aggregate_jobs:
            print(
                "Note: --per-job / --aggregate-jobs with --csv is not supported",
                file=sys.stderr,
            )
        return

    print(f"Repo: {repo}")
    print(
        f"Sample: {len(rows)} runs"
        + (f' (status filter: "{status}")' if status else "")
        + f" from gh run list -L {args.limit}\n"
    )
    print(
        "Interpretation: queue_s ≈ time waiting before GitHub started the workflow; "
        "run_s ≈ startedAt → updatedAt (includes parallel jobs).\n"
    )

    summary = _summarize(rows)
    if not summary:
        print("No runs matched.")
        return

    for wf, s in summary.items():
        print(f"## {wf}")
        print(f"  n={s['n']}  success={s['success']}  failure={s['failure']}")
        qm, qp = s["queue_median_s"], s["queue_p90_s"]
        rm, rp = s["run_median_s"], s["run_p90_s"]
        tm, tp = s["total_median_s"], s["total_p90_s"]
        print(
            f"  queue_s:   median={qm:.0f}  p90={qp:.0f}"
            if qm is not None
            else "  queue_s:   (n/a)"
        )
        print(
            f"  run_s:     median={rm:.0f}  p90={rp:.0f}"
            if rm is not None
            else "  run_s:     (n/a)"
        )
        print(
            f"  total_s:   median={tm:.0f}  p90={tp:.0f}"
            if tm is not None
            else "  total_s:   (n/a)"
        )
        print()

    if args.aggregate_jobs:
        _print_aggregate_jobs(repo, rows)

    if args.per_job:
        _print_per_job(repo, rows)


if __name__ == "__main__":
    main()
