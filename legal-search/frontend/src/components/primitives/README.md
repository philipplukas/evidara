# Primitives

Small, token-first UI building blocks for legal-search. Import from the barrel:

```ts
import { SectionLabel, StatusBadge, AccentButton } from "@/components/primitives";
```

## Exports (`index.ts`)

| Export | Role |
|--------|------|
| `SectionLabel` | Uppercase section headers |
| `InteractiveRow` | Clickable preview rows |
| `AccentButton` | Icon toggle (e.g. pin) |
| `ActionTextLink` | Micro text links with optional arrow |
| `Badge` | Document-type color pills (`colorKey` from BFF) |
| `StatusBadge` | Semantic status (healthy / degraded / …) with icon + label |

Add new primitives here and export them from `index.ts` so consumers stay on the public surface.
