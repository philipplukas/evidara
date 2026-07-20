#!/usr/bin/env bash

fast_loop_next_action() {
  local verdict="${1:-}"
  case "${verdict}" in
    pass)
      printf '%s' 'Attach this block to TAR-239 and roll the judgment into TAR-160.'
      ;;
    provider_failed)
      printf '%s' 'Inspect provider-jobs, preview-summary, and raw-artifacts before widening the slice.'
      ;;
    downstream_failed)
      printf '%s' 'Inspect processing-status, document-lifecycle, and worker/API artifact-event parity before rerunning.'
      ;;
    pipeline_pass_content_suspect)
      printf '%s' 'Keep the slice narrow and tighten the acquisition/content gates before widening.'
      ;;
    *)
      printf '%s' 'Review the run bundle and operator diagnostics before the next attempt.'
      ;;
  esac
}

copy_evidence_to_repo() {
  local summary_path="${1:?missing summary_path}"
  local evidence_md_path="${2:?missing evidence_md_path}"
  local corpus_slug="${3:?missing corpus_slug}"  # e.g. "ch-fedlex", "eu-eurlex"
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local repo_root="${script_dir}/.."
  local evidence_dir="${repo_root}/docs/runbooks/evidence"
  local date_stamp
  date_stamp="$(date -u +%Y-%m-%d)"
  local dest="${evidence_dir}/${corpus_slug}-fast-loop-${date_stamp}.md"

  if [[ ! -d "${evidence_dir}" ]]; then
    echo "warning: evidence directory not found at ${evidence_dir}" >&2
    return 1
  fi

  cp "${evidence_md_path}" "${dest}"
  echo "${dest}"
}

