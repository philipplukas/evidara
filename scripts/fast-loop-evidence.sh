#!/usr/bin/env bash

# Resolve a STABLE acceptance source, reusing one if it already exists (#766).
#
# Every fast-loop harness used to POST /v1/sources/with-version unconditionally,
# so each invocation minted a fresh source. The pipeline keys document identity
# off the source (`_document_identity_key`, #652), so a fresh source per run also
# minted a fresh DOCUMENT per run: the same law indexed again, `document_revision: 1`
# on both, indistinguishable in search.
#
# That corrupted the harness's own evidence. `search_hits` is a gate, and a second
# run turned `1` into `2` — reading like broader coverage when it was one law
# counted twice. Re-acquiring under a *stable* source publishes the next revision
# instead, which is what the pipeline was built for.
#
# Sets SOURCE_ID and SOURCE_VERSION_ID. Requires curl_json() and log() from the
# calling script.
resolve_fast_loop_source() {
  local pc_url="${1:?missing pc_url}"
  local source_name="${2:?missing source_name}"
  local run_dir="${3:?missing run_dir}"
  local version_label="${4:?missing version_label}"
  local template_id="${5:?missing template_id}"
  local overlay_id="${6:?missing overlay_id}"
  local create_payload="${7:?missing create_payload}"

  log "==> Resolving acceptance source"
  curl_json "${pc_url}/v1/sources?q=$(printf '%s' "${source_name}" | jq -sRr @uri)&limit=100" \
    | tee "${run_dir}/source-lookup.json" >/dev/null
  SOURCE_ID="$(jq -r --arg name "${source_name}" \
    'first(.data[]? | select(.name == $name) | .source_id // .id) // empty' \
    < "${run_dir}/source-lookup.json")"

  if [[ -n "${SOURCE_ID}" ]]; then
    log "    reusing source ${SOURCE_ID} — re-acquisition publishes the next revision"
    local version_payload
    version_payload="$(jq -n \
      --arg version_label "${version_label}" \
      --arg template_id "${template_id}" \
      --arg overlay_id "${overlay_id}" '{
      version_label: $version_label,
      overlay_id: $overlay_id,
      provider_template_id: $template_id
    }')"
    curl_json -X POST "${pc_url}/v1/sources/${SOURCE_ID}/versions" \
      -H "Content-Type: application/json" \
      -d "${version_payload}" | tee "${run_dir}/create.json" >/dev/null
    SOURCE_VERSION_ID="$(jq -r '.source_version_id // .id // empty' < "${run_dir}/create.json")"
  else
    log "    no existing acceptance source — creating one"
    curl_json -X POST "${pc_url}/v1/sources/with-version" \
      -H "Content-Type: application/json" \
      -d "${create_payload}" | tee "${run_dir}/create.json" >/dev/null
    SOURCE_ID="$(jq -r '.source.source_id // .source.id // .source_id // empty' < "${run_dir}/create.json")"
    SOURCE_VERSION_ID="$(jq -r '.source_version.source_version_id // .source_version.id // .source_version_id // empty' < "${run_dir}/create.json")"
  fi

  if [[ -z "${SOURCE_ID}" || -z "${SOURCE_VERSION_ID}" ]]; then
    echo "error: source resolution did not return source/source_version ids" >&2
    cat "${run_dir}/create.json" >&2
    return 1
  fi
  log "    source_id=${SOURCE_ID} source_version_id=${SOURCE_VERSION_ID}"
}

# --- Gate-coverage ledger (#744, split 2026-09-03) --------------------------------
#
# `skipped_gates` answered WHICH gates did not run and never WHY, and the two reasons
# mean opposite things:
#
#   excluded      — the operator did not ask for the gate (no title regex declared, no
#                   language to assert). Not applicable; the run is still evidence.
#   not_evaluated — the gate was asked for and could not run (legal-search unreachable,
#                   projection never queryable, no processed documents). A hole in the
#                   evidence; the run is NOT ADR-0030 acceptance evidence.
#
# The names are Soda Core v4's `CheckOutcome.EXCLUDED` / `NOT_EVALUATED`, which draws
# this distinction and escalates only the second. The escalation itself is implemented
# once, in `tools/evidara-cli/src/evidara_cli/gate_coverage.py`; these helpers only
# record what happened, and the renderer below only states it.
GATE_LEDGER=()

