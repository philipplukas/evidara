#!/usr/bin/env python3
"""Fail the build when two ADRs claim the same number.

This check exists because the collision it guards against happened while the
ADR that describes it was being written. Three lanes each read the highest ADR
number on `main`, each concluded the next integer was free, and each was right
about `main` and wrong about reality: #676 took 0038, #705 took 0039, and a
third lane took 0038 again.

**Why git does not catch this.** Two branches adding `0038-alpha.md` and
`0038-beta.md` touch different filenames. They merge without a textual
conflict. `docs/adr/README.md` and `mkdocs.yml` may conflict near the same
lines, but the natural resolution — keep both entries — is precisely the one
that lands two ADR-0038s on `main`. The signal git gives you points away from
the problem.

**What this can and cannot check.** It compares the numbers of files that exist
in one checkout, so it fires when the second colliding PR merges (or rebases),
not when it is opened. Catching it at open time would mean querying GitHub for
the files added by every other open PR — network, auth, and flake in a check
that is supposed to be cheap and offline. Failing at merge is late but
deterministic, and it is the first moment the two numbers are observable in the
same tree.

Four numbers are already duplicated from a historical renumbering
(`docs/adr/README.md` says as much). They are registered below rather than
silenced, per ADR-0040: a stale entry fails, so the register cannot outlive
the debt.

Exit codes: 0 when every ADR number is unique or registered, 1 otherwise.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(os.environ.get("ADR_NUMBERS_REPO_ROOT") or Path(__file__).resolve().parent.parent)
ADR_DIR = REPO_ROOT / "docs" / "adr"

# `0034-foo.md` and `adr-0020-foo.md` are both in use.
ADR_FILENAME = re.compile(r"^(?:adr-)?(\d{4})-.+\.md$")

# Numbers duplicated before this check existed, from a renumbering that left
# two files sharing a prefix. Each entry must name both files. Renumbering them
# now would break inbound links for no benefit; the rule is that no *new*
# collision is allowed.
KNOWN_DUPLICATES: dict[str, str] = {
    "0008": "0008-contract-interaction-model.md + 0008-nestjs-conventions-legal-search.md",
    "0009": "0009-fastapi-conventions-platform-control.md + 0009-technology-stack-and-language-boundaries.md",
    "0016": "0016-cloud-run-services-vs-jobs.md + adr-0016-design-system-component-contracts.md",
    "0026": "adr-0026-admin-ui-tailwind-ra-core.md + adr-0026-id-naming-policy.md",
}


def collect() -> dict[str, list[str]]:
    by_number: dict[str, list[str]] = defaultdict(list)
    for path in sorted(ADR_DIR.glob("*.md")):
        match = ADR_FILENAME.match(path.name)
        if match:
            by_number[match.group(1)].append(path.name)
    return by_number


def main() -> int:
    by_number = collect()
    if not by_number:
        print(f"FAIL: found no ADR files under {ADR_DIR} — the parser is broken.", file=sys.stderr)
        return 1

    duplicates = {n: files for n, files in by_number.items() if len(files) > 1}
    new = {n: files for n, files in duplicates.items() if n not in KNOWN_DUPLICATES}
    stale = sorted(set(KNOWN_DUPLICATES) - set(duplicates))

    if new:
        print(f"FAIL: {len(new)} ADR number(s) claimed by more than one file:\n", file=sys.stderr)
        for number, files in sorted(new.items()):
            print(f"  ADR-{number}:", file=sys.stderr)
            for name in files:
                print(f"    docs/adr/{name}", file=sys.stderr)
        highest = max(by_number)
        print(
            f"\nTwo ADRs cannot share a number. The next free number here is "
            f"{int(highest) + 1:04d} — but check the open PRs before taking it, "
            "because this check only sees one checkout at a time and that is exactly\n"
            "how the collision it guards against was created. See ADR-0040.\n",
            file=sys.stderr,
        )

    if stale:
        print(
            f"\nFAIL: {len(stale)} KNOWN_DUPLICATES entr(y/ies) are stale — the number is "
            "no longer duplicated. Delete them:\n",
            file=sys.stderr,
        )
        for number in stale:
            print(f"  ADR-{number}", file=sys.stderr)

    if new or stale:
        return 1

    print(
        f"ADR numbering: OK ({len(by_number)} numbers across "
        f"{sum(len(f) for f in by_number.values())} files, "
        f"{len(KNOWN_DUPLICATES)} historical duplicates registered)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
