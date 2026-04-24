#!/usr/bin/env python3
"""Compute lawyer-journey funnel KPIs from analytics events on stdin.

Reads one JSON object per line (JSONL) from stdin. Each line is a parsed
analytics event matching the catalog at
``contracts/events/legal-search.events.json`` — at minimum ``{"name": str, ...}``
and optionally a ``timestamp`` (ISO-8601) and a ``sessionId`` / ``correlationId``
/ ``userId`` to scope sessions.

Outputs three product-level KPIs to stdout:

* ``Search → focus rate`` — share of ``search.executed`` events followed
  within 5 minutes by a ``result.focused_from_list`` in the same session.
* ``Reset frequency`` — ``filter.reset_all`` events per ``search.executed``.
* ``Refinement depth`` — mean ``search.refined`` events per session.

A **session** is a contiguous sequence of events sharing a session key
(``sessionId`` > ``correlationId`` > ``userId``) with no inactivity gap
longer than 5 minutes. If no session key is present on any event, KPIs are
aggregated globally and a note is printed.

Exit codes:
  0 — success (may report a non-zero skipped-line count on stderr)
  2 — no events ingested (e.g. empty stdin or every line malformed)

Example::

    cat events.jsonl | python3 scripts/lawyer-journey-kpis.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

# Event name constants — kept in lockstep with
# contracts/events/legal-search.events.json. The drift guard in the frontend
# (src/__tests__/analytics-schema.test.ts) enforces agreement on the TS side;
# this script hard-codes the small subset it needs for clarity.
EVENT_SEARCH_EXECUTED = "search.executed"
EVENT_SEARCH_REFINED = "search.refined"
EVENT_RESULT_FOCUSED = "result.focused_from_list"
EVENT_FILTER_RESET_ALL = "filter.reset_all"

# Product-defined thresholds. 5 min matches the Slice 2 acceptance bullet.
FOCUS_WINDOW = timedelta(minutes=5)
SESSION_IDLE_GAP = timedelta(minutes=5)

# Keys tried in order to derive a per-session bucket. The frontend track()
# payload does NOT carry these today (see legal-search/frontend/src/lib/
# analytics.ts), but downstream providers (Plausible/PostHog) typically
# attach one. If none are present, we aggregate globally.
SESSION_KEYS: tuple[str, ...] = ("sessionId", "correlationId", "userId")


@dataclass
class Event:
    name: str
    timestamp: datetime | None
    session_key: str | None
    raw: dict


@dataclass
class KpiResult:
    total_events: int
    total_searches: int
    focused_after_search: int
    reset_all_count: int
    refinement_count: int
    session_count: int
    window_start: datetime | None
    window_end: datetime | None
    had_session_key: bool

    @property
    def focus_rate(self) -> float | None:
        if self.total_searches == 0:
            return None
        return self.focused_after_search / self.total_searches

    @property
    def reset_per_search(self) -> float | None:
        if self.total_searches == 0:
            return None
        return self.reset_all_count / self.total_searches

    @property
    def refinements_per_session(self) -> float | None:
        if self.session_count == 0:
            return None
        return self.refinement_count / self.session_count


# ─── Parsing ───


def _parse_iso(value: str) -> datetime:
    """Parse ISO-8601 with Z or ±HH:MM offset. Raise ValueError otherwise."""
    # fromisoformat in 3.11+ accepts most ISO strings but not a trailing "Z".
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp {value!r} is missing a timezone offset")
    return parsed.astimezone(timezone.utc)


def _session_key(raw: dict) -> str | None:
    for key in SESSION_KEYS:
        value = raw.get(key)
        if isinstance(value, str) and value:
            return f"{key}:{value}"
    return None


def parse_events(
    lines: Iterable[str],
    *,
    stderr=sys.stderr,
) -> tuple[list[Event], int, int]:
    """Parse JSONL lines into Event records.

    Returns (events, skipped_malformed_count, skipped_timestamp_count).
    Malformed JSON and lines missing ``name`` are skipped with a stderr
    warning. Lines with an unparseable timestamp are also skipped; lines
    with no timestamp at all are kept but excluded from the window summary.
    """
    events: list[Event] = []
    malformed = 0
    bad_timestamp = 0
    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            malformed += 1
            print(
                f"[lawyer-journey-kpis] skip line {lineno}: malformed JSON ({exc.msg})",
                file=stderr,
            )
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            malformed += 1
            print(
                f"[lawyer-journey-kpis] skip line {lineno}: missing 'name' field",
                file=stderr,
            )
            continue
        ts_value = raw.get("timestamp")
        ts: datetime | None = None
        if isinstance(ts_value, str) and ts_value:
            try:
                ts = _parse_iso(ts_value)
            except ValueError as exc:
                bad_timestamp += 1
                print(
                    f"[lawyer-journey-kpis] skip line {lineno}: unparseable timestamp ({exc})",
                    file=stderr,
                )
                continue
        events.append(
            Event(
                name=raw["name"],
                timestamp=ts,
                session_key=_session_key(raw),
                raw=raw,
            )
        )
    return events, malformed, bad_timestamp


# ─── KPI computation ───


def _split_sessions(events: Sequence[Event]) -> list[list[Event]]:
    """Group events into sessions.

    Session = contiguous stream of events sharing a session key with no
    idle gap > SESSION_IDLE_GAP. Events without a timestamp can't
    participate in gap detection, so they're attached to the same session
    as the previous event with the same key. If no event in the input
    carries any session key, all events form a single global session.
    """
    if not events:
        return []

    any_keyed = any(e.session_key for e in events)
    if not any_keyed:
        return [list(events)]

    # Stable sort: keyed events by (key, timestamp). Events missing a
    # timestamp sort last within their key.
    def sort_key(e: Event):
        # Order by session key, then timestamp (None = very late).
        return (
            e.session_key or "",
            e.timestamp or datetime.max.replace(tzinfo=timezone.utc),
        )

    sorted_events = sorted(events, key=sort_key)

    sessions: list[list[Event]] = []
    current: list[Event] = []
    current_key: str | None = None
    last_ts: datetime | None = None
    for e in sorted_events:
        new_session = False
        if e.session_key != current_key:
            new_session = True
        elif e.timestamp and last_ts and (e.timestamp - last_ts) > SESSION_IDLE_GAP:
            new_session = True
        if new_session:
            if current:
                sessions.append(current)
            current = []
            current_key = e.session_key
            last_ts = None
        current.append(e)
        if e.timestamp is not None:
            last_ts = e.timestamp
    if current:
        sessions.append(current)
    return sessions


def compute_kpis(events: Sequence[Event]) -> KpiResult:
    """Compute the three KPIs + window summary from parsed events."""
    total_events = len(events)
    total_searches = sum(1 for e in events if e.name == EVENT_SEARCH_EXECUTED)
    reset_all_count = sum(1 for e in events if e.name == EVENT_FILTER_RESET_ALL)
    refinement_count = sum(1 for e in events if e.name == EVENT_SEARCH_REFINED)
    had_session_key = any(e.session_key for e in events)

    sessions = _split_sessions(events)

    # Search → focus rate: count searches followed by a focus within
    # FOCUS_WINDOW in the same session. We order each session by
    # timestamp (events without a timestamp are skipped for this KPI
    # only — they can't be placed relative to a search).
    focused_after_search = 0
    for session in sessions:
        timed = [e for e in session if e.timestamp is not None]
        timed.sort(key=lambda e: e.timestamp)  # type: ignore[arg-type,return-value]
        for i, search in enumerate(timed):
            if search.name != EVENT_SEARCH_EXECUTED:
                continue
            for later in timed[i + 1 :]:
                gap = later.timestamp - search.timestamp  # type: ignore[operator]
                if gap > FOCUS_WINDOW:
                    break
                if later.name == EVENT_RESULT_FOCUSED:
                    focused_after_search += 1
                    break

    timestamps = [e.timestamp for e in events if e.timestamp is not None]
    window_start = min(timestamps) if timestamps else None
    window_end = max(timestamps) if timestamps else None

    return KpiResult(
        total_events=total_events,
        total_searches=total_searches,
        focused_after_search=focused_after_search,
        reset_all_count=reset_all_count,
        refinement_count=refinement_count,
        session_count=len(sessions),
        window_start=window_start,
        window_end=window_end,
        had_session_key=had_session_key,
    )


# ─── Rendering ───


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _format_ratio(value: float | None, unit: str) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f} {unit}"


def _format_window(result: KpiResult) -> str:
    if result.window_start is None or result.window_end is None:
        return "Window: (no timestamped events)"
    days = max(1, (result.window_end.date() - result.window_start.date()).days)
    return (
        f"Window: {result.window_start.date().isoformat()} → "
        f"{result.window_end.date().isoformat()} ({days} day"
        f"{'s' if days != 1 else ''})"
    )


def render(result: KpiResult) -> str:
    lines = [
        "Evidara lawyer-journey KPIs",
        f"Events ingested: {result.total_events:,}",
        _format_window(result),
        "",
    ]
    if not result.had_session_key:
        lines.append("[no session id in events — aggregating globally]")
        lines.append("")

    focus_rate = result.focus_rate
    reset_ratio = result.reset_per_search
    refinements = result.refinements_per_session

    focus_detail = (
        f"({result.focused_after_search} of {result.total_searches} searches led "
        f"to a {EVENT_RESULT_FOCUSED} within 5 min)"
    )
    reset_detail = (
        f"({result.reset_all_count} {EVENT_FILTER_RESET_ALL} events / "
        f"{result.total_searches} searches)"
    )
    session_label = "session" if result.session_count == 1 else "sessions"
    refine_detail = (
        f"({result.refinement_count} {EVENT_SEARCH_REFINED} events across "
        f"{result.session_count} {session_label}; sessions = contiguous activity with "
        "≤ 5 min idle gap)"
    )

    lines.append(f"Search → focus rate:   {_format_pct(focus_rate)}  {focus_detail}")
    lines.append(
        f"Reset frequency:       {_format_ratio(reset_ratio, 'per search')}  {reset_detail}"
    )
    lines.append(
        f"Refinement depth:      {_format_ratio(refinements, 'refinements / session')}  {refine_detail}"
    )
    return "\n".join(lines) + "\n"


# ─── Entrypoint ───


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv  # unused; stdin-driven by contract
    events, malformed, bad_timestamp = parse_events(sys.stdin)
    skipped_total = malformed + bad_timestamp
    if skipped_total:
        print(
            f"[lawyer-journey-kpis] skipped {skipped_total} line(s) "
            f"({malformed} malformed, {bad_timestamp} bad-timestamp)",
            file=sys.stderr,
        )
    if not events:
        print(
            "[lawyer-journey-kpis] no events ingested — refusing to emit empty KPIs",
            file=sys.stderr,
        )
        return 2

    result = compute_kpis(events)
    sys.stdout.write(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
