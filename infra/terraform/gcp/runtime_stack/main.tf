locals {
  environment          = lower(var.environment)
  raw_bucket_name      = coalesce(var.raw_artifact_bucket_name, "evidara-raw-artifacts-${local.environment}")
  manifest_bucket_name = coalesce(var.manifest_bucket_name, "evidara-manifests-${local.environment}")
  labels = {
    environment = local.environment
    managed_by  = "terraform"
    system      = "evidara"
  }

  topic_base_names = setunion(
    var.event_topic_names,
    toset([for subscription in values(var.event_subscriptions) : subscription.topic_name]),
  )

  prefixed_secret_ids = {
    for key, secret_id in var.runtime_secret_ids :
    key => "${secret_id}-${local.environment}"
  }

  prefixed_service_account_ids = {
    for key, account_id in var.runtime_service_account_ids :
    key => "${account_id}-${local.environment}"
  }

  cloud_run_services = {
    for service_name, service in var.cloud_run_services :
    service_name => merge(service, {
      prefixed_name = "${service_name}-${local.environment}"
    })
  }

  cloud_sql_instance_name = "evidara-control-${local.environment}"
}

check "subscription_topics_exist" {
  assert {
    condition = alltrue([
      for subscription in values(var.event_subscriptions) :
      contains(var.event_topic_names, subscription.topic_name)
    ])
    error_message = "Each event_subscriptions[*].topic_name must exist in event_topic_names."
  }
}

resource "google_storage_bucket" "raw_artifacts" {
  name                        = local.raw_bucket_name
  location                    = var.bucket_location
  force_destroy               = var.bucket_force_destroy
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket" "manifests" {
  name                        = local.manifest_bucket_name
  location                    = var.bucket_location
  force_destroy               = var.bucket_force_destroy
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels

  versioning {
    enabled = true
  }
}

resource "google_pubsub_topic" "events" {
  for_each = local.topic_base_names

  name   = each.value
  labels = local.labels
}

resource "google_pubsub_subscription" "events" {
  for_each = var.event_subscriptions

  name                       = each.key
  topic                      = google_pubsub_topic.events[each.value.topic_name].id
  ack_deadline_seconds       = each.value.ack_deadline_seconds
  message_retention_duration = each.value.message_retention_duration
  labels                     = local.labels

  dynamic "retry_policy" {
    for_each = each.value.retry_policy != null ? [each.value.retry_policy] : []
    content {
      minimum_backoff = retry_policy.value.minimum_backoff
      maximum_backoff = retry_policy.value.maximum_backoff
    }
  }

  dynamic "dead_letter_policy" {
    for_each = each.value.dead_letter_policy != null ? [each.value.dead_letter_policy] : []
    content {
      dead_letter_topic     = google_pubsub_topic.dead_letter[each.key].id
      max_delivery_attempts = dead_letter_policy.value.max_delivery_attempts
    }
  }
}

# --- Dead-letter queues ---

locals {
  dlq_subscriptions = {
    for name, sub in var.event_subscriptions :
    name => sub if sub.dead_letter_policy != null
  }
}

resource "google_pubsub_topic" "dead_letter" {
  for_each = local.dlq_subscriptions

  name   = "${each.key}-dlq"
  labels = local.labels
}

resource "google_pubsub_subscription" "dead_letter" {
  for_each = local.dlq_subscriptions

  name                       = "${each.key}-dlq-sub"
  topic                      = google_pubsub_topic.dead_letter[each.key].id
  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"
  labels                     = local.labels
}

# Pub/Sub service agent needs publisher access on DLQ topics to forward
# failed messages, and subscriber access on source subscriptions to modify
# ack deadlines during dead-lettering.
data "google_project" "current" {
  project_id = var.project_id
}

resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  for_each = local.dlq_subscriptions

  topic  = google_pubsub_topic.dead_letter[each.key].name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "dlq_subscriber" {
  for_each = local.dlq_subscriptions

  subscription = google_pubsub_subscription.events[each.key].name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_service_account" "runtime" {
  for_each = local.prefixed_service_account_ids

  account_id   = each.value
  display_name = "${replace(each.key, "_", " ")} ${local.environment}"
}

