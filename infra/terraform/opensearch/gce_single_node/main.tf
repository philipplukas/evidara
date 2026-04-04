locals {
  environment = lower(var.environment)
  base_name   = coalesce(var.service_name_override, "evidara-opensearch-${local.environment}")
  labels = {
    environment = local.environment
    managed_by  = "terraform"
    system      = "evidara"
    component   = "opensearch"
  }
}

# ---------- Persistent disk for OpenSearch data ----------

resource "google_compute_disk" "opensearch_data" {
  project = var.project_id
  name    = "${local.base_name}-data"
  zone    = var.zone
  type    = "pd-balanced"
  size    = var.disk_size_gb
  labels  = local.labels
}

# ---------- GCE instance (Container-Optimized OS) ----------

resource "google_compute_instance" "opensearch" {
  project      = var.project_id
  name         = local.base_name
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["${local.base_name}-allow-os"]

  labels = local.labels

  boot_disk {
    initialize_params {
      image = "projects/cos-cloud/global/images/family/cos-stable"
      size  = 20
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.opensearch_data.self_link
    device_name = "opensearch-data"
    mode        = "READ_WRITE"
  }

  network_interface {
    network    = var.network
    subnetwork = var.subnetwork
    # Internal-only: no access_config block → no external IP
  }

  metadata = {
    # COS uses cloud-init / startup scripts to run containers.
    # We use a startup script instead of the container declaration
    # metadata because we need to set sysctl and mount the data disk
    # before launching the container.
    startup-script = <<-SCRIPT
      #!/bin/bash
      set -euo pipefail

      # OpenSearch requires vm.max_map_count >= 262144
      sysctl -w vm.max_map_count=262144
      echo "vm.max_map_count=262144" >> /etc/sysctl.conf

      # Mount the persistent data disk
      DATA_DEVICE="/dev/disk/by-id/google-opensearch-data"
      DATA_DIR="/mnt/disks/opensearch-data"
      mkdir -p "$DATA_DIR"

      # Format only if not already formatted
      if ! blkid "$DATA_DEVICE" &>/dev/null; then
        mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0 "$DATA_DEVICE"
      fi

      mount -o discard,defaults "$DATA_DEVICE" "$DATA_DIR"
      chmod 777 "$DATA_DIR"

      # Run OpenSearch via Docker (COS ships with Docker pre-installed)
      docker rm -f opensearch 2>/dev/null || true

      docker run -d \
        --name opensearch \
        --restart always \
        --ulimit memlock=-1:-1 \
        --ulimit nofile=65536:65536 \
        -e "discovery.type=single-node" \
        -e "OPENSEARCH_JAVA_OPTS=-Xms${var.opensearch_heap_size} -Xmx${var.opensearch_heap_size}" \
        -e "plugins.security.disabled=true" \
        -e "OPENSEARCH_INITIAL_ADMIN_PASSWORD=admin" \
        -v "$DATA_DIR:/usr/share/opensearch/data" \
        -p 9200:9200 \
        opensearchproject/opensearch:${var.opensearch_version}
    SCRIPT
  }

  service_account {
    scopes = ["cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  allow_stopping_for_update = true

  lifecycle {
    ignore_changes = [
      # COS auto-updates the image; don't force re-creation.
      boot_disk[0].initialize_params[0].image,
    ]
  }
}

# ---------- Firewall: allow port 9200 from internal ranges ----------

resource "google_compute_firewall" "opensearch_allow" {
  project = var.project_id
  name    = "${local.base_name}-allow-9200"
  network = var.network

  allow {
    protocol = "tcp"
    ports    = ["9200"]
  }

  source_ranges = var.allowed_source_ranges
  target_tags   = ["${local.base_name}-allow-os"]

  description = "Allow OpenSearch traffic from Cloud Run VPC connector and admin ranges."
}
