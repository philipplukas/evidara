# Mermaid Diagram Style Guide

## When to use diagrams

| Situation | Tool |
|---|---|
| Architecture boundaries, deployments, system relationships | **Structurizr** (`structurizr/workspace.dsl`) |
| Feature flows, sequences, state machines, data flows in docs | **Mermaid** (inline in markdown) |
| Quick one-off sketches in PRs or issues | **Mermaid** (GitHub renders natively) |

**Rule:** Structurizr is the canonical architecture source. Mermaid is for docs-local explanatory diagrams. Do not duplicate Structurizr content as Mermaid.

## Diagram format policy

All diagrams in `docs/` **must** be Mermaid fenced code blocks:

````markdown
```mermaid
graph LR
    A --> B
```
````

**Not allowed:**

- ASCII art diagrams (hard to read, not searchable, not rendered)
- PlantUML (requires external rendering, not supported by GitHub or mkdocs natively)
- External image files for diagrams (cannot be diffed, go stale silently)
- Excalidraw/draw.io exports as images (same problem — not version-controlled as code)

**Note:** `docs/architecture/system-context.md` uses Mermaid for the high-level flow; detailed C4 views remain in Structurizr (`structurizr/workspace.dsl`).

## Mermaid theme

Use the `%%{init}%%` directive at the top of every diagram to set a consistent theme:

````markdown
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#4361ee', 'primaryTextColor': '#fff', 'primaryBorderColor': '#3a56d4', 'lineColor': '#6c757d', 'secondaryColor': '#e9ecef', 'tertiaryColor': '#f8f9fa'}}}%%
graph LR
    A[Service A] --> B[Service B]
```
````

Or for simpler diagrams where the defaults work well, use the `neutral` theme:

````markdown
```mermaid
%%{init: {'theme': 'neutral'}}%%
graph LR
    A --> B
```
````

## Standard node shapes

Use consistent shapes across all diagrams:

| Concept | Shape | Mermaid syntax |
|---|---|---|
| Service / application | Rounded rectangle | `A[Service Name]` |
| Database / store | Cylinder | `A[(Database)]` |
| External system | Hexagon | `A{{External System}}` |
| User / person | Stadium | `A([User])` |
| Decision / condition | Diamond | `A{Decision?}` |
| Event / message | Parallelogram | `A[/Event Name/]` |
| Process / step | Rectangle | `A[Step Name]` |

## Arrow styles

| Meaning | Syntax | Example |
|---|---|---|
| Synchronous call | `-->` | `A --> B` |
| Asynchronous / event | `-.->` | `A -.-> B` |
| Data flow | `==>` | `A ==> B` |
| With label | `-->\|label\|` | `A -->\|HTTPS\| B` |

## Standard diagram templates

### Container overview

Use for showing how components interact:

````markdown
```mermaid
%%{init: {'theme': 'neutral'}}%%
graph LR
    subgraph "platform-control"
        PC[Source Registry]
    end
    subgraph "document-intelligence"
        DI[Parser Pipeline]
    end
    subgraph "legal-search"
        LS[Search API]
    end

    PC -.->|bundle available event| DI
    DI ==>|canonical docs| DB[(Delta Lake)]
    DB ==>|projection| LS
    LS --> OS[(OpenSearch)]
```
````

### Sequence diagram

Use for request/response flows:

````markdown
```mermaid
%%{init: {'theme': 'neutral'}}%%
sequenceDiagram
    participant U as User
    participant FE as Next.js Frontend
    participant BFF as NestJS BFF
    participant OS as OpenSearch

    U->>FE: Search query
    FE->>BFF: GET /api/search?q=...
    BFF->>OS: OpenSearch query
    OS-->>BFF: Results
    BFF-->>FE: Shaped response
    FE-->>U: Rendered results
```
````

### State diagram

Use for lifecycle and workflow states:

````markdown
```mermaid
%%{init: {'theme': 'neutral'}}%%
stateDiagram-v2
    [*] --> Pending
    Pending --> Approved: approve()
    Pending --> Rejected: reject()
    Approved --> Running: startRun()
    Running --> Completed: success
    Running --> Failed: error
    Failed --> Running: retry()
    Completed --> [*]
```
````

### Data flow

Use for pipeline and transformation flows:

````markdown
```mermaid
%%{init: {'theme': 'neutral'}}%%
graph TD
    RAW[/Raw Artifact/] --> PARSE[Parse HTML/PDF]
    PARSE --> SEGMENT[Segment into Sections]
    SEGMENT --> CITE[Extract Citations]
    CITE --> CANON[(Canonical Document)]
    CANON --> PROJECT[Build Search Projection]
    PROJECT --> INDEX[(OpenSearch Index)]
```
````

### Entity relationship

Use for data model documentation:

````markdown
```mermaid
%%{init: {'theme': 'neutral'}}%%
erDiagram
    DOCUMENT ||--o{ SECTION : contains
    DOCUMENT ||--o{ CITATION : references
    SECTION ||--o{ CITATION : contains
    DOCUMENT {
        string document_id PK
        string title
        string jurisdiction
        string document_type
    }
    SECTION {
        string section_id PK
        string document_id FK
        int sequence
        string title
    }
    CITATION {
        string citation_id PK
        string document_id FK
        string normalized_ref
    }
```
````

## Naming conventions

- **Node IDs:** Short uppercase abbreviations (`PC`, `DI`, `LS`, `OS`)
- **Labels:** Full human-readable names in brackets (`[Source Registry]`)
- **Subgraph titles:** Component names in quotes (`"platform-control"`)
- **Arrow labels:** Protocol or verb (`|HTTPS|`, `|event|`, `|reads|`)

## Size guidelines

- Keep diagrams **under 15 nodes.** If larger, split into multiple diagrams.
- One diagram per concept. Don't try to show everything in one picture.
- Prefer `LR` (left-right) for flow diagrams, `TD` (top-down) for hierarchies.

## Review checklist for diagrams

When reviewing a PR with diagrams, check:

- [ ] Is it Mermaid (not ASCII, PlantUML, or an image)?
- [ ] Does it use the standard theme directive?
- [ ] Are node shapes consistent with the table above?
- [ ] Is it under 15 nodes?
- [ ] Does it duplicate Structurizr content? (If so, it should reference Structurizr instead)
- [ ] Does it render correctly in the GitHub markdown preview?
