terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

provider "google" {
  project = var.dev_project_id
  region  = var.region
}

provider "google" {
  alias   = "prod"
  project = var.prod_project_id
  region  = var.region
}

provider "google" {
  alias   = "wif"
  project = coalesce(var.wif_project_id, var.dev_project_id)
  region  = var.region
}
