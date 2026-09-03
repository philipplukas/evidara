"""The BFS source citation must survive a regeneration of the commune registry.

`country-overlays/ch/municipalities.yaml` redistributes 2,110 rows taken from the
BFS *Amtliches Gemeindeverzeichnis*. The citation for those rows lives in the
file's YAML comment header — which means it is written by
`scripts/load_ch_gemeindeverzeichnis.py`, and a header edit made only in the
generated file would be erased the next time anyone regenerates it.

So this asserts the citation in *both* places: in the generator's `_HEADER`
template (the thing that regeneration writes) and in the checked-in file (the
thing that is redistributed today). Either one alone would pass while the
attribution was silently gone from the other.
"""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "load_ch_gemeindeverzeichnis.py"
OVERLAY = REPO_ROOT / "country-overlays" / "ch" / "municipalities.yaml"

# The load-bearing fragments. Deliberately not the whole block: wording may be
# improved, but the publisher, the catalogue entry and the terms tier must stay.
REQUIRED_FRAGMENTS = (
    "Bundesamt fuer Statistik (BFS)",
    "historisiertes-gemeindeverzeichnis-der-schweiz",
    "https://opendata.swiss/terms-of-use#terms_open",
)


class GemeindeverzeichnisAttributionTests(unittest.TestCase):
    def test_generator_header_carries_the_bfs_citation(self) -> None:
        header = GENERATOR.read_text(encoding="utf-8")
        for fragment in REQUIRED_FRAGMENTS:
            self.assertIn(
                fragment,
                header,
                msg=(
                    f"{GENERATOR.relative_to(REPO_ROOT)} no longer emits {fragment!r}. "
                    "Regenerating the overlay would drop the BFS source citation."
                ),
            )

    def test_generated_overlay_carries_the_bfs_citation(self) -> None:
        # Only the comment header is inspected; the 2,110 data rows are irrelevant.
        head = OVERLAY.read_text(encoding="utf-8").split("\nschema:", 1)[0]
        for fragment in REQUIRED_FRAGMENTS:
            self.assertIn(
                fragment,
                head,
                msg=(
                    f"{OVERLAY.relative_to(REPO_ROOT)} header no longer carries "
                    f"{fragment!r}. See THIRD-PARTY-NOTICES.md §2."
                ),
            )


if __name__ == "__main__":
    unittest.main()
