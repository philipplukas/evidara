variable "dev_project_id" {
  description = "GCP project ID for the dev environment."
  type        = string
}

variable "prod_project_id" {
  description = "GCP project ID for the prod environment."
  type        = string
}

variable "region" {
  description = "Default region for provider configuration."
  type        = string
  default     = "europe-west6"
}

variable "wif_project_id" {
  description = "Optional project ID where the workload identity pool/provider is managed. Defaults to dev_project_id."
  type        = string
  default     = null
  nullable    = true
}

variable "github_owner" {
  description = "GitHub owner for repository restriction."
  type        = string
  default     = "philipplukas"
}

variable "github_repository" {
  description = "GitHub repository name for repository restriction."
  type        = string
  default     = "evidara"
}

variable "wif_pool_id" {
  description = "Workload identity pool ID."
  type        = string
  default     = "github"
}

variable "wif_provider_id" {
  description = "Workload identity pool provider ID."
  type        = string
  default     = "evidara"
}

variable "deployer_service_account_id_dev" {
  description = "Service account ID used by GitHub Actions for dev deploys."
  type        = string
  default     = "gha-deployer-dev"
}

variable "deployer_service_account_id_prod" {
  description = "Service account ID used by GitHub Actions for prod deploys."
  type        = string
  default     = "gha-deployer-prod"
}

variable "databricks_token_secret_name_dev" {
  description = "Secret Manager secret name for dev Databricks token."
  type        = string
  default     = "evidara-databricks-token-dev"
}

variable "databricks_token_secret_name_prod" {
  description = "Secret Manager secret name for prod Databricks token."
  type        = string
  default     = "evidara-databricks-token-prod"
}
