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
