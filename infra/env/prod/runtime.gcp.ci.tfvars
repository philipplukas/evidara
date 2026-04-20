project_id = "evidara-prod"

runtime_service_account_ids = {
  platform_control_api    = "evd-pc-api"
  platform_control_admin  = "evd-pc-admin"
  platform_control_worker = "evd-pc-worker"
  legal_search_api        = "evd-ls-api"
  legal_search_frontend   = "evd-ls-frontend"
  document_intelligence   = "evd-di-consumer"
}

# CI plan project may not have the published-surfaces bucket; optional IAM is skipped.
document_intelligence_published_bucket_name = null
# Avoid push_endpoint resolution against real Cloud Run URLs in ephemeral CI plans.
artifact_bundle_subscription_push = null
