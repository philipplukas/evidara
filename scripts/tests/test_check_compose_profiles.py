from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_compose_profiles.py"
SPEC = importlib.util.spec_from_file_location("check_compose_profiles", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REPO_ROOT = Path(__file__).resolve().parents[2]


class LoadDefinedProfilesTests(unittest.TestCase):
    def test_collects_profiles_across_compose_documents(self) -> None:
        documents = [
            {"services": {"opensearch": {"profiles": ["search", "lean-stack"]}}},
            {"services": {"nats": {"profiles": ["nats"]}}},
        ]

        self.assertEqual(
            MODULE.load_defined_profiles(documents),
            {"search", "lean-stack", "nats"},
        )

    def test_ignores_services_without_profiles(self) -> None:
        documents = [{"services": {"postgres": {"image": "postgres:16-alpine"}}}]

        self.assertEqual(MODULE.load_defined_profiles(documents), set())


class IterReferencesTests(unittest.TestCase):
    def test_finds_profile_in_docker_compose_command(self) -> None:
        refs = list(MODULE.iter_references("docker compose --profile lean-stack up -d", "a.sh"))

        self.assertEqual([(r.profile, r.line) for r in refs], [("lean-stack", 1)])

    def test_finds_multiple_profiles_on_one_command(self) -> None:
        text = "docker compose -f docker-compose.local.yml --profile apps --profile nats up"

        refs = list(MODULE.iter_references(text, "a.sh"))

        self.assertEqual([r.profile for r in refs], ["apps", "nats"])

    def test_ignores_profile_flags_of_other_clis(self) -> None:
        # The Databricks CLI takes --profile too; it is not a Compose profile.
        text = "databricks --profile dev clusters list"

        self.assertEqual(list(MODULE.iter_references(text, "a.sh")), [])

    def test_ignores_shell_expansions_that_cannot_be_resolved_statically(self) -> None:
        text = 'docker compose --profile "$MODE" up -d'

        self.assertEqual(list(MODULE.iter_references(text, "a.sh")), [])

    def test_joins_backslash_continued_commands(self) -> None:
        text = "PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=nats \\\ndocker compose --profile apps up"

        refs = list(MODULE.iter_references(text, "a.sh"))

        self.assertEqual([(r.profile, r.line) for r in refs], [("apps", 1)])


class EvaluateTests(unittest.TestCase):
    def test_passes_when_every_reference_is_defined(self) -> None:
        refs = [MODULE.ProfileReference(profile="lean-stack", source="a.sh", line=29)]

        self.assertEqual(MODULE.evaluate({"lean-stack"}, refs), [])

    def test_fails_on_a_profile_no_compose_file_defines(self) -> None:
        refs = [MODULE.ProfileReference(profile="lean-stack", source="a.sh", line=29)]

        errors = MODULE.evaluate({"search", "full"}, refs)

        self.assertEqual(len(errors), 1)
        self.assertIn("a.sh:29", errors[0])
        self.assertIn("'lean-stack' is not defined", errors[0])


class RepositoryTests(unittest.TestCase):
    def test_repository_compose_profiles_all_resolve(self) -> None:
        defined, references = MODULE.collect(REPO_ROOT)

        self.assertEqual(MODULE.evaluate(defined, references), [])

    def test_lean_stack_profile_is_wired_up(self) -> None:
        # Regression guard: scripts/dev-lean-search-stack.sh and the lean setup doc
        # shipped against a `lean-stack` profile that no compose file defined.
        defined, _ = MODULE.collect(REPO_ROOT)

        self.assertIn("lean-stack", defined)
        self.assertIn("lean", defined)


if __name__ == "__main__":
    unittest.main()
