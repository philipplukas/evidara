#!/usr/bin/env python3
"""Keep the classifier-evidence rule present, specific, and in front of authors.

## Why a rule needs a guard at all

The rule this protects — a classifier ships with a fixture from the real surface
it classifies, plus one answer established independently of the tool — exists
because the canonical metadata audit derived its key registry from
`_build_document` and applied it to `published_sections`. It reported two keys
DROPPED across all 57,128 rows and registered none of the eleven keys sections
actually carry. Wrong in both directions, green suite, because the tests were
written against the same wrong registry.

A rule that lives only as a paragraph is deleted by the next person who is
reorganising headings, and nothing notices — which is the same failure mode as
the planning anchor. So the paragraph is asserted to exist, to still carry its
two clauses and its citation, and to be mirrored by a checkbox in the PR
template, where an author meets it at the moment it applies.

This checks that the rule is *stated*. It cannot check that a given classifier
obeyed it — that judgement is the reviewer's, which is exactly why the PR
template has to ask.

Exit codes: 0 all present, 1 something is missing.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AGENTS = REPO_ROOT / "AGENTS.md"
DEFAULT_PR_TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"

RULE_HEADING = "### A classifier is tested against the surface it classifies"

# Each requirement is (label, substring that must appear). Substrings, not
# regexes: the rule may be reworded around them, but these phrases carry the
# load and a reword that drops one has dropped the rule.
RULE_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("the heading", RULE_HEADING),
    ("the three-way decision it applies to", "present / absent / indeterminate"),
    ("clause 1 — a fixture from the real surface", "real surface it classifies"),
    ("clause 2 — an independent oracle", "independently of the thing under test"),
    ("the incident's surface", "published_sections"),
    ("the incident's row count", "57,128"),
    ("the PR that fixed the tool", "#1043"),
)

PR_TEMPLATE_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("a section pointing at the rule", "A classifier is tested against the surface it classifies"),
    ("the real-surface fixture checkbox", "drawn from the real surface"),
    ("the independent-oracle checkbox", "established independently of the tool under test"),
    ("the mutation checkbox", "a named test went red"),
)


@dataclass(frozen=True)
class Finding:
    path: Path
    label: str
    needle: str


def check_text(path: Path, text: str, requirements: tuple[tuple[str, str], ...]) -> list[Finding]:
    return [Finding(path, label, needle) for label, needle in requirements if needle not in text]


def run(agents: Path, pr_template: Path) -> int:
    findings: list[Finding] = []
    for path, requirements in ((agents, RULE_REQUIREMENTS), (pr_template, PR_TEMPLATE_REQUIREMENTS)):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            print(f"❌ cannot read {path}: {error}", file=sys.stderr)
            return 1
        findings.extend(check_text(path, text, requirements))

    if findings:
        print("❌ The classifier-evidence rule is incomplete:", file=sys.stderr)
        for finding in findings:
            rel = finding.path.relative_to(REPO_ROOT) if finding.path.is_relative_to(REPO_ROOT) else finding.path
            print(f"   {rel}: missing {finding.label} — expected to find {finding.needle!r}", file=sys.stderr)
        print(
            "\n   This rule is why a classifier's tests may not be derived from the same\n"
            "   source as the classifier. Restore it rather than reword it away.",
            file=sys.stderr,
        )
        return 1

    print("✅ classifier-evidence rule present in AGENTS.md and mirrored in the PR template.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agents", type=Path, default=DEFAULT_AGENTS)
    parser.add_argument("--pr-template", type=Path, default=DEFAULT_PR_TEMPLATE)
    args = parser.parse_args(argv)
    return run(args.agents, args.pr_template)


if __name__ == "__main__":
    raise SystemExit(main())
