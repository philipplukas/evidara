"""Tests for infra/hetzner/minio-policies/scoping_matrix.py.

The regression under test is a gate that could not fail. The first version of
`verify-minio-scoping.sh` asserted "read is denied" against a key that did not exist —
and a missing object returns NoSuchKey whether or not `s3:GetObject` is granted, so
every read assertion passed unconditionally. A deny test that cannot fail is worse than
no deny test, because the PR body and ADR-0049 both cite it as proof.

So the cases that matter most here are the *vacuity* ones: every read assertion must
name a key the caller also seeds, and every write probe must sit inside the prefix the
account is actually granted.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / "infra" / "hetzner" / "minio-policies"
MODULE = POLICY_DIR / "scoping_matrix.py"
ACCOUNTS = POLICY_DIR / "accounts.json"

_spec = importlib.util.spec_from_file_location("scoping_matrix", MODULE)
assert _spec and _spec.loader
matrix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(matrix)


def parse_checks(checks: list[str]) -> dict[tuple[str, str], tuple[str, str]]:
    """`bucket:check:expect:key` -> {(bucket, check): (expect, key)}."""
    parsed = {}
    for spec in checks:
        bucket, check, expect, key = spec.split(":")
        parsed[(bucket, check)] = (expect, key)
    return parsed


class RealAccountsTest(unittest.TestCase):
    """The committed matrix must be able to fail."""

    def setUp(self) -> None:
        document = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
        self.seeds, self.accounts = matrix.build(document)
        self.by_user = {a["user"]: parse_checks(a["checks"]) for a in self.accounts}

    def test_every_read_assertion_names_a_seeded_key(self) -> None:
        """This is the whole fix: no read check may target an absent object."""
        seeded = set(self.seeds)
        for user, checks in self.by_user.items():
            for (bucket, check), (_expect, key) in checks.items():
                if check != "read":
                    continue
                self.assertIn(
                    (bucket, key),
                    seeded,
                    f"{user}: read check on {bucket}/{key} has no seeded object, so a "
                    "denial cannot be distinguished from a missing key",
                )

    def test_write_probe_stays_inside_the_granted_prefix(self) -> None:
        """A probe at the bucket root cannot test a `canonical/`-scoped grant."""
        document = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
        for account in document["accounts"]:
            checks = self.by_user[account["user"]]
            for entry in account["allow"]:
                _expect, key = checks[(entry["bucket"], "write")]
                self.assertTrue(
                    key.startswith(entry["prefix"]),
                    f"{account['user']}: write probe {key!r} is outside its granted "
                    f"prefix {entry['prefix']!r} on {entry['bucket']}",
                )

    def test_platform_control_read_is_asserted_denied(self) -> None:
        """The write-only account must be proven unable to read artifacts back."""
        expect, key = self.by_user["platform-control"][("evidara-raw-artifacts", "read")]
        self.assertEqual(expect, "deny")
        self.assertIn(("evidara-raw-artifacts", key), set(self.seeds))

    def test_document_service_write_is_asserted_denied_in_prefix(self) -> None:
        expect, key = self.by_user["document-service"][("evidara-lakehouse", "write")]
        self.assertEqual(expect, "deny")
        self.assertEqual(key, "canonical/.evidara-write-probe")

    def test_every_account_covers_every_bucket_three_ways(self) -> None:
        document = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
        buckets = document["all_buckets"]
        for user, checks in self.by_user.items():
            for bucket in buckets:
                for check in ("list", "read", "write"):
                    self.assertIn((bucket, check), checks, f"{user} misses {bucket}/{check}")

    def test_denied_buckets_are_denied_on_all_three_operations(self) -> None:
        document = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
        for account in document["accounts"]:
            checks = self.by_user[account["user"]]
            for bucket in account["deny"]:
                for check in ("list", "read", "write"):
                    self.assertEqual(
                        checks[(bucket, check)][0],
                        "deny",
                        f"{account['user']} does not expect {check} denied on {bucket}",
                    )


class AccessLevelTest(unittest.TestCase):
    """`access` must drive the expectations, not the other way round."""

    @staticmethod
    def _document(access: str, prefix: str = "") -> dict:
        return {
            "all_buckets": ["b1", "b2"],
            "accounts": [
                {
                    "user": "demo",
                    "policy_file": "demo.json",
                    "k8s_secret": "evidara-s3-demo",
                    "access_key_field": "AK",
                    "secret_key_field": "SK",
                    "allow": [{"bucket": "b1", "access": access, "prefix": prefix}],
                    "deny": ["b2"],
                }
            ],
        }

    def _checks(self, access: str, prefix: str = "") -> dict:
        _seeds, accounts = matrix.build(self._document(access, prefix))
        return parse_checks(accounts[0]["checks"])

    def test_ro_allows_read_and_denies_write(self) -> None:
        checks = self._checks("ro")
        self.assertEqual(checks[("b1", "read")][0], "allow")
        self.assertEqual(checks[("b1", "write")][0], "deny")

    def test_wo_denies_read_and_allows_write(self) -> None:
        checks = self._checks("wo")
        self.assertEqual(checks[("b1", "read")][0], "deny")
        self.assertEqual(checks[("b1", "write")][0], "allow")

    def test_rw_allows_both(self) -> None:
        checks = self._checks("rw")
        self.assertEqual(checks[("b1", "read")][0], "allow")
        self.assertEqual(checks[("b1", "write")][0], "allow")

    def test_prefix_is_applied_to_both_probes(self) -> None:
        checks = self._checks("rw", prefix="canonical/")
        self.assertEqual(checks[("b1", "read")][1], "canonical/.evidara-read-probe")
        self.assertEqual(checks[("b1", "write")][1], "canonical/.evidara-write-probe")

    def test_unknown_access_is_rejected(self) -> None:
        with self.assertRaises(matrix.MatrixError):
            matrix.build(self._document("admin"))

    def test_unclassified_bucket_is_rejected(self) -> None:
        document = self._document("ro")
        document["accounts"][0]["deny"] = []
        with self.assertRaises(matrix.MatrixError):
            matrix.build(document)

    def test_read_and_write_probes_are_distinct(self) -> None:
        """A shared key would let a write test delete the read test's object."""
        checks = self._checks("rw")
        self.assertNotEqual(checks[("b1", "read")][1], checks[("b1", "write")][1])


if __name__ == "__main__":
    unittest.main()
