locals {
  environment = lower(var.environment)
  base_name   = coalesce(var.service_name_override, "evidara-search-${local.environment}")
  labels = {
    environment = local.environment
    managed_by  = "terraform"
    system      = "evidara"
  }
  network_name                      = "${local.base_name}-vpc"
  subnet_name                       = "${local.base_name}-subnet"
  pods_secondary_range_name         = "${local.base_name}-pods"
  services_secondary_range_name     = "${local.base_name}-services"
  gke_cluster_name                  = "${local.base_name}-gke"
  gke_node_pool_name                = "${local.base_name}-pool"
  router_name                       = "${local.base_name}-router"
  nat_name                          = "${local.base_name}-nat"
  vpc_connector_name                = "${local.base_name}-connector"
  opensearch_release_name           = "opensearch"
  opensearch_service_name           = "${local.opensearch_release_name}-cluster-master"
  opensearch_internal_endpoint_host = try(data.kubernetes_service_v1.opensearch.status[0].load_balancer[0].ingress[0].ip, null)
}

resource "google_compute_network" "opensearch" {
  project                 = var.project_id
  name                    = local.network_name
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "opensearch" {
  project       = var.project_id
  name          = local.subnet_name
  ip_cidr_range = "10.40.0.0/20"
  network       = google_compute_network.opensearch.id
  region        = var.region

  secondary_ip_range {
    range_name    = local.pods_secondary_range_name
    ip_cidr_range = "10.44.0.0/16"
  }

  secondary_ip_range {
    range_name    = local.services_secondary_range_name
    ip_cidr_range = "10.45.0.0/20"
  }
}

resource "google_compute_router" "opensearch" {
  project = var.project_id
  name    = local.router_name
  region  = var.region
  network = google_compute_network.opensearch.id
}

resource "google_compute_router_nat" "opensearch" {
  project                            = var.project_id
  name                               = local.nat_name
  region                             = var.region
  router                             = google_compute_router.opensearch.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.opensearch.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
}

resource "google_project_service" "required" {
  for_each = toset([
    "container.googleapis.com",
    "compute.googleapis.com",
    "vpcaccess.googleapis.com",
  ])

  project = var.project_id
  service = each.value
}

resource "google_container_cluster" "opensearch" {
  project  = var.project_id
  name     = local.gke_cluster_name
  location = var.region

  network    = google_compute_network.opensearch.id
  subnetwork = google_compute_subnetwork.opensearch.name

  remove_default_node_pool = true
  initial_node_count       = 1
  node_locations           = var.node_locations

  release_channel {
    channel = var.gke_release_channel
  }

  min_master_version = var.cluster_min_master_version

  ip_allocation_policy {
    cluster_secondary_range_name  = local.pods_secondary_range_name
    services_secondary_range_name = local.services_secondary_range_name
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
  }

  depends_on = [google_project_service.required]
}

resource "google_container_node_pool" "opensearch" {
  project    = var.project_id
  name       = local.gke_node_pool_name
  cluster    = google_container_cluster.opensearch.name
  location   = var.region
  node_count = var.node_count

  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = var.node_disk_size_gb
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    labels       = local.labels
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

resource "google_vpc_access_connector" "opensearch" {
  project        = var.project_id
  name           = local.vpc_connector_name
  region         = var.region
  network        = google_compute_network.opensearch.name
  ip_cidr_range  = var.vpc_connector_cidr
  min_throughput = 200
  max_throughput = 300
}

resource "random_password" "opensearch_admin" {
  length           = 32
  special          = true
  override_special = "@#%^*-_=+"
}

resource "kubernetes_namespace_v1" "opensearch" {
  metadata {
    name = var.opensearch_namespace
    labels = {
      managed_by = "terraform"
    }
  }

  depends_on = [google_container_node_pool.opensearch]
}

resource "helm_release" "opensearch" {
  name       = local.opensearch_release_name
  repository = "https://opensearch-project.github.io/helm-charts/"
  chart      = "opensearch"
  version    = var.opensearch_chart_version
  namespace  = kubernetes_namespace_v1.opensearch.metadata[0].name
  timeout    = 1200

  values = [
    yamlencode({
      clusterName = local.base_name
      singleNode  = false
      replicas    = var.opensearch_replicas
      resources = {
        requests = {
          cpu    = "500m"
          memory = "2Gi"
        }
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }
      extraEnvs = [
        {
          name  = "OPENSEARCH_INITIAL_ADMIN_PASSWORD"
          value = random_password.opensearch_admin.result
        },
      ]
      opensearchJavaOpts = "-Xms${var.opensearch_heap_size} -Xmx${var.opensearch_heap_size}"
      persistence = {
        enabled = true
        size    = var.opensearch_persistence_size
      }
      service = {
        type = "LoadBalancer"
        annotations = {
          "cloud.google.com/load-balancer-type" = "Internal"
        }
      }
      securityConfig = {
        enabled = true
      }
    }),
  ]

  depends_on = [google_compute_router_nat.opensearch]
}

data "kubernetes_service_v1" "opensearch" {
  metadata {
    name      = local.opensearch_service_name
    namespace = var.opensearch_namespace
  }

  depends_on = [helm_release.opensearch]
}
