#!/usr/bin/env bash
# Claude Code SessionStart hook — fast situational smoke (target: <5s wall-clock).
# Prints branch + recent commit, warns if on main, spot-checks Python test collection.
set -u

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

branch="$(git branch --show-current 2>/dev/null || echo '(detached)')"
last="$(git log -1 --oneline 2>/dev/null || echo '(no commits)')"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

echo "== evidara session start =="
echo "branch : ${branch}"
echo "last   : ${last}"
echo "dirty  : ${dirty} file(s)"

if [ "${branch}" = "main" ]; then
  echo "warn   : on main — create a feature branch before editing"
fi

# Optional: pytest collect (skipped if uv not available)
if command -v uv >/dev/null 2>&1 && [ -d platform-control ]; then
  collect="$(cd platform-control && timeout 4 uv run pytest --collect-only -q 2>&1 | tail -1 || true)"
  echo "pytest : ${collect:-(skipped)}"
fi

echo "roadmap: issue #279 (see CLAUDE.md for milestone pointers)"
echo "==========================="
