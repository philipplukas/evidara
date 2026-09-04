/*
 * Evidara — Document Intelligence Platform
 * Canonical architecture definition (C4 model)
 *
 * This is the source of truth for system architecture.
 * Update this file when domain boundaries, deployments,
 * or inter-component relationships change.
 *
 * Validate: structurizr validate -workspace structurizr/workspace.dsl
 * Render:   docker run -it --rm -p 8080:8080 -v ./structurizr:/usr/local/structurizr structurizr/lite
 */

workspace "Evidara" "Document intelligence platform for legal research" {

    model {
        # --- People ---
        legalResearcher = person "Legal Researcher" "Searches and explores legal documents"
        operator = person "Operator" "Manages sources, approvals, runs, and monitors system health"
        prospect = person "Prospective User" "Evaluating Evidara; has no account and no access to the product"

        # --- Evidara platform ---
        evidara = softwareSystem "Evidara" "Document intelligence platform" {

            # --- platform-control ---
            platformControl = container "platform-control" "Source lifecycle, runs, approvals, reference data" "Kubernetes (k3s) / FastAPI" {
                sourceRegistry = component "Source Registry" "Manages seed sources and source versions"
                runOrchestrator = component "Run Orchestrator" "Creates and tracks processing runs"
                approvalWorkflow = component "Approval Workflow" "Manages approval state for source versions"
                referenceData = component "Reference Data" "Jurisdictions, authorities, metadata"
            }
            platformControlAdmin = container "platform-control-admin" "Internal control-plane admin UI for operators" "Kubernetes (k3s) / Next.js + React-admin"

            # --- document-intelligence ---
            docIntelligence = container "document-intelligence" "Raw-to-canonical processing pipelines" "Kubernetes (k3s) / Python queue consumer" {
                parser = component "Parser" "Extracts structure from raw artifacts (HTML, PDF)"
                segmenter = component "Segmenter" "Splits documents into sections"
                citationExtractor = component "Citation Extractor" "Identifies and normalizes legal citations"
                canonicalWriter = component "Canonical Writer" "Writes canonical entities to Delta tables"
                documentService = component "Document Service" "Read surface for lean/full document body from published Delta rows (BFF only)" "HTTPS / OpenAPI" {
                    tags "Read API"
                }
            }

            # --- legal-search ---
            legalSearch = container "legal-search" "Search and document detail experience" "Kubernetes (k3s)" {
                frontend = component "Frontend" "Search UI, document detail, workspace" "Next.js"
                bff = component "BFF" "Backend-for-frontend, shapes data for UI" "NestJS"
                searchProjection = component "Search Projection" "Builds search-ready projections from canonical"
            }

            # --- marketing (ADR-0039) ---
            # Statically exported; NO server runtime and NO dependency on any
            # other container. The absence of an arrow from `marketing` to
            # anything else in this model is the architectural point: the only
            # publicly reachable surface cannot reach the control plane, the
            # search API, or any data store.
            #
            # DEPLOYED 2026-09-04, but temporarily behind the shared BasicAuth
            # middleware at the operator's request, so the `prospect -> marketing`
            # edge below is an intention rather than the runtime until that
            # annotation is removed from infra/hetzner/marketing/ingress-tls.yaml.
            # The `Public` tag describes the container's design posture (no server
            # runtime, no secret, no reachable neighbour), which is unchanged by
            # the password.
            marketing = container "marketing" "Public waitlist and positioning page" "Kubernetes (k3s) / Next.js static export behind Traefik" {
                tags "Public"
            }

            # --- Data stores (all self-hosted in-cluster; see ADR-0029) ---
            postgres = container "PostgreSQL" "Source registry, runs, approvals, reference data" "CloudNativePG" "Database"
            deltaLake = container "Delta Lake" "Canonical document truth and published downstream surfaces" "Delta on MinIO (pure-Python deltalake); queried via Nessie + Trino" "Database"
            openSearch = container "OpenSearch" "Serving index and aliases for legal document projections" "OpenSearch" "Database"
            objectStorage = container "Object Storage" "Raw artifact files and immutable manifest objects" "MinIO (S3-compatible)" "Database"
            broker = container "NATS JetStream" "Asynchronous event transport for bundle, processing-status, publication, and withdrawal events" "NATS JetStream"

            # --- Identity (ADR-0038) ---
            # Deployed (ADR-0038 §8 step 2) and load-bearing for NOTHING yet. There
            # are deliberately no arrows from any application to this container: no
            # app authenticates against it, and both UIs are still behind one shared
            # BasicAuth password. The edges appear with §8 steps 4-7 (assertion seam,
            # then Auth.js login on admin, then on legal-search). Drawing them now
            # would model an intention, not the runtime.
            zitadel = container "Zitadel" "Self-hosted OIDC provider: users, organizations, sessions, login UI" "Kubernetes (k3s) / Zitadel (Go), Postgres-backed"
        }

        # --- External systems ---
        legalSources = softwareSystem "Legal Sources" "External legal document providers" "Existing System"

        # --- Relationships: People ---
        legalResearcher -> legalSearch "Searches and explores documents" "HTTPS"
        operator -> platformControlAdmin "Manages sources and monitors runs" "HTTPS"
        # The prospect reaches ONLY the marketing page. There is deliberately
        # no `prospect -> legalSearch` edge: until user identity exists
        # (ADR-0038), there is no way to let a stranger into the product
        # without handing them the shared operator password. See ADR-0039.
        prospect -> marketing "Reads positioning, joins the waitlist" "HTTPS"

        # --- Relationships: Platform flow ---
        legalSources -> platformControl "Provides raw legal artifacts"
        platformControl -> objectStorage "Stores raw artifacts and bundle manifests"
        platformControl -> broker "Publishes artifact bundle events"
        platformControl -> postgres "Persists source, run, approval state"
        platformControlAdmin -> platformControl "Calls operator read and business APIs" "HTTPS / OpenAPI"

        broker -> docIntelligence "Delivers artifact bundle events"
        docIntelligence -> objectStorage "Reads raw artifacts and bundle manifests"
        docIntelligence -> deltaLake "Writes canonical documents, sections, processing manifests, and published surfaces"
        docIntelligence -> broker "Publishes processing status, document publication, and document withdrawal events"
        platformControl -> broker "Publishes artifact bundle and index update events"
        broker -> platformControl "Delivers processing status events"
        broker -> legalSearch "Delivers document publication, withdrawal, and index update events"

        legalSearch -> openSearch "Writes and queries search projections"

        # The one real edge Zitadel has today: its own database in the same CNPG
        # instance as platform-control's (ADR-0038 §2 reason 2 — one backup story,
        # not two), under its own Postgres role.
        zitadel -> postgres "Persists users, organizations, and sessions in the `zitadel` database"

        # --- Internal component relationships ---
        frontend -> bff "API calls" "HTTPS / OpenAPI"
        bff -> openSearch "Search queries"
        bff -> documentService "Document detail reads (lean/full body)" "HTTPS / OpenAPI"
        documentService -> deltaLake "Queries published document / section / Docling surfaces only"
        broker -> searchProjection "Delivers publication and reindex events"
        searchProjection -> deltaLake "Reads published canonical surfaces for projection build"
        searchProjection -> openSearch "Writes projections and alias updates"

        sourceRegistry -> postgres "CRUD"
        runOrchestrator -> postgres "CRUD"
        approvalWorkflow -> postgres "CRUD"

        parser -> segmenter "Passes parsed documents"
        segmenter -> citationExtractor "Passes sections"
        citationExtractor -> canonicalWriter "Passes enriched entities"
        canonicalWriter -> deltaLake "Writes"
    }

    views {
        systemContext evidara "SystemContext" {
            include *
            description "System context — Evidara and its users"
            autolayout lr
        }

        container evidara "Containers" {
            include *
            description "Container view — runtime components and data stores"
            autolayout lr
        }

        component platformControl "PlatformControl" {
            include *
            description "platform-control internal components"
            autolayout lr
        }

        component docIntelligence "DocumentIntelligence" {
            include *
            description "document-intelligence internal components"
            autolayout lr
        }

        component legalSearch "LegalSearch" {
            include *
            description "legal-search internal components"
            autolayout lr
        }

        styles {
            element "Software System" {
                background #1168bd
                color #ffffff
                shape RoundedBox
            }
            element "Existing System" {
                background #999999
                color #ffffff
            }
            element "Person" {
                background #08427b
                color #ffffff
                shape Person
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "Database" {
                shape Cylinder
            }
            element "Read API" {
                background #2a9d8f
                color #ffffff
                stroke #1d7066
                strokeWidth 2
            }
        }
    }
}