render_fast_loop_evidence_markdown() {
  local summary_path="${1:?missing summary_path}"
  local output_path="${2:?missing output_path}"
  local corpus_label="${3:?missing corpus_label}"
  local environment
  local template_id
  local jurisdiction_id
  local authority_id
  local source_id
  local source_version_id
  local run_id
  local verdict
  local run_dir
  local started_at_utc
  local completed_at_utc
  local max_resources
  local run_mode
  local next_action
  local checks_markdown
  local skipped_gates_markdown
  local skipped_gate_count
  local paste_block

  environment="$(jq -r '.environment // "unknown"' "${summary_path}")"
  template_id="$(jq -r '.template_id // "unknown"' "${summary_path}")"
  jurisdiction_id="$(jq -r '.jurisdiction_id // empty' "${summary_path}")"
  authority_id="$(jq -r '.authority_id // empty' "${summary_path}")"
  source_id="$(jq -r '.source_id // "unknown"' "${summary_path}")"
  source_version_id="$(jq -r '.source_version_id // "unknown"' "${summary_path}")"
  run_id="$(jq -r '.run_id // "unknown"' "${summary_path}")"
  verdict="$(jq -r '.verdict // "unknown"' "${summary_path}")"
  run_dir="$(jq -r '.run_dir // "unknown"' "${summary_path}")"
  started_at_utc="$(jq -r '.started_at_utc // empty' "${summary_path}")"
  completed_at_utc="$(jq -r '.completed_at_utc // empty' "${summary_path}")"
  max_resources="$(jq -r '.max_resources // empty' "${summary_path}")"
  # An acceptance run reaches the live portal to PRODUCE evidence; it does not
  # imply either ADR-0030 key is turned. Evidence that does not say which mode
  # produced it can be read as proof of something it never showed, so the mode is
  # stated rather than left to the reader (#743).
  run_mode="$(jq -r '.run_mode // empty' "${summary_path}")"
  next_action="$(fast_loop_next_action "${verdict}")"

  checks_markdown="$(
    jq -r '.checks | to_entries[] | "- `\(.key)=\(.value)`"' "${summary_path}"
  )"

  # A gate that self-skipped must read as skipped here, not as a pass (#744). The
  # `checks` list above renders `<gate>_ok=1` for a gate that never ran, which is the
  # green-because-it-never-ran failure this repo keeps paying for (#605, #675, #713) —
  # and this markdown is the artifact an operator reads before flipping `enabled: true`
  # under ADR-0030. Scripts that do not emit `skipped_gates` yet get the empty list,
  # so the section stays truthful rather than claiming a coverage they never reported.
  skipped_gate_count="$(jq -r '(.checks.skipped_gates // []) | length' "${summary_path}")"
  if [[ "${skipped_gate_count}" -gt 0 ]]; then
    skipped_gates_markdown="$(
      jq -r '(.checks.skipped_gates // [])[] | "- `\(.)` — **skipped (not applicable to this template)**, not verified"' "${summary_path}"
    )"
  elif jq -e 'has("checks") and (.checks | has("skipped_gates"))' "${summary_path}" >/dev/null; then
    skipped_gates_markdown="- None — every gate below was evaluated."
  else
    skipped_gates_markdown="- Unknown — this run did not report gate coverage."
  fi

  paste_block="$(
    jq -r --arg corpus_label "${corpus_label}" --arg next_action "${next_action}" '
      # `content_type_html_count` predates --expect-content-type and is still emitted by
      # the sibling fast-loop scripts; prefer the corpus-agnostic key when present.
      (.checks.content_type_match_count // .checks.content_type_html_count // 0) as $ct_count
      | (.checks.expect_content_type // "text/html") as $ct_label
      | (.checks.skipped_gates // []) as $skipped
      | [
        "> " + $corpus_label + " fast loop `" + (.template_id // "unknown") + "` on `" + (.environment // "unknown") + "` returned `" + (.verdict // "unknown") + "` (`" + (.run_id // "unknown") + "`).",
        "> Checks: captured=`" + ((.checks.captured_count // 0) | tostring) + "`, raw_artifacts=`" + ((.checks.raw_artifact_count // 0) | tostring) + "`, " + $ct_label + "=`" + ($ct_count | tostring) + "`, DI accepted/processing/canonical_ready=`" + ((.checks.accepted_count // 0) | tostring) + "/" + ((.checks.processing_count // 0) | tostring) + "/" + ((.checks.canonical_ready_count // 0) | tostring) + "`, lifecycle processed=`" + ((.checks.processed_count // 0) | tostring) + "`.",
        "> Run mode: `" + (.run_mode // "unspecified") + "`" + (if (.run_mode // "") == "acceptance" then " — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned." else "." end),
        "> Skipped gates (not verified): " + (if ($skipped | length) > 0 then ($skipped | map("`" + . + "`") | join(", ")) else "none" end) + ".",
        "> Source/version: `" + (.source_id // "unknown") + "` / `" + (.source_version_id // "unknown") + "`.",
        "> Next action: " + $next_action
      ] | join("\n")
    ' "${summary_path}"
  )"

  cat >"${output_path}" <<EOF
# ${corpus_label} Fast Loop Evidence Summary

- Environment: \`${environment}\`
- Template: \`${template_id}\`
- Source: \`${source_id}\`
- Source version: \`${source_version_id}\`
- Run: \`${run_id}\`
- Verdict: \`${verdict}\`
- Max resources: \`${max_resources}\`
- Run mode: \`${run_mode:-unspecified}\`
- Started at (UTC): \`${started_at_utc}\`
- Completed at (UTC): \`${completed_at_utc}\`
- Run dir: \`${run_dir}\`
EOF

  if [[ -n "${jurisdiction_id}" ]]; then
    cat >>"${output_path}" <<EOF
- Jurisdiction: \`${jurisdiction_id}\`
EOF
  fi

  if [[ -n "${authority_id}" ]]; then
    cat >>"${output_path}" <<EOF
- Authority: \`${authority_id}\`
EOF
  fi

  cat >>"${output_path}" <<EOF

## Gate coverage

${skipped_gates_markdown}

## Checks

${checks_markdown}

## TAR-239 / TAR-160 Paste Block

${paste_block}
EOF
}
