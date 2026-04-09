# Country Overlays

Country overlays keep jurisdiction-specific content, mapping, and operator guidance
in one place, then sync into component-specific surfaces (contracts, legal-search,
platform-control).

Current overlays:

- `at/` — Austria

Each country overlay contains:

- `overlay.yaml` — canonical jurisdiction/source-family mapping metadata
- `user-content.yaml` — end-user label/copy overlays
- `operator-content.yaml` — operator onboarding/triage overlays
- `reference-data.yaml` — reference-data records expected in platform-control seeds
