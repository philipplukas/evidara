#!/usr/bin/env python3
"""Emit a local machine-readable GA lane rollup from repo runbooks."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
BOARD_PATH = REPO_ROOT / "docs/runbooks/ga-operator-board.md"


@dataclass(frozen=True)
class LaneConfig:
    lane_id: str
    board_title: str
    title: str
    primary_doc: str
    evidence_paths: tuple[str, ...]
    blocker_override: str | None = None
    next_action_override: str | None = None


LANES: tuple[LaneConfig, ...] = (
    LaneConfig(
        lane_id="TAR-214",
        board_title="Release evidence refresh",
        title="Release evidence refresh",
        primary_doc="docs/runbooks/tar-214-release-evidence-refresh.md",
        evidence_paths=(
            "docs/runbooks/phase-5-go-no-go-memo.md",
            "docs/runbooks/evidence/2026-04-13-dev-mvp-acceptance-run1.json",
            "docs/runbooks/tar-77-evidence-prep.md",
        ),
        blocker_override=(
            "The release packet is still incomplete until TAR-77 branch-protection proof, "
            "TAR-64 smoke evidence, TAR-85 acceptance evidence, and the TAR-69 synthesis are "
            "all refreshed and re-linked."
        ),
    ),
    LaneConfig(
        lane_id="TAR-70",
        board_title="Gate policy hardening",
        title="Gate policy hardening",
        primary_doc="docs/runbooks/tar-70-gate-policy-hardening.md",
        evidence_paths=(
            "docs/runbooks/tar-70-emitted-check-matrix.md",
            "docs/setup/branch-rules.md",
        ),
        blocker_override=(
            "The branch-gate model is still recovering from merge-wave drift and needs one "
            "agreed steady-state rule set that matches emitted checks."
        ),
    ),
    LaneConfig(
        lane_id="TAR-238",
        board_title="Runner reliability",
        title="Runner reliability",
        primary_doc="docs/runbooks/runner-trust-verification-checklist.md",
        evidence_paths=(
            "docs/runbooks/ci-actions-duration-metrics.md",
            "docs/runbooks/github-app-proof-rerun-checklist.md",
        ),
        blocker_override=(
            "Runner stability is improved, but the pool is not yet treated as fully solved or "
            "trusted for release evidence without continued preflight verification."
        ),
    ),
    LaneConfig(
        lane_id="TAR-239",
        board_title="Five-country acceptance A (CH + AT)",
        title="Five-country acceptance A (CH + AT)",
        primary_doc="docs/runbooks/five-country-acceptance-a.md",
        evidence_paths=(
            "docs/runbooks/evidence/2026-04-13-ch-fedlex-sparql-preview-run1.md",
            "docs/runbooks/evidence/2026-04-14-at-ris-fast-loop-run1.md",
            "docs/runbooks/ch-at-thin-slice-execution.md",
        ),
        blocker_override=(
            "CH and AT now have live fast-loop proof; the remaining work is rolling the evidence "
            "cleanly into the GA packet and deciding whether to widen further or move on."
        ),
    ),
    LaneConfig(
        lane_id="TAR-240",
        board_title="Five-country acceptance B (DE + FR)",
        title="Five-country acceptance B (DE + FR)",
        primary_doc="docs/runbooks/five-country-acceptance-de-fr.md",
        evidence_paths=(),
        blocker_override=(
            "The DE/FR lane is ready but still evidence-oriented: the checklist exists, but "
            "live acceptance evidence has not yet been attached into TAR-160."
        ),
    ),
    LaneConfig(
        lane_id="TAR-241",
        board_title="Relevance baseline",
        title="Relevance baseline",
        primary_doc="docs/runbooks/search-relevance-baseline.md",
        evidence_paths=(
            "docs/runbooks/evidence/2026-04-13-dev-relevance-pack.md",
            "docs/runbooks/staging-relevance-query-pack-suggestions.md",
        ),
        blocker_override=(
            "The current dev relevance signal no longer has an empty q=* control row, but the "
            "seed queries still collapse to generic top hits, so the open issue now looks more "
            "like retrieval / projection quality than pure alias emptiness."
        ),
        next_action_override=(
            "Rerun the relevance query pack with the q=* control row, attach the result table, "
            "and route the next step through projection / replay verification before retuning ranking."
        ),
    ),
    LaneConfig(
        lane_id="TAR-160",
        board_title="GA umbrella / final sign-off",
        title="GA umbrella / final sign-off",
        primary_doc="docs/runbooks/ga-operator-board.md",
        evidence_paths=(
            "docs/runbooks/phase-5-go-no-go-memo.md",
            "docs/runbooks/five-country-acceptance-a.md",
            "docs/runbooks/five-country-acceptance-de-fr.md",
        ),
        blocker_override=(
            "Final GA sign-off still depends on the lane inputs being refreshed, attached, and "
            "assembled into one readable end-to-end packet."
        ),
        next_action_override=(
            "Assemble the refreshed TAR-214, TAR-70, TAR-238, TAR-239, TAR-240, and TAR-241 "
            "evidence into one GA sign-off packet and record the release decision."
        ),
    ),
)


DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a local machine-readable GA lane rollup from current repo docs."
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format. JSON is the machine-readable default.",
    )
    parser.add_argument(
        "--output",
        help="Optional file path to write the rendered rollup to.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_iso_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def parse_header_date(text: str, field: str) -> str | None:
    match = re.search(rf"^{re.escape(field)}:\s*(20\d{{2}}-\d{{2}}-\d{{2}})\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def parse_board_statuses(text: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("| Lane | Linear | Status | Push now? | Exit condition |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] == "------":
            continue
        lane_title, linear, status, push_now, exit_condition = cells
        rows[lane_title] = {
            "linear": linear.strip("`"),
            "status": status,
            "push_now": push_now.lower() == "yes",
            "exit_condition": exit_condition,
        }
    return rows


def extract_section(text: str, headings: list[str]) -> str | None:
    heading_pattern = "|".join(re.escape(h) for h in headings)
    match = re.search(
        rf"(?ms)^##+\s+(?:{heading_pattern})\s*$\n(.*?)(?=^##+\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else None


def extract_list_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^[-*]\s+", line):
            items.append(re.sub(r"^[-*]\s+", "", line).strip())
            continue
        if re.match(r"^\d+\.\s+", line):
            items.append(re.sub(r"^\d+\.\s+", "", line).strip())
    return items


def normalize_sentence(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact.rstrip(".") + "."


def pick_blocker(text: str, primary_doc: str, override: str | None) -> str:
    if override:
        return override

    section = extract_section(text, ["Current state", "Current posture", "Notes", "Risks"])
    if section:
        candidates = extract_list_items(section)
    else:
        candidates = [line.strip() for line in text.splitlines() if line.strip().startswith("-")]

    keywords = ("blocked", "blocker", "stale", "pending", "not yet", "still", "missing", "drift", "gap")
    for candidate in candidates:
        lowered = candidate.lower()
        if any(keyword in lowered for keyword in keywords):
            return normalize_sentence(candidate)

    return f"No explicit blocker was auto-extracted from {primary_doc}; inspect the lane note directly."


def pick_next_action(text: str, override: str | None) -> str:
    if override:
        return override

    sections = [
        "Exact next actions",
        "Exact next checks",
        "Next runnable pass",
        "Suggested execution order",
        "Immediate operator actions",
    ]
    for heading in sections:
        section = extract_section(text, [heading])
        if not section:
            continue
        items = extract_list_items(section)
        if items:
            return normalize_sentence(items[0])

    return "Inspect the lane doc and pick the first unresolved checklist item."


def resolve_paths(config: LaneConfig) -> list[Path]:
    paths = [REPO_ROOT / config.primary_doc]
    for relative in config.evidence_paths:
        paths.append(REPO_ROOT / relative)
    return paths


def gather_evidence_anchors(paths: list[Path]) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            anchors.append(
                {
                    "label": path.name,
                    "path": str(path.relative_to(REPO_ROOT)),
                    "exists": False,
                }
            )
            continue
        stat = path.stat()
        anchors.append(
            {
                "label": path.name,
                "path": str(path.relative_to(REPO_ROOT)),
                "exists": True,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
            }
        )
    return anchors


def freshness_from_paths(paths: list[Path]) -> dict[str, Any]:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return {
            "latest_source_path": None,
            "latest_source_date": None,
            "age_days": None,
            "bucket": "unknown",
        }

    latest = max(existing, key=lambda path: path.stat().st_mtime)
    latest_dt = datetime.fromtimestamp(latest.stat().st_mtime).astimezone()
    age_days = (datetime.now().astimezone().date() - latest_dt.date()).days
    if age_days <= 2:
        bucket = "fresh"
    elif age_days <= 7:
        bucket = "aging"
    else:
        bucket = "stale"
    return {
        "latest_source_path": str(latest.relative_to(REPO_ROOT)),
        "latest_source_date": latest_dt.date().isoformat(),
        "age_days": age_days,
        "bucket": bucket,
    }


def collect_inline_links(text: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for label, target in LINK_RE.findall(text):
        if target.startswith("http"):
            links.append({"label": label, "target": target, "type": "url"})
        elif not target.startswith("#"):
            links.append({"label": label, "target": target, "type": "repo-path"})
    return links


def latest_header_date(text: str) -> str | None:
    values = [
        parse_header_date(text, "Last reviewed"),
        parse_header_date(text, "Last verified"),
    ]
    valid = [value for value in values if value]
    if not valid:
        return None
    return max(valid)


def build_rollup() -> dict[str, Any]:
    board_text = read_text(BOARD_PATH)
    board_statuses = parse_board_statuses(board_text)
    board_date = latest_header_date(board_text)

    lanes: list[dict[str, Any]] = []
    for config in LANES:
        primary_path = REPO_ROOT / config.primary_doc
        primary_text = read_text(primary_path)
        board_row = board_statuses.get(config.board_title, {})
        paths = resolve_paths(config)

        lane = {
            "lane_id": config.lane_id,
            "title": config.title,
            "linear": board_row.get("linear", config.lane_id),
            "status": board_row.get("status", "unknown"),
            "push_now": board_row.get("push_now", False),
            "exit_condition": board_row.get("exit_condition"),
            "primary_doc": config.primary_doc,
            "primary_doc_last_verified": latest_header_date(primary_text),
            "freshness": freshness_from_paths(paths),
            "evidence_anchors": gather_evidence_anchors(paths),
            "blocker": pick_blocker(primary_text, config.primary_doc, config.blocker_override),
            "next_action": pick_next_action(primary_text, config.next_action_override),
            "inline_links": collect_inline_links(primary_text)[:8],
        }
        lanes.append(lane)

    ready_count = sum(1 for lane in lanes if lane["status"] in {"ready", "collecting"})
    active_push_count = sum(1 for lane in lanes if lane["status"] == "active" and lane["push_now"])
    overall_next = next(
        (lane["next_action"] for lane in lanes if lane["push_now"]),
        "No active push-now lane was found; inspect the GA operator board directly.",
    )

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "repository_root": str(REPO_ROOT),
        "source_board": {
            "path": str(BOARD_PATH.relative_to(REPO_ROOT)),
            "last_verified": board_date,
        },
        "summary": {
            "lane_count": len(lanes),
            "active_push_now_count": active_push_count,
            "ready_or_collecting_count": ready_count,
            "overall_next_action": overall_next,
        },
        "lanes": lanes,
    }


def render_markdown(rollup: dict[str, Any]) -> str:
    lines = [
        "# GA Status Rollup",
        "",
        f"- Generated at: `{rollup['generated_at']}`",
        f"- Source board: `{rollup['source_board']['path']}`",
        f"- Overall next action: {rollup['summary']['overall_next_action']}",
        "",
        "| Lane | Status | Push now | Freshness | Blocker | Next action |",
        "|------|--------|----------|-----------|---------|-------------|",
    ]
    for lane in rollup["lanes"]:
        freshness = lane["freshness"]["bucket"]
        blocker = lane["blocker"].replace("|", "\\|")
        next_action = lane["next_action"].replace("|", "\\|")
        lines.append(
            f"| `{lane['lane_id']}` | {lane['status']} | "
            f"{'yes' if lane['push_now'] else 'no'} | {freshness} | "
            f"{blocker} | {next_action} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    rollup = build_rollup()
    rendered = (
        json.dumps(rollup, indent=2, sort_keys=False) + "\n"
        if args.format == "json"
        else render_markdown(rollup)
    )

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
