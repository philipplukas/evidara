"""Unit tests for survey_communal_portals discovery (no DNS, no HTTP).

These pin the two defects that made the 2026-07-21 pilot report 919 `undiscovered`
communes when it had never contacted 137 of them and had never requested a French
path even once. Both were silent: the survey reported a clean outcome for every row,
so only an assertion on the probe list itself can hold the line.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "survey_communal_portals.py"
    name = "_survey_communal_portals_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class SlugVariantsTest(unittest.TestCase):
    """Phase A must clean unhostnameable characters, not discard the name."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load_module()

    def test_parenthesised_canton_yields_stem_and_qualified_form(self):
        slugs = self.m.slug_variants("Buchs (AG)", "ag")
        self.assertIn("buchs", slugs)
        self.assertIn("buchs-ag", slugs)

    def test_parenthesised_name_is_not_double_canton_suffixed(self):
        self.assertNotIn("buchs-ag-ag", self.m.slug_variants("Buchs (AG)", "ag"))

    def test_bilingual_name_splits_on_slash(self):
        slugs = self.m.slug_variants("Biel/Bienne", "be")
        for expected in ("biel", "bienne", "biel-bienne"):
            self.assertIn(expected, slugs)

    def test_bei_qualified_name_yields_stem_and_compact_form(self):
        slugs = self.m.slug_variants("Wohlen bei Bern", "be")
        for expected in ("wohlen", "wohlen-bern", "wohlen-bei-bern"):
            self.assertIn(expected, slugs)

    def test_umlaut_is_transliterated_and_stripped(self):
        slugs = self.m.slug_variants("Gränichen", "ag")
        self.assertIn("graenichen", slugs)
        self.assertIn("granichen", slugs)

    def test_no_name_form_is_dropped_wholesale(self):
        """The regression itself: these three produced zero candidates."""
        for name in ("Buchs (AG)", "Biel/Bienne", "Erlinsbach (AG)"):
            self.assertTrue(
                self.m.slug_variants(name, "ag"), f"{name} produced no slugs"
            )


class ProbeOrderTest(unittest.TestCase):
    """Phase B must order breadth-first by path, so the budget spans domains."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load_module()

    def _row(self, language="de", domains=("a.example", "b.example", "c.example")):
        row = self.m.PortalRow(bfs_id=1, name="Test", canton="ag", language=language)
        row.candidate_domains = list(domains)
        return row

    def test_budget_reaches_every_candidate_domain(self):
        """The 782-row defect: domains 2 and 3 were never requested at all."""
        urls = self.m.probe_urls(self._row())[: self.m.MAX_HTTP_ATTEMPTS]
        for domain in ("a.example", "b.example", "c.example"):
            self.assertTrue(
                any(domain in u for u in urls), f"{domain} unreachable within budget"
            )

    def test_top_path_is_tried_on_all_domains_before_second_path(self):
        urls = self.m.probe_urls(self._row())
        self.assertEqual(
            urls[:3],
            [
                "https://a.example/rechtssammlung",
                "https://b.example/rechtssammlung",
                "https://c.example/rechtssammlung",
            ],
        )

    def test_french_commune_probes_french_paths_first(self):
        """These paths were last in a flat list and truncated away for every row."""
        urls = self.m.probe_urls(self._row(language="fr", domains=("m.example",)))
        self.assertEqual(urls[0], "https://m.example/recueil-systematique")

    def test_french_paths_reachable_within_budget_for_french_communes(self):
        urls = self.m.probe_urls(self._row(language="fr"))[: self.m.MAX_HTTP_ATTEMPTS]
        self.assertTrue(any("recueil-systematique" in u for u in urls))

    def test_unknown_language_falls_back_to_both_language_paths(self):
        paths = self.m.collection_paths("rm")
        self.assertIn("/rechtssammlung", paths)
        self.assertIn("/recueil-systematique", paths)

    def test_vendor_tenant_is_probed_before_own_domains(self):
        row = self._row()
        row.vendor_subdomain = "test.tlex.ch"
        self.assertEqual(
            self.m.probe_urls(row)[0], "https://test.tlex.ch/app/de/overview"
        )

    def test_probe_urls_are_deduplicated(self):
        urls = self.m.probe_urls(self._row(domains=("a.example", "a.example")))
        self.assertEqual(len(urls), len(set(urls)))


class OutcomeHonestyTest(unittest.TestCase):
    """`undiscovered` must mean "looked and found nothing", never "never looked"."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load_module()

    def test_no_candidates_is_not_probed_not_undiscovered(self):
        row = self.m.PortalRow(bfs_id=1, name="Test", canton="ag", language="de")
        self.m.fingerprint(row, fetcher=None)  # never reached: no URL to fetch
        self.assertEqual(row.outcome, "not_probed")

    def test_exhausted_budget_records_what_was_actually_probed(self):
        class _NoHitFetcher:
            def get(self, url):
                return 404, ""

        row = self.m.PortalRow(bfs_id=1, name="Test", canton="ag", language="de")
        row.candidate_domains = ["a.example", "b.example", "c.example"]
        self.m.fingerprint(row, _NoHitFetcher())
        self.assertEqual(row.outcome, "undiscovered")
        self.assertIn("budget-truncated", row.note)
        self.assertIn(f"{self.m.MAX_HTTP_ATTEMPTS} of", row.note)


