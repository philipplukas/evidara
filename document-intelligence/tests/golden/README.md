# Golden Bundle Fixtures

Each fixture directory contains:

- `event.json`: bundle event template with `__MANIFEST_*__` placeholders
- `bundle-manifest.json`: manifest template with `__ARTIFACT_*__` placeholders
- `document.html`, `document.xml`, or `document.json`: primary artifact content
- `expected.json`: assertions for the golden test

The tests materialize each fixture into a temporary working directory, replace the path, size, and checksum placeholders, then run the normal bundle-based pipeline against the generated files.

Current fixture coverage:

- `simple_html`: straightforward title and heading extraction
- `messy_html`: noisy HTML with navigation and footer content around the main body
- `nested_headings`: top-level and nested heading ordering
- `no_heading_fallback`: body-only content with no headings
- `ris_xml`: RIS-style XML with legal section labels and extracted metadata
- `invalid_no_primary`: failure path when the bundle lacks a selectable primary artifact
