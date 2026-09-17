#!/usr/bin/env bash
# The cantonal rung's deployed-environment loop driver.
#
# WHY THIS EXISTS. Every fast-loop driver in this repo targeted a federal or foreign
# corpus — fedlex, bger, at-ris, de-bundesrecht, eu-eurlex, legifrance — and none
# targeted LexFind. That is why every piece of cantonal acceptance evidence in
# `docs/runbooks/evidence/` records `Environment: compose-local`: the cantonal rung
# had no path to a deployed environment at all, while `lexfind_api` was `live` and
# covered 26 cantons plus Bund behind one API.
#
# WHY IT IS A WRAPPER AND NOT A FIFTH COPY. `ch-fedlex-fast-loop.sh` is already the
# general driver — its own header says the corpus expectations "are flags so that a
# non-Fedlex corpus (a municipal PDF source, say) is measured against its own shape".
# It is misnamed rather than Fedlex-specific. `ch-bger-fast-loop.sh` is a 536-line
# sibling copy of it, and a third copy would be the drift this repo keeps paying for
# in mapping files. So this sets the cantonal defaults and delegates; everything the
# loop does lives in one implementation.
#
# What it cannot do yet: `--mode production`. The delegate checks run readiness
# BEFORE its own approve step, and production readiness requires an approved source
# version, so production always exits 1 for a fresh source (#998). `acceptance` is
# the working mode and is what the ADR-0030 evidence workflow wants anyway.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TEMPLATE_ID="lexfind_api_zh_full"
JURISDICTION_ID="jur_ch_zh"
AUTHORITY_ID="auth_zh_sk"
SOURCE_NAME="CH LexFind cantonal fast-loop source"
CORPUS_SLUG="ch-lexfind"
CORPUS_LABEL="CH LexFind"
EXPECT_LANGUAGE="de"

usage() {
  cat <<'USAGE'
Usage: scripts/ch-lexfind-fast-loop.sh [options]

Runs the acquisition->evidence loop for a LexFind cantonal template against a
deployed environment. Thin wrapper over ch-fedlex-fast-loop.sh, which owns the loop.

Defaults (override with the same flags the delegate takes):
  --template          lexfind_api_zh_full
  --jurisdiction-id   jur_ch_zh
  --authority-id      auth_zh_sk
  --expect-language   de
  content type        application/pdf
  url pattern         lexfind\.ch/

Another canton: pass --template, --jurisdiction-id and --authority-id together.
Evidence binds to the TEMPLATE, not the provider (#846), so one canton's run does
not satisfy the enablement check for the other 25.

  bash scripts/ch-lexfind-fast-loop.sh \
    --pc-url http://127.0.0.1:8000 --ls-url http://127.0.0.1:3102 \
    --api-key "$(kubectl -n evidara get secret evidara-auth \
        -o jsonpath='{.data.PLATFORM_CONTROL_OPERATOR_API_KEY}' | base64 -d)" \
    --mode acceptance --max-resources 25

NOTE ON --expect-title. Deliberately NOT defaulted. `lexfind_api_zh_full` enumerates
a whole canton, so there is no single title the run should produce, and passing a
catch-all would report `title_checked=1` while asserting nothing — the shape of green
this repo keeps getting burned by. Pass one for a NARROW template
(`--template lexfind_api_zh_tierschutz --expect-title 'Tierschutz|Hunde'`), and leave
it unset for a whole-canton run, where `title_checked=0` is the honest answer.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

# The URL pattern asserts the HOST and nothing finer, on purpose. LexFind returns
# either a direct `.pdf` URL from the record or the `/tol/{id}/{lang}` fallback
# (`lexfind_api_provider.py:1358`), so pinning one shape would fail on whichever the
# API happened to return. The host IS the meaningful assertion for a mirror: it
# proves the bytes came from the mirror the compliance policy names. Whether the
# bytes match the canton's own copy is a separate, stronger check the provider
# already makes per run (md5 mirror spot-check).
# A LexFind capture is a PDF, so the canonical text only exists after an
# extraction step and the projection lands later than it does for an HTML corpus.
# The delegate's 12-poll default left a 7-document run still unqueryable at 60s
# and fully queryable shortly after, which reported the indexed-language and
# indexed-title gates NOT EVALUATED — a hole, and enough to disqualify an
# otherwise clean run as acceptance evidence (#744). Passed BEFORE "$@" so a
# caller can still override it.
exec "${SCRIPT_DIR}/ch-fedlex-fast-loop.sh" \
  --readback-polls 60 \
  --template "${TEMPLATE_ID}" \
  --expect-content-type "application/pdf" \
  --url-pattern 'lexfind\.ch/' \
  --jurisdiction-id "${JURISDICTION_ID}" \
  --authority-id "${AUTHORITY_ID}" \
  --source-name "${SOURCE_NAME}" \
  --corpus-slug "${CORPUS_SLUG}" \
  --corpus-label "${CORPUS_LABEL}" \
  --expect-language "${EXPECT_LANGUAGE}" \
  "$@"
