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
            c = _parse_iso(j.get("created_at"))
            st = _parse_iso(j.get("started_at"))
            en = _parse_iso(j.get("completed_at"))
            name = str(j.get("name") or "?")
            concl = j.get("conclusion")
            if not st or not en:
                continue
            jq = max(0.0, (st - c).total_seconds()) if c else 0.0
            jr = max(0.0, (en - st).total_seconds())
            job_rows.append((jq, jr, name, concl))
        job_rows.sort(key=lambda t: -(t[0] + t[1]))
        for jq, jr, name, concl in job_rows[:12]:
            print(f"  {name}: queue={jq:.0f}s run={jr:.0f}s ({concl})")
        if len(job_rows) > 12:
            print(f"  ... {len(job_rows) - 12} more jobs")
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
        if args.per_job:
            print(
                "Note: --per-job with --csv is not supported; run without --csv",
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

    if args.per_job:
        _print_per_job(repo, rows)


if __name__ == "__main__":
    main()
