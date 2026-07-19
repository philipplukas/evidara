# ============================================================================
# DEPRECATED — GCP prod runtime. ADR-0029 replaced this with self-hosted Hetzner
# k3s; the live prod runtime is `infra/hetzner/` + `k8s/gitops/`, and this stack's
# `terraform destroy` is the last open item of ADR-0029 Slice 6.
#
# Do not add new services or secrets here. If you are provisioning something for
# the runtime that actually serves traffic, it belongs in `infra/hetzner/apps/`.
#
# Known gap, left deliberately unfixed: this file declares no
# PLATFORM_CONTROL_OPERATOR_API_KEY / API_KEY for `platform-control-api` or
# `legal-search-api`. On the live Hetzner runtime those keys ARE provisioned —
# `infra/hetzner/deploy-stage5.sh` creates the `evidara-auth` Secret and the
# Deployments consume it — so the gap is confined to this dead stack. Plumbing
# secrets into a stack that is being destroyed would be the wrong fix. What was
# fixed instead is the app-side fail-open the gap depended on: both APIs now
# refuse traffic (503) when no key is configured rather than serving everything.
# ============================================================================

environment = "prod"

project_id      = "evidara-prod"
region          = "europe-west6"
bucket_location = "EUROPE-WEST6"

# Runtime Pub/Sub defaults (runtime_stack `variables.tf`) create topics without an env suffix
# and push `document-processing-status-updated` / `document-processed` to platform-control-api
# unless overridden. Prod inherits those unsuffixed topic names (see di-consumer env_vars below).

raw_artifact_bucket_name = "evidara-raw-artifacts-prod"
manifest_bucket_name     = "evidara-manifests-prod"

document_intelligence_published_bucket_name = "evidara-document-intelligence-surfaces-prod"

artifact_bundle_subscription_push = {
  subscription_key = "document-intelligence-artifact-bundle-available"
  target_service   = "di-consumer"
}

enable_cloud_sql       = true
cloud_sql_tier         = "db-custom-2-7680"
cloud_sql_disk_size_gb = 50

