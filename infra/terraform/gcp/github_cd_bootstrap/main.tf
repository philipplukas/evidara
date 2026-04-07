locals {
  repo_slug = "${var.github_owner}/${var.github_repository}"
}

resource "google_iam_workload_identity_pool" "github" {
  provider = google.wif

  workload_identity_pool_id = var.wif_pool_id
  display_name              = "GitHub Actions Pool"
  description               = "OIDC identity pool for Evidara GitHub Actions."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  provider = google.wif

  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = var.wif_provider_id
  display_name                       = "Evidara GitHub Provider"
  description                        = "OIDC provider for github.com token.actions.githubusercontent.com"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository=='${local.repo_slug}'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer_dev" {
  account_id   = var.deployer_service_account_id_dev
  display_name = "GitHub deployer (dev)"
}

resource "google_service_account" "deployer_prod" {
  provider = google.prod

  account_id   = var.deployer_service_account_id_prod
  display_name = "GitHub deployer (prod)"
}

resource "google_service_account_iam_member" "deployer_dev_wif_user" {
  service_account_id = google_service_account.deployer_dev.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.repo_slug}"
}

resource "google_service_account_iam_member" "deployer_prod_wif_user" {
  provider = google.prod

  service_account_id = google_service_account.deployer_prod.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.repo_slug}"
}

resource "google_project_iam_member" "deployer_dev_roles" {
  for_each = toset([
    "roles/run.admin",
    "roles/artifactregistry.writer",
    "roles/iam.serviceAccountUser",
    "roles/secretmanager.secretAccessor",
  ])

  project = var.dev_project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer_dev.email}"
}

resource "google_storage_bucket_iam_member" "deployer_dev_bucket_object_admin" {
  for_each = var.deployer_dev_storage_object_admin_buckets

  bucket = each.value
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.deployer_dev.email}"
}

resource "google_project_iam_member" "deployer_prod_roles" {
  provider = google.prod
  for_each = toset([
    "roles/run.admin",
    "roles/artifactregistry.writer",
    "roles/iam.serviceAccountUser",
    "roles/secretmanager.secretAccessor",
  ])

  project = var.prod_project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer_prod.email}"
}

resource "google_storage_bucket_iam_member" "deployer_prod_bucket_object_admin" {
  provider = google.prod
  for_each = var.deployer_prod_storage_object_admin_buckets

  bucket = each.value
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.deployer_prod.email}"
}

resource "google_secret_manager_secret" "databricks_token_dev" {
  secret_id = var.databricks_token_secret_name_dev
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "databricks_token_prod" {
  provider  = google.prod
  secret_id = var.databricks_token_secret_name_prod
  replication {
    auto {}
  }
}
