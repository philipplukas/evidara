"""The scaffold's output must pass the gate CI runs over the committed file.

A scaffold whose YAML the repo's own validator rejects is worse than no scaffold: it
produces confident, wrong config, and the operator finds out at commit time or — worse —
after pasting it. So this does not re-state `check_country_overlay`'s rules; it runs
`_validate_template` itself over what the scaffold emits, for every provider it claims to
support.

The CLI is a separate package under tools/, so it is imported by path the way this
directory already imports scripts.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import yaml

from scripts.check_country_overlay import _validate_template

REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_SRC = REPO_ROOT / "tools" / "evidara-cli" / "src"
if str(_CLI_SRC) not in sys.path:
    sys.path.insert(0, str(_CLI_SRC))

_spec = importlib.util.spec_from_file_location(
    "evidara_cli_scaffold", _CLI_SRC / "evidara_cli" / "scaffold.py"
)
assert _spec and _spec.loader
scaffold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scaffold)


CASES = {
    "lexfind_api": dict(
        provider="lexfind_api",
        jurisdiction_id="jur_ch_be",
        corpus_id="corpus_public_ch_canton_be_legislation",
        entity_ids=[4],
    ),
    "fedlex_sparql": dict(
        provider="fedlex_sparql",
        jurisdiction_id="jur_ch_federal",
        corpus_id="corpus_public_ch_fedlex_probe",
        seed_urls=["https://fedlex.data.admin.ch/eli/cc/1999/404"],
    ),
    "gemeinde_http": dict(
        provider="gemeinde_http",
        jurisdiction_id="jur_ch_gemeinde_261",
        corpus_id="corpus_public_ch_gemeinde_261",
        bfs_number=261,
        seed_urls=["https://www.stadt-zuerich.ch/vorschriften"],
    ),
}


class ScaffoldOutputPassesTheRealValidator(unittest.TestCase):
    def test_every_supported_provider_scaffolds_something_valid(self) -> None:
        for name, kwargs in CASES.items():
            with self.subTest(provider=name):
                body = scaffold.build_template(**kwargs)
                template_id = scaffold.default_template_id(
                    kwargs["provider"], kwargs["jurisdiction_id"]
                )
                errors = _validate_template("ch", template_id, body)
                self.assertEqual(errors, [], f"{name}: {errors}")

    def test_the_rendered_yaml_parses_back_to_the_same_template(self) -> None:
        """The YAML is hand-rendered to match the file's indentation, so round-tripping
        it is the only thing that proves the rendering is not subtly malformed."""
        for name, kwargs in CASES.items():
            with self.subTest(provider=name):
                body = scaffold.build_template(**kwargs)
                template_id = scaffold.default_template_id(
                    kwargs["provider"], kwargs["jurisdiction_id"]
                )
                parsed = yaml.safe_load(scaffold.render_yaml(template_id, body))
                self.assertEqual(list(parsed), [template_id])
                self.assertEqual(parsed[template_id], body)

    def test_the_rendered_yaml_also_passes_the_validator(self) -> None:
        """Validating the dict is not enough: the operator pastes the TEXT."""
        kwargs = CASES["lexfind_api"]
        template_id = scaffold.default_template_id("lexfind_api", kwargs["jurisdiction_id"])
        parsed = yaml.safe_load(
            scaffold.render_yaml(template_id, scaffold.build_template(**kwargs))
        )
        self.assertEqual(_validate_template("ch", template_id, parsed[template_id]), [])

    def test_enabled_is_always_false_and_is_not_a_parameter(self) -> None:
        """ADR-0030's config key fails closed. A scaffold that could emit `true` would be
        a way to skip the acceptance run, in the one file where skipping it is invisible."""
        for name, kwargs in CASES.items():
            with self.subTest(provider=name):
                self.assertIs(scaffold.build_template(**kwargs)["enabled"], False)
        self.assertNotIn("enabled", scaffold.build_template.__code__.co_varnames)

    def test_an_unsupported_provider_is_refused_rather_than_guessed(self) -> None:
        with self.assertRaises(scaffold.ScaffoldError) as ctx:
            scaffold.build_template(
                provider="canton_http", jurisdiction_id="jur_ch_zh", corpus_id="corpus_x"
            )
        self.assertIn("cannot scaffold provider", str(ctx.exception))

    def test_missing_scope_arguments_are_refused(self) -> None:
        with self.assertRaises(scaffold.ScaffoldError):
            scaffold.build_template(
                provider="lexfind_api", jurisdiction_id="jur_ch_be", corpus_id="corpus_x"
            )
        with self.assertRaises(scaffold.ScaffoldError):
            scaffold.build_template(
                provider="gemeinde_http", jurisdiction_id="jur_ch_gemeinde_261",
                corpus_id="corpus_x", bfs_number=261,
            )

    def test_the_declared_jurisdiction_must_exist_in_the_seed(self) -> None:
        """The scaffold emits `jurisdiction_id`, so it can emit a wrong one — and the
        guard added with that field is what catches it."""
        body = scaffold.build_template(
            provider="lexfind_api",
            jurisdiction_id="jur_ch_atlantis",
            corpus_id="corpus_x",
            entity_ids=[99],
        )
        errors = _validate_template("ch", "lexfind_api_atlantis", body)
        self.assertTrue(any("not in" in e for e in errors), errors)
