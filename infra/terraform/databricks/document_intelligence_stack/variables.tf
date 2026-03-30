variable "environment" {
  description = "Target Evidara environment."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], lower(var.environment))
    error_message = "environment must be one of dev, staging, or prod."
  }
}

variable "workspace_host" {
  description = "Databricks workspace host URL."
  type        = string
}

variable "catalog_name" {
  description = "Optional Unity Catalog catalog override. Defaults to an environment-specific Evidara catalog name."
  type        = string
  default     = null
  nullable    = true
}

variable "schema_name" {
  description = "Optional schema override. Defaults to published."
  type        = string
  default     = null
  nullable    = true
}

variable "schema_comment" {
  description = "Optional schema description override."
  type        = string
  default     = null
  nullable    = true
}

variable "external_location_name" {
  description = "Optional external location name override. Defaults to an environment-specific Evidara name."
  type        = string
  default     = null
  nullable    = true
}

variable "external_location_url" {
  description = "External location URL backing the published surfaces root, for example gs://bucket/path."
  type        = string
}

variable "storage_credential_name" {
  description = "Existing Unity Catalog storage credential used by the external location."
  type        = string
}

variable "create_external_location" {
  description = "Whether Terraform should create the external location object."
  type        = bool
  default     = true
}

variable "catalog_grants" {
  description = "Principals and privileges to grant on the catalog."
  type = list(object({
    principal  = string
    privileges = list(string)
  }))
  default = []
}

variable "schema_grants" {
  description = "Principals and privileges to grant on the schema."
  type = list(object({
    principal  = string
    privileges = list(string)
  }))
  default = []
}

variable "external_location_grants" {
  description = "Principals and privileges to grant on the external location."
  type = list(object({
    principal  = string
    privileges = list(string)
  }))
  default = []
}
