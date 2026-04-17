# Country Overlays

Country overlays keep jurisdiction-specific content, mapping, and operator guidance
in one place, then sync into component-specific surfaces (contracts, legal-search,
platform-control).

Current overlays:

- `at/` — Austria
- `ch/` — Switzerland
- `de/` — Germany

Each country overlay contains:

- `overlay.yaml` — canonical jurisdiction/source-family mapping metadata
- `user-content.yaml` — end-user label/copy overlays
- `operator-content.yaml` — operator onboarding/triage overlays
- `reference-data.yaml` — reference-data records expected in platform-control seeds

Country overlays may additionally contain large or country-specific registries
that do not fit the curated `reference-data.yaml` pattern. These files are
scoped to a single overlay and documented inline. Current examples:

- `ch/municipalities.yaml` — Swiss municipality registry keyed by BFS number,
  with an optional `law_collection` block per municipality. Pilot subset only;
  full load from the BFS Gemeindeverzeichnis is out of scope for this file.
- `de/municipalities.yaml` — German municipality registry keyed by AGS
  (Amtlicher Gemeindeschlüssel), with the same `law_collection` shape. Pilot
  subset only; city-states (Berlin, Hamburg, Bremen) are intentionally
  covered at Land level and not duplicated here.
