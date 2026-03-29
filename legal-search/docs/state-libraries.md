# Frontend State Libraries: How to Choose and Use Them

This project now uses a **hybrid state model**:

- **`nuqs`** for URL-driven state (selection, tabs, search context, facet refinements)
- **React Context + reducer-style actions** for local workspace interaction flows
- **React Query** for server-backed detail data

## Quick comparison

| Library | Best for | Tradeoffs |
|---|---|---|
| `nuqs` | Shareable UI state in URL (filters, pagination, selected entities) | Query-string schema design matters; avoid huge payloads |
| React Context + reducer | App-local interaction state with explicit actions | Can rerender broadly without selector optimization |
| Zustand | Medium/large local client state with selective subscriptions | Extra dependency + architecture discipline needed |
| Jotai | Fine-grained composable state atoms | Harder to reason globally in very large apps |
| Redux Toolkit | Very large apps needing strict patterns/tooling | More boilerplate for smaller product surfaces |
| React Query | Remote/server state with cache + async lifecycle | Not a replacement for all local UI state |

## Why this repo uses `nuqs` for facets

Facet and context constraints are part of search intent, so they should be:

1. **Linkable** (copy/paste URL)
2. **Restorable** (browser back/forward)
3. **Hydration-safe** in App Router

`nuqs` provides parser-based query-state handling that keeps these concerns explicit and typed.

## Practical pattern used here

1. Define parser schema for each query key.
2. Build `state` from parsed query values.
3. Expose dispatch-like actions that update query keys.
4. Keep server data in React Query and workspace navigation in local store.

This gives facet behavior that feels like app state, but remains URL-native.
