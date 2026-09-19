#!/usr/bin/env bash
#
# Run one quality gate and report PASS / FAIL / DID-NOT-RUN honestly.
#
# WHY THIS EXISTS
# ---------------
# On 2026-09-19 a gate was run as `... | tail -40`. The suite failed; `tail`
# exited 0; the shell reported 0; the run was recorded as green. Nothing about
# that is exotic — a pipeline's exit status is its LAST command's, so every
# `gate | tail`, `gate | head`, `gate | grep` silently launders a failure into a
# success. It happened repeatedly in one session before anyone noticed, and it
# was noticed by luck.
#
# `set -o pipefail` fixes the exit status, but nobody types it in an ad-hoc
# pipeline. So the fix is not a rule, it is an entry point: run the gate through
# this script, read the last line, and the last line is the truth regardless of
# what the caller pipes it into.
#
#     bash scripts/run-gate.sh platform-control -- bash scripts/check-platform-control.sh
#     bash scripts/run-gate.sh legal-search-api --dir legal-search/api -- npm run check
#
# The final line is exactly one of:
#
#     PASS gate=<name> exit=0 log=<path>
#     FAIL gate=<name> exit=<status> log=<path>
#     DID-NOT-RUN gate=<name> exit=none log=<path> missing=<what>
#
# and the script's own exit status is 0 for PASS, the command's status for FAIL,
# and 2 for DID-NOT-RUN. DID-NOT-RUN is deliberately NOT 0: a gate whose
# prerequisites were absent did not pass (AGENTS.md, "A gate is evidence only for
# the stages that actually ran"). The common causes are all silent — no Docker
# daemon for the Testcontainers layer, a fresh worktree with no `node_modules`,
# a missing tool — and each one leaves the earlier output looking like success.
#
# Prerequisites: `--requires` states one explicitly; otherwise a small amount is
# inferred from the command (a `docker`/Testcontainers gate needs a daemon, an
# `npm`/`npx` gate needs `node_modules`). Anything not detected is left to the
# command, which is the honest default — this wrapper never claims a gate could
# not run when it simply does not know.

set -uo pipefail

usage() {
  cat >&2 <<'EOF'
usage: run-gate.sh <name> [--dir DIR] [--requires SPEC]... [--log-dir DIR] -- <command> [args...]

  <name>            short label for the gate, used in the report line and log name
  --dir DIR         run the command from DIR (relative to the repo root)
  --requires SPEC   a prerequisite that must hold, else DID-NOT-RUN. One of:
                      docker            a reachable Docker daemon
                      cmd:<name>        an executable on PATH
                      path:<path>       a file or directory that must exist
                      env:<VAR>         a non-empty environment variable
  --log-dir DIR     where to write the full output (default: $EVIDARA_GATE_LOG_DIR
                    or <repo>/.gate-logs)
EOF
}

name=""
work_dir=""
log_dir="${EVIDARA_GATE_LOG_DIR:-}"
requires=()
command_argv=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --) shift; command_argv=("$@"); break ;;
    --dir) work_dir="${2:-}"; shift 2 ;;
    --log-dir) log_dir="${2:-}"; shift 2 ;;
    --requires) requires+=("${2:-}"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "run-gate.sh: unknown option '$1'" >&2; usage; exit 64 ;;
    *)
      if [[ -z "${name}" ]]; then name="$1"; shift; else
        echo "run-gate.sh: unexpected argument '$1' (did you forget '--'?)" >&2
        usage; exit 64
      fi
      ;;
  esac
done

if [[ -z "${name}" || ${#command_argv[@]} -eq 0 ]]; then
  usage
  exit 64
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -n "${log_dir}" ]] || log_dir="${repo_root}/.gate-logs"
mkdir -p "${log_dir}"

safe_name="${name//[^A-Za-z0-9._-]/_}"
log_file="${log_dir}/${safe_name}-$(date -u +%Y%m%dT%H%M%SZ).log"
: >"${log_file}"

run_dir="${repo_root}"
if [[ -n "${work_dir}" ]]; then
  if [[ "${work_dir}" = /* ]]; then run_dir="${work_dir}"; else run_dir="${repo_root}/${work_dir}"; fi
fi

report() {
  # $1 status, $2 exit status (or "none"), $3 optional "missing=" detail
  local status="$1" code="$2" detail="${3:-}"
  local line="${status} gate=${name} exit=${code} log=${log_file}"
  [[ -n "${detail}" ]] && line="${line} ${detail}"
  printf '%s\n' "${line}" | tee -a "${log_file}"
}

did_not_run() {
  report "DID-NOT-RUN" "none" "missing=$1"
  exit 2
}

# ─── Prerequisites: explicit ───
for spec in ${requires+"${requires[@]}"}; do
  case "${spec}" in
    docker)
      command -v docker >/dev/null 2>&1 || did_not_run "docker (not on PATH)"
      docker info >/dev/null 2>&1 || did_not_run "docker-daemon (not reachable)"
      ;;
    cmd:*)
      command -v "${spec#cmd:}" >/dev/null 2>&1 || did_not_run "${spec}"
      ;;
    path:*)
      target="${spec#path:}"
      [[ "${target}" = /* ]] || target="${run_dir}/${target}"
      [[ -e "${target}" ]] || did_not_run "${spec}"
      ;;
    env:*)
      var="${spec#env:}"
      [[ -n "${!var:-}" ]] || did_not_run "${spec}"
      ;;
    *)
      echo "run-gate.sh: unknown --requires spec '${spec}'" >&2
      exit 64
      ;;
  esac
done

if [[ ! -d "${run_dir}" ]]; then
  did_not_run "dir:${work_dir:-.}"
fi

# ─── Prerequisites: inferred ───
#
# Only the two that this repo has actually been burned by, and only when they
# are unambiguous. Everything else is left to the command: a wrapper that guesses
# wrong and reports DID-NOT-RUN is as dishonest as one that guesses wrong and
# reports PASS.
flat_command="${command_argv[*]}"

if [[ "${command_argv[0]}" == "npm" || "${command_argv[0]}" == "npx" ]]; then
  if [[ -f "${run_dir}/package.json" && ! -d "${run_dir}/node_modules" ]]; then
    did_not_run "node_modules (run 'npm ci' in ${work_dir:-.})"
  fi
fi

if [[ "${flat_command}" == *"test:integration"* || "${flat_command}" == *"testcontainers"* ]]; then
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    did_not_run "docker-daemon (the Testcontainers layer cannot run without it)"
  fi
fi

if ! command -v "${command_argv[0]}" >/dev/null 2>&1; then
  did_not_run "cmd:${command_argv[0]}"
fi

# ─── Run ───
{
  printf '# gate: %s\n' "${name}"
  printf '# dir:  %s\n' "${run_dir}"
  printf '# cmd:  %s\n' "${flat_command}"
  printf '# utc:  %s\n\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >>"${log_file}"

# pipefail is set at the top, and PIPESTATUS[0] is read regardless — the point of
# this script is that the command's own status survives being piped.
(cd "${run_dir}" && "${command_argv[@]}") 2>&1 | tee -a "${log_file}"
status="${PIPESTATUS[0]}"

if [[ "${status}" -eq 0 ]]; then
  report "PASS" "0"
  exit 0
fi

report "FAIL" "${status}"
exit "${status}"
