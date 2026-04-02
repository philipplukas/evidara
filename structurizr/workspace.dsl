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

        # --- Evidara platform ---
        evidara = softwareSystem "Evidara" "Document intelligence platform" {

            # --- platform-control ---
            platformControl = container "platform-control" "Source lifecycle, runs, approvals, reference data" "Cloud Run / FastAPI" {
                sourceRegistry = component "Source Registry" "Manages seed sources and source versions"
                runOrchestrator = component "Run Orchestrator" "Creates and tracks processing runs"
                approvalWorkflow = component "Approval Workflow" "Manages approval state for source versions"
                referenceData = component "Reference Data" "Jurisdictions, authorities, metadata"
            }

            # --- document-intelligence ---
            docIntelligence = container "document-intelligence" "Raw-to-canonical processing pipelines" "Databricks" {
                parser = component "Parser" "Extracts structure from raw artifacts (HTML, PDF)"
                segmenter = component "Segmenter" "Splits documents into sections"
                citationExtractor = component "Citation Extractor" "Identifies and normalizes legal citations"
                canonicalWriter = component "Canonical Writer" "Writes canonical entities to Delta tables"
                documentService = component "Document Service" "Read surface for lean/full document body from published Delta rows (BFF only)" "HTTPS / OpenAPI" {
                    tags "Read API"
                }
            }

            # --- legal-search ---
            legalSearch = container "legal-search" "Search and document detail experience" "Cloud Run" {
                frontend = component "Frontend" "Search UI, document detail, workspace" "Next.js"
                bff = component "BFF" "Backend-for-frontend, shapes data for UI" "NestJS"
                searchProjection = component "Search Projection" "Builds search-ready projections from canonical"
            }

            # --- Data stores ---
            postgres = container "PostgreSQL" "Source registry, runs, approvals, reference data" "Cloud SQL" "Database"
            deltaLake = container "Delta Lake" "Canonical document truth and published downstream surfaces" "Databricks / Cloud Storage" "Database"
            openSearch = container "OpenSearch" "Serving index and aliases for legal document projections" "OpenSearch Service" "Database"
            objectStorage = container "Cloud Storage" "Raw artifact files and immutable manifest objects" "GCS" "Database"
            pubSub = container "Pub/Sub" "Asynchronous event transport for bundle, processing-status, publication, and withdrawal events" "GCP Pub/Sub"
        }

        # --- External systems ---
        legalSources = softwareSystem "Legal Sources" "External legal document providers" "Existing System"

        # --- Relationships: People ---
        legalResearcher -> legalSearch "Searches and explores documents" "HTTPS"
        operator -> platformControl "Manages sources and monitors runs" "HTTPS"

        # --- Relationships: Platform flow ---
        legalSources -> platformControl "Provides raw legal artifacts"
        platformControl -> objectStorage "Stores raw artifacts and bundle manifests"
        platformControl -> pubSub "Publishes artifact bundle events"
        platformControl -> postgres "Persists source, run, approval state"

        pubSub -> docIntelligence "Delivers artifact bundle events"
        docIntelligence -> objectStorage "Reads raw artifacts and bundle manifests"
        docIntelligence -> deltaLake "Writes canonical documents, sections, processing manifests, and published surfaces"
        docIntelligence -> pubSub "Publishes processing status, document publication, and document withdrawal events"
        platformControl -> pubSub "Publishes artifact bundle and index update events"
        pubSub -> platformControl "Delivers processing status events"
        pubSub -> legalSearch "Delivers document publication, withdrawal, and index update events"

        legalSearch -> openSearch "Writes and queries search projections"

        # --- Internal component relationships ---
        frontend -> bff "API calls" "HTTPS / OpenAPI"
        bff -> openSearch "Search queries"
        bff -> documentService "Document detail reads (lean/full body)" "HTTPS / OpenAPI"
        documentService -> deltaLake "Queries published document / section / Docling surfaces only"
        pubSub -> searchProjection "Delivers publication and reindex events"
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
