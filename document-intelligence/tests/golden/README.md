# Golden Bundle Fixtures

Each fixture directory contains:

- `event.json`: bundle event template with `__MANIFEST_*__` placeholders
- `bundle-manifest.json`: manifest template with `__ARTIFACT_*__` placeholders
- `document.html`, `document.xml`, or `document.json`: primary artifact content
- `expected.json`: assertions for the golden test

The tests materialize each fixture into a temporary working directory, replace the path, size, and checksum placeholders, then run the normal bundle-based pipeline against the generated files.

Optional `expected.json` field **`metadata_eval`**: when present, `tests/metadata_eval.py` (and `tests/test_metadata_eval.py` in CI) runs the pipeline and checks title substrings, `document_type`, `source_family`, and `llm_invoked` expectations, grouped by manifest `jurisdiction_id`.

Current fixture coverage:

- `simple_html`: straightforward title and heading extraction
- `messy_html`: noisy HTML with navigation and footer content around the main body
- `nested_headings`: top-level and nested heading ordering
- `no_heading_fallback`: body-only content with no headings
- `html_div_fallback`: HTML parsed via div fallback path
- `ris_xml`: RIS-style XML with legal section labels and extracted metadata (synthetic)
- `invalid_no_primary`: failure path when the bundle lacks a selectable primary artifact
- `ris_xml_law_short`: real BGBl. II Nr. 74/2026 — short Verordnung (Notarstelle Wien-Favoriten)
- `ris_xml_law_consolidated`: real consolidated Bundesnorm (NOR11013238)
- `ris_xml_decision_vfgh`: real VfGH Rechtssatz V258/2025 — zoning plan annulment
- `ris_xml_decision_vwgh`: real VwGH Rechtssatz (JWR_2024190104_20260312L01)
- `ris_html_decision_vfgh`: same VfGH decision in HTML format
- `ris_html_decision_vwgh`: same VwGH decision in HTML format
- `ch_commentary_html`: synthetic Swiss German commentary with provision and case-law anchors
- `ch_fedlex_law_html`: Swiss Fedlex constitution excerpt (Bundesverfassung, SR 101) — article-level `Art. N` headings, SR + article citation forms
- `ch_fedlex_bv_html`: the **real, full** Bundesverfassung (SR 101, Stand 3. März 2024) as served by Fedlex — 232 `<article id="art_N">` provisions nested under `<section>` chapters. Guards #573: the whole statute must not collapse into one section. Source: `https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/1999/404/20240303/de/html/fedlex-data-admin-ch-eli-cc-1999-404-20240303-de-html-4.html` (public Swiss federal law)

Optional `expected.json` fields **`section_max_content_length`** (no single section may exceed it — catches "the whole document became one section") and **`key_section_anchors`** (section title → in-document anchor id, e.g. `art_36`).