resource "google_project_iam_member" "runtime_pubsub_publisher" {
  for_each = google_service_account.runtime

  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "runtime_pubsub_subscriber" {
  for_each = google_service_account.runtime

  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "runtime_storage_object_admin" {
  for_each = google_service_account.runtime

  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_secret_manager_secret" "runtime" {
  for_each = local.prefixed_secret_ids

  secret_id = each.value
  replication {
    auto {}
  }

  labels = local.labels
}

resource "google_project_iam_member" "runtime_secret_accessor" {
  for_each = google_service_account.runtime

  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_sql_database_instance" "platform_control" {
  count = var.enable_cloud_sql ? 1 : 0

  name             = local.cloud_sql_instance_name
  region           = var.region
  database_version = "POSTGRES_15"

  settings {
    tier            = var.cloud_sql_tier
    disk_size       = var.cloud_sql_disk_size_gb
    disk_autoresize = true

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled = true
    }

    user_labels = local.labels
  }

  deletion_protection = true
}

resource "google_sql_database" "platform_control" {
  count = var.enable_cloud_sql ? 1 : 0

  name     = var.platform_control_database_name
  instance = google_sql_database_instance.platform_control[0].name
}

resource "random_password" "sql_user" {
  count = var.enable_cloud_sql ? 1 : 0

  length  = 32
  special = false
}

resource "google_sql_user" "platform_control" {
  count = var.enable_cloud_sql ? 1 : 0

  name     = "platform_control"
  instance = google_sql_database_instance.platform_control[0].name
  password = random_password.sql_user[0].result
}

# Write the async Postgres DSN into the existing secret so Cloud Run
# services pick it up automatically via secret_env_vars.
resource "google_secret_manager_secret_version" "platform_control_dsn" {
  count = var.enable_cloud_sql ? 1 : 0

  secret      = google_secret_manager_secret.runtime["platform_control_dsn"].id
  secret_data = "postgresql+asyncpg://platform_control:${random_password.sql_user[0].result}@/${var.platform_control_database_name}?host=/cloudsql/${google_sql_database_instance.platform_control[0].connection_name}"
}

resource "google_project_iam_member" "runtime_cloudsql_client" {
  for_each = var.enable_cloud_sql ? {
    for key, svc in local.cloud_run_services :
    svc.service_account_key => google_service_account.runtime[svc.service_account_key]
    if length(svc.cloud_sql_instances) > 0
  } : {}

  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_cloud_run_v2_service" "runtime" {
  for_each = local.cloud_run_services

  name                = each.value.prefixed_name
  location            = var.region
  ingress             = each.value.ingress
  deletion_protection = false

  template {
    service_account = google_service_account.runtime[each.value.service_account_key].email
    timeout         = "${each.value.timeout_seconds}s"

    scaling {
      min_instance_count = each.value.min_instance_count
      max_instance_count = each.value.max_instance_count
    }

    dynamic "vpc_access" {
      for_each = each.value.vpc_connector == null ? [] : [each.value.vpc_connector]
      content {
        connector = vpc_access.value
        egress    = each.value.vpc_egress
      }
    }

    containers {
      image = each.value.image

      resources {
        limits = {
          cpu    = each.value.cpu
          memory = each.value.memory
        }
      }

      ports {
        container_port = each.value.container_port
      }

      dynamic "env" {
        for_each = each.value.env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.value.secret_env_vars
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.runtime[env.value.secret_name].secret_id
              version = env.value.version
            }
          }
        }
      }

      dynamic "volume_mounts" {
        for_each = length(each.value.cloud_sql_instances) > 0 ? [1] : []
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      dynamic "startup_probe" {
        for_each = each.value.startup_probe_path != null ? [1] : []
        content {
          http_get {
            path = each.value.startup_probe_path
            port = each.value.container_port
          }
          initial_delay_seconds = 2
          period_seconds        = 3
          failure_threshold     = 3
          timeout_seconds       = 2
        }
      }

      dynamic "liveness_probe" {
        for_each = each.value.liveness_probe_path != null ? [1] : []
        content {
          http_get {
            path = each.value.liveness_probe_path
            port = each.value.container_port
          }
          period_seconds    = 15
          failure_threshold = 3
          timeout_seconds   = 2
        }
      }
    }

    dynamic "volumes" {
      for_each = length(each.value.cloud_sql_instances) > 0 ? [1] : []
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = each.value.cloud_sql_instances
        }
      }
    }
  }

  labels = local.labels

  depends_on = [
    google_project_iam_member.runtime_secret_accessor,
    google_project_iam_member.runtime_storage_object_admin,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "runtime_public_invoker" {
  for_each = {
    for name, service in local.cloud_run_services :
    name => service if service.allow_unauthenticated
  }

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.runtime[each.key].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
