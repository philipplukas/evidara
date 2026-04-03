output "wif_provider_resource_name" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account_email_dev" {
  value = google_service_account.deployer_dev.email
}

output "deployer_service_account_email_prod" {
  value = google_service_account.deployer_prod.email
}

output "databricks_token_secret_name_dev" {
  value = google_secret_manager_secret.databricks_token_dev.secret_id
}

output "databricks_token_secret_name_prod" {
  value = google_secret_manager_secret.databricks_token_prod.secret_id
}
