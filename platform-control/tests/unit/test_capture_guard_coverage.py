"""The capture-guard coverage matrix, as an assertion rather than a docstring.

Both capture gates existed for months and protected one provider each:
``check_capture`` had a single call site (``lexfind_api_provider``) and
``assess_legal_text_density`` had one wiring (``portal_http_provider_base``, so the
three subclasses that inherit it). ``gemeinde_http`` — LIVE, PDF-capturing, and the
municipal rung of ADR-0033's own dog question — called neither.

Nothing could see that. document-intelligence's ``tests/test_quarantine.py`` wrote the
gap down in a *module docstring* and said so explicitly: "the exemption below is keyed
on content type while the real coverage depends on provider class, so the drift test
cannot see this widen". A comment is not a gate. This file is the gate.

**What it asserts, and what it deliberately does not.** It asserts that each registered
provider's decision about each gate is *recorded and current* — not that every provider
calls every gate. Three of the thirteen are wired to neither on purpose, and their
reasons are the interesting half of the matrix: a gate configured for the wrong
modality or the wrong language is worse than no gate, because it refuses honest
captures while looking like protection.

Adding a provider to ``build_provider_registry`` without deciding fails here. That is
the point: the decision is cheap to make and expensive to notice you never made.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from platform_control.config import get_settings
from platform_control.services.provider_registry_factory import build_provider_registry

_SERVICES = Path(__file__).resolve().parents[2] / "src" / "platform_control" / "services"

_CHECK_CAPTURE = "check_capture"
_DENSITY_GATE = "assess_legal_text_density"


@dataclass(frozen=True)
class GuardExpectation:
    """One row of the matrix: which gates a provider's capture path must call."""

    module: str
    #: Modules whose capture path this provider inherits (its gate calls live there).
    inherits_from: str | None
    check_capture: bool
    legal_text_density: bool
    #: Why — load-bearing for the `False` rows, which are decisions, not omissions.
    reason: str


# The matrix. `check_capture` belongs where the provider promised a format OUT OF BAND
# (a URL suffix, a listing's `DataType`, an API field) and the server could contradict
# it; where the content type is simply read back off the response there is nothing to
# contradict and the check would be theatre. `assess_legal_text_density` belongs where
# the provider captures assessable text (HTML/XML) in a language the shared marker
# vocabulary actually covers — DE, IT and Swiss FR ("art.", "§", "Abs.", "comma").
_MATRIX: dict[str, GuardExpectation] = {
    "lexfind_api": GuardExpectation(
        module="lexfind_api_provider.py",
        inherits_from=None,
        check_capture=True,
        legal_text_density=True,
        reason=(
            "PDF promised by the LexFind record; the density gate is called for its "
            "deliberate abstention on application/pdf, so the abstention is evidence "
            "rather than an absence (#716, ADR-0047)."
        ),
    ),
    "gemeinde_http": GuardExpectation(
        module="gemeinde_http_provider.py",
        inherits_from=None,
        check_capture=True,
        legal_text_density=True,
        reason=(
            "The manifestation's content type is derived from the URL SUFFIX the "
            "landing page published, so only check_capture holds the server to it. "
            "Communes that publish HTML get the density gate; the PDF path abstains."
        ),
    ),
    "ris_ogd": GuardExpectation(
        module="ris_ogd_provider.py",
        inherits_from=None,
        check_capture=True,
        legal_text_density=True,
        reason=(
            "The RIS listing promises Xml/Html/Pdf before the download is fetched, and "
            "this provider decodes every body as text — a binary arriving where Xml was "
            "promised would be UTF-8-mangled and captured. Austrian federal law is "
            "German and cites § and Abs. throughout."
        ),
    ),
    "fedlex_sparql": GuardExpectation(
        module="fedlex_sparql_provider.py",
        inherits_from=None,
        check_capture=False,
        legal_text_density=True,
        reason=(
            "Fetches an HTML manifestation and reads the content type off the response, "
            "so there is no out-of-band promise for check_capture to enforce. The "
            "density gate is the heuristic scripts/ch-fedlex-fast-loop.sh has run "
            "against this provider's own output all along (art_density >= 3)."
        ),
    ),
    "ch_court_decisions": GuardExpectation(
        module="ch_court_decisions_provider.py",
        inherits_from=None,
        check_capture=False,
        legal_text_density=True,
        reason=(
            "Server-rendered HTML read back off the response. An index walk reaches "
            "consent interstitials and 'nicht gefunden' pages, all 200 text/html with "
            "visible text; a Swiss ruling cites Art./Abs./lit. well clear of the floor."
        ),
    ),
    "deterministic_http": GuardExpectation(
        module="deterministic_http_provider.py",
        inherits_from=None,
        check_capture=False,
        legal_text_density=True,
        reason=(
            "Generic text fetcher; content type is whatever the server said. Every "
            "template pointing here targets a DE/CH/IT collection "
            "(source_blueprints.yaml:114,129,176,672), and the gate abstains on the "
            "content types it cannot read."
        ),
    ),
    "canton_http": GuardExpectation(
        module="canton_http_provider.py",
        inherits_from="portal_http_provider_base.py",
        check_capture=False,
        legal_text_density=True,
        reason="Inherits PortalHttpProviderBase's capture path, which runs the gate.",
    ),
    "bundesland_http": GuardExpectation(
        module="bundesland_http_provider.py",
        inherits_from="portal_http_provider_base.py",
        check_capture=False,
        legal_text_density=True,
        reason="Inherits PortalHttpProviderBase's capture path, which runs the gate.",
    ),
    "regione_http": GuardExpectation(
        module="regione_http_provider.py",
        inherits_from="portal_http_provider_base.py",
        check_capture=False,
        legal_text_density=True,
        reason="Inherits PortalHttpProviderBase's capture path, which runs the gate.",
    ),
    "eur_lex_sparql": GuardExpectation(
        module="eur_lex_sparql_provider.py",
        inherits_from=None,
        check_capture=False,
        legal_text_density=False,
        reason=(
            "DELIBERATELY UNGATED. `_preferred_languages` defaults to ['en'] "
            "(eur_lex_sparql_provider.py) and content_gate's vocabulary is DE/IT: EU "
            "English writes 'Article 5', which carries no `art.`, `§` or `Abs.`. Wiring "
            "the gate here would refuse honest EU captures — worse than no gate. "
            "Closing this needs an EN/FR marker vocabulary, and content_gate's regex is "
            "pinned by DI's drift test (document-intelligence/tests/test_quarantine.py), "
            "so it is a cross-component change, not a one-line edit. Content type is "
            "read off the response, so check_capture has no promise to enforce either."
        ),
    ),
    "legifrance": GuardExpectation(
        module="legifrance_provider.py",
        inherits_from=None,
        check_capture=False,
        legal_text_density=False,
        reason=(
            "DELIBERATELY UNGATED. The body is a JSON API field (`texteHtml`), not "
            "bytes received for a document, so there is nothing for check_capture to "
            "check. French statute text writes 'Article' and 'l'article L. 121-4', "
            "outside content_gate's DE/IT vocabulary. readiness=SCAFFOLD — no run of "
            "any mode dispatches."
        ),
    ),
    "firecrawl": GuardExpectation(
        module="firecrawl_provider.py",
        inherits_from=None,
        check_capture=False,
        legal_text_density=False,
        reason=(
            "NOT APPLICABLE HERE, AND A REAL GAP ELSEWHERE. start_run dispatches an "
            "external job and returns no inline_resources; pages arrive later at "
            "firecrawl_webhook_service.py, which persists them as RawArtifact rows with "
            "a guessed content type and calls neither gate. That is a separate capture "
            "path outside this lane's provider modules — see the PR body."
        ),
    ),
    "cassette": GuardExpectation(
        module="cassette_provider.py",
        inherits_from=None,
        check_capture=False,
        legal_text_density=False,
        reason=(
            "Offline fixture replay for SHADOW mode. Nothing is received, so 'are these "
            "the bytes I asked for?' has no meaning; and gating replay would make "
            "failure-path fixtures unusable for exercising the failure paths."
        ),
    ),
}


