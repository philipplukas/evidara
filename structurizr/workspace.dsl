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
            platformControl = container "platform-control" "Source lifecycle, runs, approvals, reference data" "Cloud Run / NestJS" {
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
            }

            # --- legal-search ---
            legalSearch = container "legal-search" "Search and document detail experience" "Cloud Run" {
                frontend = component "Frontend" "Search UI, document detail, workspace" "Next.js"
                bff = component "BFF" "Backend-for-frontend, shapes data for UI" "NestJS"
                searchProjection = component "Search Projection" "Builds search-ready projections from canonical"
            }

            # --- Data stores ---
            postgres = container "PostgreSQL" "Source registry, runs, approvals, reference data" "Cloud SQL" "Database"
            deltaLake = container "Delta Lake" "Canonical document truth" "Databricks / Cloud Storage" "Database"
            openSearch = container "OpenSearch" "Search index for legal documents" "OpenSearch Service" "Database"
            objectStorage = container "Cloud Storage" "Raw artifact files" "GCS" "Database"
        }

        # --- External systems ---
        legalSources = softwareSystem "Legal Sources" "External legal document providers" "Existing System"

        # --- Relationships: People ---
        legalResearcher -> legalSearch "Searches and explores documents" "HTTPS"
        operator -> platformControl "Manages sources and monitors runs" "HTTPS"

        # --- Relationships: Platform flow ---
        legalSources -> platformControl "Provides raw legal artifacts"
        platformControl -> objectStorage "Stores raw artifacts"
        platformControl -> docIntelligence "Triggers processing runs" "Event / API"
        platformControl -> postgres "Persists source, run, approval state"

        docIntelligence -> objectStorage "Reads raw artifacts"
        docIntelligence -> deltaLake "Writes canonical documents, sections, citations"
        docIntelligence -> platformControl "Reports run results" "Event"

        legalSearch -> openSearch "Queries search index"
        legalSearch -> deltaLake "Reads canonical data (projection building)"

        # --- Internal component relationships ---
        frontend -> bff "API calls" "HTTPS / OpenAPI"
        bff -> openSearch "Search queries"
        bff -> searchProjection "Builds projections"

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
        }
    }
}