class _ScriptedFetcher:
    """Serves canned responses by URL; anything unlisted 404s. Records every call."""

    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url):
        self.calls.append(url)
        if url in self.responses:
            return 200, self.responses[url]
        return 404, ""


def _sitemap(paths):
    locs = "".join(f"<loc>https://a.example{p}</loc>" for p in paths)
    return f"<?xml version='1.0'?><urlset>{locs}</urlset>"


class SitemapProbeTest(unittest.TestCase):
    """A site enumerating itself answers what guessing paths cannot."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load_module()

    def _row(self):
        row = self.m.PortalRow(bfs_id=1, name="Test", canton="ag", language="de")
        row.candidate_domains = ["a.example"]
        return row

    def test_collection_found_via_sitemap_is_fingerprinted(self):
        paths = [f"/page-{i}" for i in range(30)] + [
            "/verwaltung/reglemente-uebersicht"
        ]
        fetcher = _ScriptedFetcher(
            {
                "https://a.example/sitemap.xml": _sitemap(paths),
                "https://a.example/verwaltung/reglemente-uebersicht": (
                    "<html>" + "<a href='/erlass/1.1'>x</a>" * 6 + "</html>"
                ),
            }
        )
        row = self._row()
        self.m.fingerprint(row, fetcher)
        self.assertEqual(row.outcome, "fingerprinted")
        self.assertIn("reglemente-uebersicht", row.collection_url)

    def test_complete_sitemap_without_collection_is_a_finding(self):
        """Muhen: 161 pages enumerated, not one a legal collection."""
        fetcher = _ScriptedFetcher(
            {"https://a.example/sitemap.xml": _sitemap([f"/p-{i}" for i in range(40)])}
        )
        row = self._row()
        self.m.fingerprint(row, fetcher)
        self.assertEqual(row.outcome, "no_collection_published")
        self.assertEqual(row.sitemap_entries, 40)
        self.assertIn("40 pages", row.note)

    def test_stub_sitemap_cannot_prove_absence(self):
        """Too few pages to support a claim about what the site does not contain."""
        fetcher = _ScriptedFetcher(
            {"https://a.example/sitemap.xml": _sitemap(["/", "/kontakt"])}
        )
        row = self._row()
        self.m.fingerprint(row, fetcher)
        self.assertEqual(row.outcome, "undiscovered")

    def test_no_sitemap_at_all_stays_undiscovered(self):
        row = self._row()
        self.m.fingerprint(row, _ScriptedFetcher({}))
        self.assertEqual(row.outcome, "undiscovered")
        self.assertIn("no sitemap", row.note)

    def test_sitemap_location_is_taken_from_robots_txt(self):
        fetcher = _ScriptedFetcher(
            {
                "https://a.example/robots.txt": "Sitemap: https://a.example/sm/all.xml",
                "https://a.example/sm/all.xml": _sitemap(
                    [f"/p-{i}" for i in range(40)]
                ),
            }
        )
        row = self._row()
        self.m.fingerprint(row, fetcher)
        self.assertEqual(row.sitemap_url, "https://a.example/sm/all.xml")
        self.assertEqual(row.outcome, "no_collection_published")

    def test_sitemap_index_is_followed_one_level(self):
        """Still followed — a child sitemap is how most large sites expose pages."""
        index = (
            "<?xml version='1.0'?><sitemapindex>"
            "<loc>https://a.example/sm-1.xml</loc></sitemapindex>"
        )
        fetcher = _ScriptedFetcher(
            {
                "https://a.example/sitemap.xml": index,
                "https://a.example/sm-1.xml": _sitemap([f"/p-{i}" for i in range(40)]),
            }
        )
        row = self._row()
        self.m.fingerprint(row, fetcher)
        self.assertEqual(row.sitemap_entries, 40)
        self.assertFalse(row.sitemap_complete)

    def test_sitemap_index_cannot_prove_absence(self):
        """One child of an index is a fragment, and a fragment proves nothing.

        This assertion was previously inverted -- the suite asserted that an index
        *should* yield `no_collection_published`, which is why the defect shipped
        green. Following one child is right for FINDING a collection and wrong for
        concluding there is none.
        """
        index = (
            "<?xml version='1.0'?><sitemapindex>"
            "<loc>https://a.example/sm-1.xml</loc>"
            "<loc>https://a.example/sm-2.xml</loc></sitemapindex>"
        )
        fetcher = _ScriptedFetcher(
            {
                "https://a.example/sitemap.xml": index,
                "https://a.example/sm-1.xml": _sitemap([f"/p-{i}" for i in range(40)]),
            }
        )
        row = self._row()
        self.m.fingerprint(row, fetcher)
        self.assertEqual(row.outcome, "undiscovered")
        self.assertIn("absence not claimable", row.note)

    def test_all_sitemaps_declared_in_robots_are_read(self):
        """robots.txt may declare one sitemap per section; one of them is not the site.

        Stadt Zürich's robots.txt declares a dozen. Reading only the first is how a
        collection that IS published gets missed.
        """
        robots = (
            "        Sitemap: https://a.example/friedhofforum/de.gsitemap.xml\n"
            "        Sitemap: https://a.example/politik/de.gsitemap.xml\n"
        )
        fetcher = _ScriptedFetcher(
            {
                "https://a.example/robots.txt": robots,
                "https://a.example/friedhofforum/de.gsitemap.xml": _sitemap(
                    [f"/friedhofforum/seite-{i}" for i in range(27)]
                ),
                "https://a.example/politik/de.gsitemap.xml": _sitemap(
                    ["/politik/rechtssammlung"]
                ),
                "https://a.example/politik/rechtssammlung": (
                    "<html>" + "<a href='/erlass/1.1'>x</a>" * 6 + "</html>"
                ),
            }
        )
        row = self._row()
        self.m.fingerprint(row, fetcher)
        self.assertEqual(row.outcome, "fingerprinted")
        self.assertIn("rechtssammlung", row.collection_url)

    def test_zurich_shaped_partial_sitemaps_do_not_deny_a_known_collection(self):
        """BFS 261 regression: the survey called Stadt Zürich unpublished.

        `communal_portals.yaml` registers www.stadt-zuerich.ch as the Amtliche
        Sammlung, "(verified)", and it is the only commune with a working
        gemeinde_http template. The 2026-07-22 full survey nonetheless recorded
        `no_collection_published`, because robots.txt declares a dozen section
        sitemaps, `re.search` took the first (Friedhofforum -- the cemetery forum),
        and its 27 pages were read as the whole city.

        Here the second declared sitemap is unreachable, so the set was NOT fully
        enumerated and absence must not be claimed from what was.

        Any absence logic that denies BFS 261 is wrong by construction.
        """
        robots = (
            "        Sitemap: https://a.example/friedhofforum/de.gsitemap.xml\n"
            "        Sitemap: https://a.example/politik/de.gsitemap.xml\n"
        )
        fetcher = _ScriptedFetcher(
            {
                "https://a.example/robots.txt": robots,
                "https://a.example/friedhofforum/de.gsitemap.xml": _sitemap(
                    [f"/friedhofforum/seite-{i}" for i in range(27)]
                ),
                # The sitemap that would carry the collection is not reachable.
            }
        )
        row = self._row()
        self.m.fingerprint(row, fetcher)
        self.assertFalse(row.sitemap_complete)
        self.assertNotEqual(
            row.outcome,
            "no_collection_published",
            "a fragment of the site must never license a claim about the whole site",
        )

    def test_french_and_italian_vocabulary_are_matched(self):
        for path in ("/recueil-systematique", "/reglements-communaux", "/regolamenti"):
            self.assertTrue(self.m.COLLECTION_VOCAB.search(path), f"{path} not matched")


class OfficialDomainTest(unittest.TestCase):
    """Wikidata's official host leads; DNS guesses remain as fallback."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load_module()

    def test_official_domain_is_probed_first(self):
        row = self.m.PortalRow(
            bfs_id=4003, name="Buchs (AG)", canton="ag", language="de"
        )
        row.candidate_domains = ["www.buchs-aargau.ch", "www.buchs.ch"]
        self.assertEqual(
            self.m.probe_urls(row)[0], "https://www.buchs-aargau.ch/rechtssammlung"
        )

    def test_cached_domains_are_reused_without_a_query(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / self.m.DOMAIN_CACHE_FILE).write_text(
                json.dumps({"4003": "www.buchs-aargau.ch"}), encoding="utf-8"
            )
            # No network: a miss here would raise trying to reach Wikidata.
            self.assertEqual(
                self.m.load_official_domains(cache), {"4003": "www.buchs-aargau.ch"}
            )


if __name__ == "__main__":
    unittest.main()