gate_ledger_reset() { GATE_LEDGER=(); }

# gate_excluded <gate> <reason-slug>
gate_excluded() { GATE_LEDGER+=("${1:?missing gate}|excluded|${2:?missing reason}"); }

# gate_not_evaluated <gate> <reason-slug>
gate_not_evaluated() { GATE_LEDGER+=("${1:?missing gate}|not_evaluated|${2:?missing reason}"); }

gate_ledger_json() {
  jq -nc '[$ARGS.positional[] | split("|") | {gate: .[0], outcome: .[1], reason: .[2]}]' \
    --args "${GATE_LEDGER[@]+"${GATE_LEDGER[@]}"}"
}

# gate_ledger_names_json [outcome] — every gate, or only those with that outcome.
gate_ledger_names_json() {
  local outcome="${1:-}"
  jq -nc --arg outcome "${outcome}" \
    '[$ARGS.positional[] | split("|")
      | select($outcome == "" or .[1] == $outcome) | .[0]]' \
    --args "${GATE_LEDGER[@]+"${GATE_LEDGER[@]}"}"
}

# Log the ledger for the operator watching the run, naming the two outcomes apart.
gate_ledger_log() {
  local entry gate outcome reason
  local not_evaluated=0
  for entry in "${GATE_LEDGER[@]+"${GATE_LEDGER[@]}"}"; do
    IFS='|' read -r gate outcome reason <<< "${entry}"
    if [[ "${outcome}" == "excluded" ]]; then
      log "    - ${gate}: EXCLUDED (${reason}) — not applicable, not asserted"
    else
      log "    - ${gate}: NOT EVALUATED (${reason}) — asked for, could not run"
      not_evaluated=1
    fi
  done
  if [[ "${not_evaluated}" -eq 1 ]]; then
    log "==> Gates were NOT EVALUATED. This bundle is not ADR-0030 acceptance evidence"
    log "    until they run: an unverified gate is not a passed gate (#744)."
  fi
}

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
    downstream_incomplete)
      printf '%s' 'Some captured documents never reached canonical. Compare captured-resources.json against processing-status.json to find which, then raise DI_MAX_POLLS if they were merely slow or inspect the consumer if they were dropped. Do NOT treat this bundle as acceptance evidence.'
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

  # A gate that did not run must read as not-run here, not as a pass (#744). The
  # `checks` list above renders `<gate>_ok=1` for a gate that never ran, which is the
  # green-because-it-never-ran failure this repo keeps paying for (#605, #675, #713) —
  # and this markdown is the artifact an operator reads before flipping `enabled: true`
  # under ADR-0030.
  #
  # Since 2026-09-03 the two reasons are told apart: a gate the operator EXCLUDED (not
  # applicable to this corpus) is a defensible pass, while a gate that was NOT EVALUATED
  # (asked for and could not run) is a hole in the evidence. Normalised here exactly as
  # `tools/evidara-cli/src/evidara_cli/gate_coverage.py` does it, including the
  # conservative legacy read: a bundle carrying `skipped_gates` but no `gate_coverage`
  # predates the split and its reasons are unrecoverable from the file, so every entry
  # is read as NOT EVALUATED — the direction that can only refuse evidence that might
  # have been fine, never accept evidence that is not.
  local gate_ledger_json_normalised
  gate_ledger_json_normalised="$(
    jq -c '(.checks // {}) as $c
      | if ($c.gate_coverage | type) == "array" then
          [ $c.gate_coverage[]
            | {gate: ((.gate // "") | tostring),
               outcome: (if .outcome == "excluded" then "excluded" else "not_evaluated" end),
               reason: ((.reason // "reason_not_recorded") | tostring)}
            | select(.gate != "") ]
        elif ($c.skipped_gates | type) == "array" then
          [ $c.skipped_gates[]
            | {gate: (. | tostring), outcome: "not_evaluated", reason: "reason_not_recorded"}
            | select(.gate != "") ]
        else null
        end' "${summary_path}"
  )"

  if [[ "${gate_ledger_json_normalised}" == "null" ]]; then
    skipped_gates_markdown="- Unknown — this run reported no gate coverage at all. Read every gate below as unverified; this bundle cannot be cited as ADR-0030 acceptance evidence."
  else
    skipped_gates_markdown="$(
      jq -r --argjson ledger "${gate_ledger_json_normalised}" -n '
        [ ($ledger[] | select(.outcome == "excluded")
           | "- `\(.gate)` — **excluded** (`\(.reason)`): deliberately not asserted for this corpus, so it is unverified but not a hole."),
          ($ledger[] | select(.outcome == "not_evaluated")
           | "- `\(.gate)` — **NOT EVALUATED** (`\(.reason)`): asked for and could not run. This is a hole in the evidence, not a pass."),
          (if ($ledger | length) == 0 then "- None — every gate below was evaluated." else empty end),
          (if ([$ledger[] | select(.outcome == "not_evaluated")] | length) > 0
           then "\nAt least one gate was NOT EVALUATED, so this bundle is not ADR-0030 acceptance evidence until it runs (#744)."
           else empty end)
        ] | join("\n")'
    )"
  fi

  paste_block="$(
    jq -r --arg corpus_label "${corpus_label}" --arg next_action "${next_action}" \
      --argjson ledger "${gate_ledger_json_normalised}" '
      # `content_type_html_count` predates --expect-content-type and is still emitted by
      # the sibling fast-loop scripts; prefer the corpus-agnostic key when present.
      (.checks.content_type_match_count // .checks.content_type_html_count // 0) as $ct_count
      | (.checks.expect_content_type // "text/html") as $ct_label
      | [($ledger // [])[] | select(.outcome == "excluded") | .gate] as $excluded
      | [($ledger // [])[] | select(.outcome == "not_evaluated") | .gate] as $not_evaluated
      | [
        "> " + $corpus_label + " fast loop `" + (.template_id // "unknown") + "` on `" + (.environment // "unknown") + "` returned `" + (.verdict // "unknown") + "` (`" + (.run_id // "unknown") + "`).",
        "> Checks: captured=`" + ((.checks.captured_count // 0) | tostring) + "`, raw_artifacts=`" + ((.checks.raw_artifact_count // 0) | tostring) + "`, " + $ct_label + "=`" + ($ct_count | tostring) + "`, DI accepted/processing/canonical_ready=`" + ((.checks.accepted_count // 0) | tostring) + "/" + ((.checks.processing_count // 0) | tostring) + "/" + ((.checks.canonical_ready_count // 0) | tostring) + "`, lifecycle processed=`" + ((.checks.processed_count // 0) | tostring) + "`.",
        "> Run mode: `" + (.run_mode // "unspecified") + "`" + (if (.run_mode // "") == "acceptance" then " — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned." else "." end),
        (if $ledger == null
         then "> Gate coverage: NOT REPORTED by this run — every gate below is unverified, so this run is NOT ADR-0030 acceptance evidence."
         else "> Gates excluded (not applicable, not asserted): " + (if ($excluded | length) > 0 then ($excluded | map("`" + . + "`") | join(", ")) else "none" end) + "."
         end),
        (if $ledger == null
         then empty
         else "> Gates NOT EVALUATED (asked for, could not run): " + (if ($not_evaluated | length) > 0 then ($not_evaluated | map("`" + . + "`") | join(", ")) + " — this run is NOT ADR-0030 acceptance evidence." else "none." end)
         end),
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
