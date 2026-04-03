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
  topic                      = google_pubsub_topic.events[each.value.topic_name].name
  ack_deadline_seconds       = each.value.ack_deadline_seconds
  message_retention_duration = each.value.message_retention_duration
  labels                     = local.labels
}
