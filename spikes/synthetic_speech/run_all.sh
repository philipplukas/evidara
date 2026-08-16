#!/usr/bin/env bash
# Run the whole laboratory and rebuild the report.
#
#   bash run_all.sh            full corpora (tens of minutes)
#   bash run_all.sh --quick    small corpora, for a smoke run
#
# Every experiment is independent and deterministic given --seed, so a single one can be
# re-run on its own and the report rebuilt from whatever JSON is present.
set -euo pipefail
cd "$(dirname "$0")"

ARGS=("$@")

echo "== tests =="
uv run pytest -q

for exp in experiments/0*.py; do
  echo
  echo "== ${exp} =="
  uv run python "${exp}" "${ARGS[@]}"
done

echo
echo "== report =="
uv run python experiments/build_report.py
