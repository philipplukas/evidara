variable "catalog_name" {
  description = "Unity Catalog catalog for document-intelligence published surfaces."
  type        = string
  default     = "document_intelligence"
}

variable "schema_name" {
  description = "Unity Catalog schema for published surfaces."
  type        = string
  default     = "published"
}

variable "schema_comment" {
  description = "Optional schema description."
  type        = string
  default     = "Published canonical surfaces for Evidara document-intelligence."
}

variable "external_location_name" {
  description = "Unity Catalog external location name for the published surfaces root."
  type        = string
  default     = "document_intelligence_surfaces"
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
