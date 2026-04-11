output "environment" {
  value = local.environment
}

output "raw_artifact_bucket_name" {
  value = google_storage_bucket.raw_artifacts.name
}

output "manifest_bucket_name" {
  value = google_storage_bucket.manifests.name
}

output "event_topic_names" {
  value = { for topic_name, topic in google_pubsub_topic.events : topic_name => topic.name }
}

output "event_subscription_names" {
  value = {
    for subscription_name, subscription in google_pubsub_subscription.events :
    subscription_name => subscription.name
  }
}

output "dead_letter_topic_names" {
  value = {
    for name, topic in google_pubsub_topic.dead_letter :
    name => topic.name
  }
}

output "dead_letter_subscription_names" {
  value = {
    for name, subscription in google_pubsub_subscription.dead_letter :
    name => subscription.name
  }
}

output "runtime_service_accounts" {
  value = {
    for key, account in google_service_account.runtime :
    key => account.email
  }
}

output "runtime_secret_ids" {
  value = {
    for key, secret in google_secret_manager_secret.runtime :
    key => secret.secret_id
  }
}

output "cloud_sql_instance_connection_name" {
  value = (
    var.enable_cloud_sql
    ? google_sql_database_instance.platform_control[0].connection_name
    : null
  )
}

output "cloud_run_service_names" {
  value = {
    for key, service in google_cloud_run_v2_service.runtime :
    key => service.name
  }
}

output "cloud_run_service_urls" {
  value = {
    for key, service in google_cloud_run_v2_service.runtime :
    key => service.uri
  }
}

output "cloud_run_job_names" {
  value = {
    for key, job in google_cloud_run_v2_job.runtime :
    key => job.name
  }
}

output "billing_budget_resource_name" {
  description = "Resource name of the project-scoped billing budget when enable_billing_budget is true (for API or Console deep links)."
  value       = var.enable_billing_budget ? google_billing_budget.project_spend[0].name : null
}
