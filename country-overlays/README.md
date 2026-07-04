# Country Overlays

Country overlays keep jurisdiction-specific content, mapping, and operator guidance
in one place, then sync into component-specific surfaces (contracts, legal-search,
platform-control).

> **License:** Overlay data in `country-overlays/` is licensed under **CC-BY-4.0**
> ([`/LICENSE-data`](../LICENSE-data)), not the AGPL-3.0 that covers the platform
> code. This covers Evidara's own mapping/structuring work; the underlying primary
> legal sources carry their own upstream terms, which each overlay must record.
> See [ADR-0028](../docs/adr/adr-0028-open-core-licensing.md).

Current overlays:

- `at/` — Austria
- `ch/` — Switzerland

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
