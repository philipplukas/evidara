variable "github_owner" {
  description = "GitHub organization or user that owns the repository."
  type        = string
}

variable "repository_name" {
  description = "Repository name to manage."
  type        = string
}

variable "environments" {
  description = "Environment names to manage in the GitHub repository."
  type        = set(string)
  default     = ["dev", "prod"]

  validation {
    condition = alltrue([
      for env in var.environments :
      contains(["dev", "staging", "prod"], lower(env))
    ])
    error_message = "environments may only contain dev, staging, and prod."
  }
}

variable "repository_variables" {
  description = "Repository-level GitHub Actions variables."
  type        = map(string)
  default     = {}
}

variable "environment_variables" {
  description = "Environment-level GitHub Actions variables keyed by environment name."
  type        = map(map(string))
  default     = {}
}

variable "repository_secrets" {
  description = "Repository-level GitHub Actions secrets."
  type        = map(string)
  default     = {}
}

variable "environment_secrets" {
  description = "Environment-level GitHub Actions secrets keyed by environment name."
  type        = map(map(string))
  default     = {}
}