cloud_run_services = {
  "platform-control-api" = {
    image                 = "europe-west6-docker.pkg.dev/evidara-prod/runtime/platform-control:latest"
    service_account_key   = "platform_control_api"
    allow_unauthenticated = false
    vpc_connector         = "projects/evidara-prod/locations/europe-west6/connectors/evidara-search-prod-connector"
    vpc_egress            = "PRIVATE_RANGES_ONLY"
    cloud_sql_instances   = ["evidara-prod:europe-west6:evidara-control-prod"]
    env_vars = {
      PLATFORM_CONTROL_GCP_PROJECT_ID               = "evidara-prod"
      PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND       = "gcs"
      PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND      = "pubsub"
      PLATFORM_CONTROL_RAW_ARTIFACT_BUCKET          = "evidara-raw-artifacts-prod"
      PLATFORM_CONTROL_RAW_ARTIFACT_PUBSUB_TOPIC    = "raw-artifact-available"
      PLATFORM_CONTROL_ARTIFACT_BUNDLE_PUBSUB_TOPIC = "artifact-bundle-available"
      # Keep acquisition dispatch off the API process; `platform-control-worker` polls `dispatch_pending_runs`.
      PLATFORM_CONTROL_RUN_DISPATCH_BACKEND = "worker"
      # PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_RECORD_DIR = "/var/firecrawl-webhook-log"
      # ^ Leave commented until a durable GCS FUSE mount is added under volumes (see #254).
    }
    secret_env_vars = {
      PLATFORM_CONTROL_DATABASE_URL = {
        secret_name = "platform_control_dsn"
      }
      PLATFORM_CONTROL_FIRECRAWL_API_KEY = {
        secret_name = "firecrawl_api_key"
      }
      PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_SECRET = {
        secret_name = "firecrawl_webhook"
      }
    }
  }

  "legal-search-api" = {
    image                 = "europe-west6-docker.pkg.dev/evidara-prod/runtime/legal-search-api:latest"
    service_account_key   = "legal_search_api"
    allow_unauthenticated = false
    env_vars = {
      OPENSEARCH_ALIAS_READ               = "evidara-documents-read-prod"
      OPENSEARCH_ALIAS_WRITE              = "evidara-documents-write-prod"
      OPENSEARCH_INDEX_SECTIONS           = "evidara-sections-read-prod"
      OPENSEARCH_INDEX_CITATIONS          = "evidara-citations-read-prod"
      OPENSEARCH_INDEX_PROJECTION_HISTORY = "evidara-projection-history-prod"
      # TODO: replace after first terraform apply creates services (placeholder Cloud Run hostname).
      DOCUMENT_INTELLIGENCE_BASE_URL = "https://document-intelligence-document-service-prod.example.run.app"
    }
    secret_env_vars = {
      OPENSEARCH_NODE = {
        secret_name = "opensearch_node"
      }
      OPENSEARCH_USERNAME = {
        secret_name = "opensearch_username"
      }
      OPENSEARCH_PASSWORD = {
        secret_name = "opensearch_password"
      }
      DOCUMENT_INTELLIGENCE_API_KEY = {
        secret_name = "document_service_bearer_token"
      }
    }
    vpc_connector = "projects/evidara-prod/locations/europe-west6/connectors/evidara-search-prod-connector"
    vpc_egress    = "PRIVATE_RANGES_ONLY"
  }

  "document-intelligence-document-service" = {
    image               = "europe-west6-docker.pkg.dev/evidara-prod/runtime/document-intelligence-document-service:latest"
    service_account_key = "document_intelligence"
    # Was `true` — i.e. the `allUsers` IAM binding, an anonymous public endpoint on a
    # service that reads published Delta rows. Its only other credential is
    # DOCUMENT_SERVICE_BEARER_TOKEN, and nothing external needs to call it: the sole
    # caller is legal-search-api, in-cluster, via DOCUMENT_INTELLIGENCE_BASE_URL.
    #
    # This stack is dead (see the banner at the top of this file), so the practical
    # exposure today is nil — but it is flipped rather than left, because "dead" is a
    # claim about the world, not about the file, and a `terraform apply` from anyone
    # who believes otherwise would open it. The equivalent on the live runtime is
    # `infra/hetzner/apps/document-intelligence.yaml`, whose document-service is a
    # ClusterIP Service with no Ingress — not internet-reachable.
    allow_unauthenticated = false
    startup_probe_path    = "/health"
    liveness_probe_path   = "/health"
    env_vars = {
      DI_SURFACES_ROOT_URI = "gs://evidara-document-intelligence-surfaces-prod/published"
    }
    secret_env_vars = {
      DOCUMENT_SERVICE_BEARER_TOKEN = {
        secret_name = "document_service_bearer_token"
      }
    }
    vpc_connector = "projects/evidara-prod/locations/europe-west6/connectors/evidara-search-prod-connector"
    vpc_egress    = "PRIVATE_RANGES_ONLY"
  }

  "platform-control-admin" = {
    image                 = "europe-west6-docker.pkg.dev/evidara-prod/runtime/platform-control-admin:latest"
    service_account_key   = "platform_control_admin"
    allow_unauthenticated = false
    env_vars = {
      # TODO: replace after first terraform apply creates services (placeholder Cloud Run hostname).
      PLATFORM_CONTROL_API_URL = "https://platform-control-api-prod.example.run.app"
    }
    vpc_connector = "projects/evidara-prod/locations/europe-west6/connectors/evidara-search-prod-connector"
    vpc_egress    = "PRIVATE_RANGES_ONLY"
  }

  "legal-search-frontend" = {
    image                 = "europe-west6-docker.pkg.dev/evidara-prod/runtime/legal-search-frontend:latest"
    service_account_key   = "legal_search_frontend"
    allow_unauthenticated = false
    env_vars = {
      # TODO: replace after first terraform apply creates services (placeholder Cloud Run hostnames).
      NEXT_PUBLIC_API_URL           = "https://legal-search-api-prod.example.run.app"
      NEXT_PUBLIC_CONTROL_PANEL_URL = "https://platform-control-admin-prod.example.run.app"
    }
    vpc_connector = "projects/evidara-prod/locations/europe-west6/connectors/evidara-search-prod-connector"
    vpc_egress    = "PRIVATE_RANGES_ONLY"
  }

  "platform-control-worker" = {
    image                 = "europe-west6-docker.pkg.dev/evidara-prod/runtime/platform-control-worker:latest"
    service_account_key   = "platform_control_worker"
    allow_unauthenticated = false
    min_instance_count    = 1
    max_instance_count    = 1
    startup_probe_path    = "/health"
    liveness_probe_path   = "/health"
    vpc_connector         = "projects/evidara-prod/locations/europe-west6/connectors/evidara-search-prod-connector"
    vpc_egress            = "PRIVATE_RANGES_ONLY"
    cloud_sql_instances   = ["evidara-prod:europe-west6:evidara-control-prod"]
    env_vars = {
      PLATFORM_CONTROL_GCP_PROJECT_ID               = "evidara-prod"
      PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND       = "gcs"
      PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND      = "pubsub"
      PLATFORM_CONTROL_RAW_ARTIFACT_BUCKET          = "evidara-raw-artifacts-prod"
      PLATFORM_CONTROL_RAW_ARTIFACT_PUBSUB_TOPIC    = "raw-artifact-available"
      PLATFORM_CONTROL_ARTIFACT_BUNDLE_PUBSUB_TOPIC = "artifact-bundle-available"
      PLATFORM_CONTROL_RUN_DISPATCH_BACKEND         = "worker"
    }
    secret_env_vars = {
      PLATFORM_CONTROL_DATABASE_URL = {
        secret_name = "platform_control_dsn"
      }
      PLATFORM_CONTROL_FIRECRAWL_API_KEY = {
        secret_name = "firecrawl_api_key"
      }
    }
  }

  "di-consumer" = {
    image                 = "europe-west6-docker.pkg.dev/evidara-prod/runtime/di-consumer:latest"
    service_account_key   = "document_intelligence"
    allow_unauthenticated = false
    min_instance_count    = 0
    startup_probe_path    = "/health"
    liveness_probe_path   = "/health"
    env_vars = {
      DI_GCP_PROJECT_ID                  = "evidara-prod"
      DI_EVENT_PUBLISHER_BACKEND         = "pubsub"
      DI_STATUS_TOPIC_NAME               = "document-processing-status-updated"
      DI_PROCESSED_TOPIC_NAME            = "document-processed"
      DI_DOCUMENT_PROCESSED_PUBSUB_TOPIC = "document-processed"
      DI_SURFACES_ROOT_URI               = "gs://evidara-document-intelligence-surfaces-prod/published"
      DI_PROCESSING_VERSION              = "0.1.0"
      DI_PARSER_BACKEND                  = "legacy"
    }
  }
}

