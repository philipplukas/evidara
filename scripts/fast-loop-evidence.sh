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
  local next_action
  local checks_markdown
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
  next_action="$(fast_loop_next_action "${verdict}")"

  checks_markdown="$(
    jq -r '.checks | to_entries[] | "- `\(.key)=\(.value)`"' "${summary_path}"
  )"

  paste_block="$(
    jq -r --arg corpus_label "${corpus_label}" --arg next_action "${next_action}" '
      [
        "> " + $corpus_label + " fast loop `" + (.template_id // "unknown") + "` on `" + (.environment // "unknown") + "` returned `" + (.verdict // "unknown") + "` (`" + (.run_id // "unknown") + "`).",
        "> Checks: captured=`" + ((.checks.captured_count // 0) | tostring) + "`, raw_artifacts=`" + ((.checks.raw_artifact_count // 0) | tostring) + "`, html=`" + ((.checks.content_type_html_count // 0) | tostring) + "`, DI accepted/processing/canonical_ready=`" + ((.checks.accepted_count // 0) | tostring) + "/" + ((.checks.processing_count // 0) | tostring) + "/" + ((.checks.canonical_ready_count // 0) | tostring) + "`, lifecycle processed=`" + ((.checks.processed_count // 0) | tostring) + "`.",
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

## Checks

${checks_markdown}

## TAR-239 / TAR-160 Paste Block

${paste_block}
EOF
}
