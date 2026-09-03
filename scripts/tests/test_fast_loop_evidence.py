"""Gate-coverage rendering in `scripts/fast-loop-evidence.sh` (#744).

The evidence markdown these tests exercise is the artifact an operator reads before
flipping `enabled: true` under ADR-0030. A gate that did not run must read as not-run
there — reporting it as a pass is the green-because-it-never-ran defect this repo keeps
paying for (#605, #675, #713).

Since 2026-09-03 that is two claims, not one. A gate the operator EXCLUDED (no title
pattern to assert for this corpus) is unverified but not a hole; a gate that was NOT
EVALUATED (asked for, and legal-search was unreachable) is a hole, and the run is not
acceptance evidence. The single `skipped_gates` list rendered both as "skipped (not
applicable to this template)" — which is a false statement about the second.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_LIB = REPO_ROOT / "scripts" / "fast-loop-evidence.sh"


def render(summary: dict) -> str:
    """Source the shell library and render `summary` to evidence markdown."""
    with tempfile.TemporaryDirectory() as tmp:
        summary_path = Path(tmp) / "summary.json"
        output_path = Path(tmp) / "evidence-summary.md"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{EVIDENCE_LIB}" && '
                f'render_fast_loop_evidence_markdown "{summary_path}" "{output_path}" "CH Fedlex"',
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"render failed: {result.stderr}")
        return output_path.read_text(encoding="utf-8")


BASE_CHECKS = {
    "captured_count": 3,
    "raw_artifact_count": 3,
    "accepted_count": 3,
    "processing_count": 3,
    "canonical_ready_count": 3,
    "processed_count": 3,
}


def summary(**checks: object) -> dict:
    return {
        "environment": "dev",
        "template_id": "gemeinde_http_zh_stadt_hundevorschriften",
        "source_id": "src_1",
        "source_version_id": "sv_1",
        "run_id": "run_1",
        "verdict": "pass",
        "checks": {**BASE_CHECKS, **checks},
    }


def ledger(*entries: tuple[str, str, str]) -> dict:
    """A `gate_coverage` ledger plus its union, as the harnesses emit both."""
    return {
        "gate_coverage": [
            {"gate": gate, "outcome": outcome, "reason": reason}
            for gate, outcome, reason in entries
        ],
        "skipped_gates": [gate for gate, _outcome, _reason in entries],
    }


class GateCoverageTests(unittest.TestCase):
    def test_an_excluded_gate_reads_as_excluded_and_carries_its_reason(self) -> None:
        markdown = render(
            summary(**ledger(("title_ok", "excluded", "no_expected_title_declared")))
        )

        self.assertIn("## Gate coverage", markdown)
        self.assertIn("`title_ok` — **excluded** (`no_expected_title_declared`)", markdown)
        # Excluded is unverified but not a hole; the bundle stays citable.
        self.assertIn("> Gates NOT EVALUATED (asked for, could not run): none.", markdown)
        self.assertNotIn("not ADR-0030 acceptance evidence", markdown)

    def test_a_not_evaluated_gate_is_named_a_hole_not_an_inapplicable_gate(self) -> None:
        markdown = render(
            summary(**ledger(("indexed_title_ok", "not_evaluated", "no_legal_search_url")))
        )

        self.assertIn(
            "`indexed_title_ok` — **NOT EVALUATED** (`no_legal_search_url`)", markdown
        )
        # The old renderer said "not applicable to this template" here. An unreachable
        # legal-search is not a statement about the template.
        self.assertNotIn("not applicable to this template", markdown)
        self.assertIn("not ADR-0030 acceptance evidence", markdown)

    def test_the_two_outcomes_are_told_apart_in_the_paste_block(self) -> None:
        markdown = render(
            summary(
                **ledger(
                    ("title_ok", "excluded", "no_expected_title_declared"),
                    ("indexed_title_ok", "not_evaluated", "projection_not_queryable"),
                )
            )
        )

        self.assertIn(
            "> Gates excluded (not applicable, not asserted): `title_ok`.", markdown
        )
        self.assertIn(
            "> Gates NOT EVALUATED (asked for, could not run): `indexed_title_ok` — "
            "this run is NOT ADR-0030 acceptance evidence.",
            markdown,
        )

    def test_empty_coverage_reports_full_coverage(self) -> None:
        markdown = render(summary(gate_coverage=[], skipped_gates=[]))

        self.assertIn("None — every gate below was evaluated.", markdown)
        self.assertIn("> Gates excluded (not applicable, not asserted): none.", markdown)
        self.assertIn("> Gates NOT EVALUATED (asked for, could not run): none.", markdown)

    def test_a_legacy_bundle_is_read_as_not_evaluated(self) -> None:
        # A bundle from before the split cannot say WHY a gate is absent. Reading it as
        # excluded would upgrade an unknown into a pass; reading it as NOT EVALUATED can
        # only refuse evidence that might have been fine. Same rule as
        # `tools/evidara-cli/src/evidara_cli/gate_coverage.py`.
        markdown = render(summary(skipped_gates=["title_ok"]))

        self.assertIn("`title_ok` — **NOT EVALUATED** (`reason_not_recorded`)", markdown)
        self.assertIn("not ADR-0030 acceptance evidence", markdown)

    def test_a_legacy_bundle_with_an_empty_list_still_reads_as_full_coverage(self) -> None:
        # Why the conservative read costs nothing: every bundle persisted under
        # docs/runbooks/evidence/ reports `skipped_gates: []`, which means the same
        # thing under both readings.
        markdown = render(summary(skipped_gates=[]))

        self.assertIn("None — every gate below was evaluated.", markdown)
        self.assertIn("> Gates NOT EVALUATED (asked for, could not run): none.", markdown)
        self.assertNotIn("not ADR-0030 acceptance evidence", markdown)

    def test_run_without_the_key_is_unknown_not_covered(self) -> None:
        # The five sibling fast-loop scripts do not emit gate coverage yet. Their
        # evidence must not claim a coverage they never reported.
        markdown = render(summary())

        self.assertIn("Unknown — this run reported no gate coverage at all.", markdown)
        self.assertIn("> Gate coverage: NOT REPORTED by this run", markdown)
        self.assertNotIn("every gate below was evaluated", markdown)


class GateLedgerHelpers(unittest.TestCase):
    """The ledger the harnesses build, exercised without running a harness."""

    def _ledger(self, script: str) -> dict:
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'log() {{ :; }}; source "{EVIDENCE_LIB}"; gate_ledger_reset; {script}; '
                'printf "%s\n%s\n%s\n" "$(gate_ledger_json)" '
                '"$(gate_ledger_names_json excluded)" "$(gate_ledger_names_json not_evaluated)"',
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"ledger failed: {result.stderr}")
        full, excluded, not_evaluated = result.stdout.strip().splitlines()
        return {
            "gate_coverage": json.loads(full),
            "excluded": json.loads(excluded),
            "not_evaluated": json.loads(not_evaluated),
        }

    def test_an_empty_ledger_serialises_as_an_empty_array(self) -> None:
        # `[]` and `null` are different claims: the first says every gate ran.
        self.assertEqual(
            self._ledger(":"),
            {"gate_coverage": [], "excluded": [], "not_evaluated": []},
        )

    def test_each_outcome_lands_in_its_own_list(self) -> None:
        got = self._ledger(
            "gate_excluded title_ok no_expected_title_declared; "
            "gate_not_evaluated indexed_title_ok no_legal_search_url"
        )

        self.assertEqual(
            got["gate_coverage"],
            [
                {
                    "gate": "title_ok",
                    "outcome": "excluded",
                    "reason": "no_expected_title_declared",
                },
                {
                    "gate": "indexed_title_ok",
                    "outcome": "not_evaluated",
                    "reason": "no_legal_search_url",
                },
            ],
        )
        self.assertEqual(got["excluded"], ["title_ok"])
        self.assertEqual(got["not_evaluated"], ["indexed_title_ok"])


class EveryHarnessThatReportsCoverageSaysWhy(unittest.TestCase):
    """A harness must not reintroduce the collapsed list (#744).

    `skipped_gates` alone cannot distinguish a gate nobody asked for from a gate that
    could not run, and only the second must refuse the flip. A harness that emits the
    old key without the ledger is the partial port this asserts against.
    """

    def test_no_harness_emits_skipped_gates_without_gate_coverage(self) -> None:
        scripts_dir = REPO_ROOT / "scripts"
        harnesses = sorted(
            [*scripts_dir.glob("*-fast-loop.sh"), scripts_dir / "ch-fedlex-compose-e2e.sh"]
        )
        self.assertGreaterEqual(len(harnesses), 6, "fast-loop harnesses disappeared")

        offenders = []
        for script in harnesses:
            body = script.read_text(encoding="utf-8")
            if "skipped_gates:" not in body:
                continue  # emits no coverage at all; the renderer reports that as unknown
            if "gate_coverage:" not in body:
                offenders.append(f"{script.name}: emits skipped_gates with no gate_coverage")
            if "skipped_gates+=(" in body:
                offenders.append(
                    f"{script.name}: builds the collapsed list directly instead of the ledger"
                )
        self.assertEqual(offenders, [], "; ".join(offenders))


class ContentTypeLabelTests(unittest.TestCase):
    def test_paste_block_labels_the_configured_content_type(self) -> None:
        markdown = render(
            summary(expect_content_type="application/pdf", content_type_match_count=3)
        )

        self.assertIn("application/pdf=`3`", markdown)

    def test_legacy_html_count_key_still_renders(self) -> None:
        # Sibling scripts still emit `content_type_html_count`; dropping the fallback
        # would silently render `text/html=0` for a run that captured resources.
        markdown = render(summary(content_type_html_count=7))

        self.assertIn("text/html=`7`", markdown)


if __name__ == "__main__":
    unittest.main()


class RunModeTests(unittest.TestCase):
    """An acceptance run's evidence must not read like a production run's (#743).

    A `pass` from an acceptance run proves the pipeline works; it does NOT mean
    either ADR-0030 key is turned. Evidence that omits the mode can be read as
    proof of something it never showed.
    """

    def test_acceptance_mode_is_named_and_qualified(self) -> None:
        markdown = render({**summary(), "run_mode": "acceptance"})

        self.assertIn("- Run mode: `acceptance`", markdown)
        self.assertIn("> Run mode: `acceptance` — an acceptance rehearsal", markdown)
        self.assertIn("does not imply either ADR-0030 key is turned", markdown)

    def test_preview_mode_carries_no_acceptance_caveat(self) -> None:
        markdown = render({**summary(), "run_mode": "preview"})

        self.assertIn("> Run mode: `preview`.", markdown)
        self.assertNotIn("acceptance rehearsal", markdown)

    def test_a_run_that_reported_no_mode_says_so(self) -> None:
        # The sibling harnesses do not emit run_mode yet. Unspecified must not be
        # silently rendered as the safe-looking default.
        markdown = render(summary())

        self.assertIn("- Run mode: `unspecified`", markdown)
        self.assertIn("> Run mode: `unspecified`.", markdown)


def resolve(lookup_response: str) -> tuple[str, str, list[str]]:
    """Run `resolve_fast_loop_source` against a stubbed curl_json.

    Returns (source_id, source_version_id, urls_posted_to).
    """
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        calls_path = run_dir / "calls.log"

        # Stub curl_json: record every POST target, answer the source lookup with
        # the caller's fixture, and answer either create path with a fresh id.
        stub = f"""
        curl_json() {{
          local url="" prev=""
          for a in "$@"; do
            case "$prev" in
              -X) ;;
              *) [[ "$a" == http* ]] && url="$a" ;;
            esac
            prev="$a"
          done
          if [[ "$*" == *"-X POST"* ]]; then
            printf '%s\\n' "$url" >> "{calls_path}"
          fi
          case "$url" in
            *"/v1/sources?q="*) printf '%s' '{lookup_response}' ;;
            *"/versions") printf '%s' '{{"source_version_id":"sv_new"}}' ;;
            *"with-version") printf '%s' '{{"source":{{"source_id":"src_created"}},"source_version":{{"source_version_id":"sv_created"}}}}' ;;
          esac
        }}
        log() {{ :; }}
        source "{EVIDENCE_LIB}"
        resolve_fast_loop_source "https://pc.test" "CH Fedlex fast-loop source" "{run_dir}" \\
          "vlabel" "tmpl" "ch" '{{"source":{{}},"source_version":{{}}}}'
        printf '%s %s' "$SOURCE_ID" "$SOURCE_VERSION_ID"
        """

        result = subprocess.run(
            ["bash", "-c", stub], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise AssertionError(f"resolve failed: {result.stderr}")

        source_id, version_id = result.stdout.strip().split(" ")
        calls = (
            calls_path.read_text(encoding="utf-8").split()
            if calls_path.exists()
            else []
        )
        return source_id, version_id, calls


class ResolveFastLoopSource(unittest.TestCase):
    """A rehearsal must not mint a new source per run (#766).

    The pipeline keys document identity off the source, so a fresh source per run
    minted a fresh document per run — and `search_hits`, which is an ADR-0030 gate,
    counted one law twice. Reuse is what makes the evidence mean what it says.
    """

    def test_an_existing_source_is_reused_rather_than_minted(self) -> None:
        existing = '{"data":[{"source_id":"src_existing","name":"CH Fedlex fast-loop source"}]}'

        source_id, version_id, calls = resolve(existing)

        self.assertEqual(source_id, "src_existing")
        self.assertEqual(version_id, "sv_new")
        self.assertTrue(
            any(c.endswith("/v1/sources/src_existing/versions") for c in calls),
            f"expected a version POST under the existing source, got {calls}",
        )
        self.assertFalse(
            any("with-version" in c for c in calls),
            f"reuse path must not POST /v1/sources/with-version, got {calls}",
        )

    def test_a_name_that_does_not_match_is_not_treated_as_a_hit(self) -> None:
        # Substring/prefix matching here would reuse an unrelated operator source.
        other = '{"data":[{"source_id":"src_other","name":"CH Fedlex fast-loop source (old)"}]}'

        source_id, _version_id, calls = resolve(other)

        self.assertEqual(source_id, "src_created")
        self.assertTrue(any("with-version" in c for c in calls))

    def test_the_first_run_still_creates_a_source(self) -> None:
        source_id, version_id, calls = resolve('{"data":[]}')

        self.assertEqual(source_id, "src_created")
        self.assertEqual(version_id, "sv_created")
        self.assertTrue(any("with-version" in c for c in calls))


class EveryHarnessResolvesRatherThanCreates(unittest.TestCase):
    """The #766 fix landed for one script and was reported as landing for all seven.

    This asserts the property across the whole family so the next port cannot be
    partial and still read as complete.
    """

    def test_no_fast_loop_script_posts_with_version_directly(self) -> None:
        offenders = []
        for script in sorted((REPO_ROOT / "scripts").glob("*-fast-loop.sh")):
            body = script.read_text(encoding="utf-8")
            if "resolve_fast_loop_source" not in body:
                offenders.append(f"{script.name}: never calls resolve_fast_loop_source")
            if "/v1/sources/with-version" in body:
                offenders.append(f"{script.name}: still POSTs /v1/sources/with-version")
        self.assertEqual(offenders, [], "; ".join(offenders))


class IndexedTitleIsAsserted(unittest.TestCase):
    """A harness that reads back from legal-search must assert the title there (#772).

    #771 shipped green because the title gate read `captured-resources.json` while
    the language gate read the index. The captured title was always correct; the
    pipeline replaced it afterwards. Any harness close enough to the index to check
    a language facet is close enough to check the name of the law.
    """

    # The four harnesses below never contact legal-search at all, so they cannot
    # assert an indexed anything. Named here rather than silently excluded, so the
    # gap is visible in the test that would otherwise imply full coverage.
    NO_LEGAL_SEARCH_READBACK = {
        "at-ris-fast-loop.sh",
        "de-bundesrecht-fast-loop.sh",
        "eu-eurlex-fast-loop.sh",
        "fr-legifrance-fast-loop.sh",
    }

    def _harnesses(self):
        scripts_dir = REPO_ROOT / "scripts"
        return sorted(
            [*scripts_dir.glob("*-fast-loop.sh"), scripts_dir / "ch-fedlex-compose-e2e.sh"]
        )

    def test_a_harness_that_checks_language_also_checks_title(self) -> None:
        offenders = []
        for script in self._harnesses():
            body = script.read_text(encoding="utf-8")
            checks_language = "indexed_language_ok" in body
            checks_title = "indexed_title_ok" in body
            if checks_language and not checks_title:
                offenders.append(
                    f"{script.name}: reads back the language facet but not the title"
                )
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_the_indexed_title_can_block_the_verdict(self) -> None:
        # Present-but-inert is the failure mode this repo keeps paying for: the gate
        # must reach the verdict, not merely appear in the summary JSON.
        offenders = []
        for script in self._harnesses():
            body = script.read_text(encoding="utf-8")
            if "indexed_title_ok" not in body:
                continue
            verdict_lines = [
                line
                for line in body.splitlines()
                if "indexed_title_ok" in line and "verdict" not in line and "elif" in line
            ]
            if not verdict_lines:
                offenders.append(f"{script.name}: indexed_title_ok never gates the verdict")
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_the_documented_gap_matches_reality(self) -> None:
        # If one of these gains a legal-search readback, this list must shrink with
        # it — otherwise the exclusion quietly becomes a hiding place.
        for name in self.NO_LEGAL_SEARCH_READBACK:
            body = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertNotIn(
                "indexed_language_ok",
                body,
                f"{name} now reads back from legal-search and must assert the indexed title",
            )


class EveryHarnessRunsOnTheSelfHostedRuntime(unittest.TestCase):
    """A harness that hard-requires `gcloud` cannot produce evidence at all (#799).

    ADR-0029 retired the GCP runtime. Four of the six harnesses kept a top-level
    `require_cmd gcloud` and resolved their URL via `gcloud run services describe`,
    so AT/DE/EU/FR had no runnable way to produce or refresh the evidence an
    operator attaches when flipping `enabled: true` under ADR-0030. That is why
    #798's AT RIS evidence could not simply be re-run: it did not go stale, it
    became unreproducible when the runtime changed, and nothing failed loudly.

    These assert the property across the whole family, so the next harness added
    cannot reintroduce a hard GCP dependency and still read as complete.
    """

    def _harnesses(self) -> list[Path]:
        found = sorted((REPO_ROOT / "scripts").glob("*-fast-loop.sh"))
        # Guard the glob itself: an empty list would make every check below vacuous.
        self.assertGreaterEqual(len(found), 6, "fast-loop harnesses disappeared from scripts/")
        return found

    def test_gcloud_is_never_required_unconditionally(self) -> None:
        offenders = []
        for script in self._harnesses():
            for lineno, line in enumerate(
                script.read_text(encoding="utf-8").splitlines(), start=1
            ):
                # Top-level (column 0) means it runs before any mode is chosen.
                if line.startswith("require_cmd gcloud"):
                    offenders.append(f"{script.name}:{lineno}: unconditional require_cmd gcloud")
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_every_harness_accepts_a_self_hosted_api_key(self) -> None:
        offenders = []
        for script in self._harnesses():
            body = script.read_text(encoding="utf-8")
            if "--api-key" not in body:
                offenders.append(f"{script.name}: no --api-key flag")
            if "EVIDARA_PLATFORM_CONTROL_API_KEY" not in body:
                offenders.append(f"{script.name}: does not read EVIDARA_PLATFORM_CONTROL_API_KEY")
            if "X-API-Key" not in body:
                offenders.append(f"{script.name}: never sends an X-API-Key header")
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_no_call_site_hardcodes_the_cloud_run_bearer_token(self) -> None:
        # Every request must go through PC_AUTH_HEADER. A call site that pins the
        # Bearer header directly sends an empty credential in self-hosted mode —
        # present-but-inert, the failure this repo keeps rediscovering (#728).
        offenders = []
        for script in self._harnesses():
            for lineno, line in enumerate(
                script.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "Authorization: Bearer" not in line:
                    continue
                # Assignments into a header array are the sanctioned form: the
                # managed-branch PC_AUTH_HEADER, and ch-fedlex's LS_AUTH_HEADER for
                # legal-search, which is public-by-default when self-hosted.
                if "_AUTH_HEADER=(" in line:
                    continue
                offenders.append(f"{script.name}:{lineno}: Bearer header outside an auth array")
        self.assertEqual(offenders, [], "; ".join(offenders))