cloud_run_jobs = {
  "platform-control-db-migrate" = {
    image               = "europe-west6-docker.pkg.dev/evidara-prod/runtime/platform-control:latest"
    service_account_key = "platform_control_api"
    command             = ["sh"]
    args = [
      "-lc",
      <<-EOT
      set -euo pipefail
      if [ -f /app/alembic.ini ]; then
        (cd /app && alembic -c alembic.ini upgrade head) || echo "Alembic migration failed; applying metadata bootstrap fallback."
      else
        echo "Missing /app/alembic.ini; applying metadata bootstrap fallback."
      fi
      python - <<'PY'
      import asyncio
      import platform_control.models  # noqa: F401
      from platform_control.config import get_settings
      from platform_control.models.base import Base
      from sqlalchemy.ext.asyncio import create_async_engine


      async def main() -> None:
          engine = create_async_engine(get_settings().database_url)
          async with engine.begin() as conn:
              await conn.run_sync(Base.metadata.create_all)
          await engine.dispose()


      asyncio.run(main())
      print("platform-control schema bootstrap complete")
      PY
      EOT
    ]
    timeout_seconds     = 900
    max_retries         = 1
    vpc_connector       = "projects/evidara-prod/locations/europe-west6/connectors/evidara-search-prod-connector"
    vpc_egress          = "PRIVATE_RANGES_ONLY"
    cloud_sql_instances = ["evidara-prod:europe-west6:evidara-control-prod"]
    secret_env_vars = {
      PLATFORM_CONTROL_DATABASE_URL = {
        secret_name = "platform_control_dsn"
      }
    }
  }

  # NOTE (#713): there is deliberately NO `os-alias-bootstrap` job here any more.
  # It created the documents index with `{"settings":{...}}` and no `mappings`, so
  # every field fell back to OpenSearch dynamic mapping — the inverse of the
  # canonical convention (bare `text` that cannot aggregate, `.keyword` that can)
  # and with no `legal_text` analyzer, a silent recall loss on a German corpus.
  # Because it ran before the API and creation is first-writer-wins, it pre-empted
  # the API's own bootstrap permanently.
  #
  # The documents index has ONE creation path: `bootstrapDocumentsIndex()` in
  # legal-search/api/src/core/opensearch/documents-bootstrap.ts, invoked from
  # main.ts on startup, deriving from the canonical mapping. That is also how the
  # live Hetzner runtime (ADR-0029) provisions it. `os-alias-check` below stays as
  # the read-only preflight. See AGENTS.md "The documents-index mapping has one
  # source of truth".

  "os-alias-check" = {
    image               = "curlimages/curl:8.10.1"
    service_account_key = "legal_search_api"
    command             = ["sh"]
    args = [
      "-lc",
      "set -euo pipefail; NODE=\"$${OPENSEARCH_NODE%/}\"; AUTH=\"$${OPENSEARCH_USERNAME}:$${OPENSEARCH_PASSWORD}\"; for alias in \"$${OPENSEARCH_ALIAS_READ}\" \"$${OPENSEARCH_ALIAS_WRITE}\"; do if ! curl -fsS -u \"$${AUTH}\" \"$${NODE}/_alias/$${alias}\" >/dev/null; then echo \"Missing OpenSearch alias '$${alias}' in prod. The legal-search-api startup bootstrap creates the index and both aliases from the canonical mapping; redeploy or restart legal-search-api-prod (OPENSEARCH_BOOTSTRAP_ON_STARTUP must not be false), then rerun smoke.\" >&2; exit 1; fi; done; echo 'OpenSearch aliases exist and are reachable.'"
    ]
    timeout_seconds = 300
    max_retries     = 0
    vpc_connector   = "projects/evidara-prod/locations/europe-west6/connectors/evidara-search-prod-connector"
    vpc_egress      = "PRIVATE_RANGES_ONLY"
    env_vars = {
      OPENSEARCH_ALIAS_READ  = "evidara-documents-read-prod"
      OPENSEARCH_ALIAS_WRITE = "evidara-documents-write-prod"
    }
    secret_env_vars = {
      OPENSEARCH_NODE = {
        secret_name = "opensearch_node"
      }
      OPENSEARCH_USERNAME = {
        secret_name = "opensearch_username"
      }
      OPENSEARCH_PASSWORD = {
        secret_name = "opensearch_password"
      }
    }
  }
}

runtime_service_account_ids = {
  platform_control_api    = "evd-pc-api"
  platform_control_admin  = "evd-pc-admin"
  platform_control_worker = "evd-pc-worker"
  legal_search_api        = "evd-ls-api"
  legal_search_frontend   = "evd-ls-frontend"
  document_intelligence   = "evd-di-consumer"
}

# --- Optional billing guardrails (Cloud Billing budgets) ---
# See infra/terraform/gcp/runtime_stack/billing_guardrails.tf and dev/runtime.gcp.tfvars.example.
# enable_billing_budget = false

enable_billing_budget = false