def _calls_in(module: str) -> set[str]:
    """Names called anywhere in a services module, read from its AST.

    Source-level rather than behavioural on purpose: the question is "is this gate
    wired into this provider at all", which is exactly what has been silently false.
    A behavioural assertion needs a fixture per provider and would grow a blind spot
    the moment one is skipped.
    """
    tree = ast.parse((_SERVICES / module).read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    return called


def _effective_calls(expectation: GuardExpectation) -> set[str]:
    calls = _calls_in(expectation.module)
    if expectation.inherits_from:
        calls |= _calls_in(expectation.inherits_from)
    return calls


def test_every_registered_provider_has_a_recorded_guard_decision() -> None:
    """A provider registered without a matrix row is a decision nobody made."""
    registered = set(build_provider_registry(get_settings())._providers)
    # Guard the guard: an empty or truncated registry would make the comparison below
    # vacuously interesting rather than loudly wrong.
    assert len(registered) == 13, f"expected 13 registered providers, got {sorted(registered)}"
    assert registered == set(_MATRIX), (
        "the capture-guard matrix and the provider registry disagree. Every provider "
        "must record whether each gate applies to it and why — including 'neither', "
        "which is the answer for three of them. Missing from the matrix: "
        f"{sorted(registered - set(_MATRIX))}; stale rows: {sorted(set(_MATRIX) - registered)}"
    )


def test_the_matrix_matches_what_the_providers_actually_call() -> None:
    drift: list[str] = []
    for name, expectation in _MATRIX.items():
        calls = _effective_calls(expectation)
        for gate, expected in (
            (_CHECK_CAPTURE, expectation.check_capture),
            (_DENSITY_GATE, expectation.legal_text_density),
        ):
            if (gate in calls) != expected:
                verb = "does not call" if expected else "calls"
                drift.append(f"{name} ({expectation.module}) {verb} {gate}")
    assert not drift, (
        "a provider's capture path no longer matches its recorded guard decision: "
        + "; ".join(drift)
        + ". Update the wiring or the matrix row — whichever is wrong — but do not "
        "leave the two disagreeing."
    )


def test_every_ungated_provider_states_why() -> None:
    """The `False, False` rows are the load-bearing ones; they must justify themselves."""
    for name, expectation in _MATRIX.items():
        if expectation.check_capture or expectation.legal_text_density:
            continue
        assert len(expectation.reason) > 120, (
            f"{name} is wired to neither capture gate with a one-line reason. An "
            "ungated capture path is a claim that neither failure mode is reachable "
            "there; say why in enough detail that a reviewer can disagree with it."
        )


def test_the_two_gates_stay_separate_modules() -> None:
    """`artifact_guard` must not grow a marker check, or DI's drift test loses its anchor.

    ADR-0047 and `artifact_guard`'s own docstring say the vocabulary and threshold live
    in `content_gate` and nowhere else, because two opinions about what law looks like
    is how they drift apart. document-intelligence's `test_quarantine.py` reads
    `content_gate.py`'s source at test time and would silently stop pinning anything if
    the definition moved.
    """
    acquisition_core = _SERVICES.parents[1] / "acquisition_core"
    guard_source = (acquisition_core / "artifact_guard.py").read_text(encoding="utf-8")
    assert "_LEGAL_MARKER_RE" not in guard_source
    assert "assess_legal_text_density" not in guard_source.split('"""', 2)[-1]
