locals {
  environment_variables_flat = merge([
    for environment_name, variables in var.environment_variables : {
      for variable_name, value in variables :
      "${environment_name}:${variable_name}" => {
        environment_name = environment_name
        variable_name    = variable_name
        value            = value
      }
    }
  ]...)

  environment_secrets_flat = merge([
    for environment_name, secrets in var.environment_secrets : {
      for secret_name, secret_value in secrets :
      "${environment_name}:${secret_name}" => {
        environment_name = environment_name
        secret_name      = secret_name
        secret_value     = secret_value
      }
    }
  ]...)
}

check "environment_variable_keys_exist" {
  assert {
    condition = alltrue([
      for env_name in keys(var.environment_variables) :
      contains(var.environments, env_name)
    ])
    error_message = "All environment_variables keys must be included in environments."
  }
}

check "environment_secret_keys_exist" {
  assert {
    condition = alltrue([
      for env_name in keys(var.environment_secrets) :
      contains(var.environments, env_name)
    ])
    error_message = "All environment_secrets keys must be included in environments."
  }
}

resource "github_repository_environment" "managed" {
  for_each = var.environments

  repository  = var.repository_name
  environment = each.value
}

resource "github_actions_variable" "repository" {
  for_each = var.repository_variables

  repository    = var.repository_name
  variable_name = each.key
  value         = each.value
}

resource "github_actions_environment_variable" "environment" {
  for_each = local.environment_variables_flat

  repository    = var.repository_name
  environment   = each.value.environment_name
  variable_name = each.value.variable_name
  value         = each.value.value

  depends_on = [github_repository_environment.managed]
}

resource "github_actions_secret" "repository" {
  for_each = var.repository_secrets

  repository      = var.repository_name
  secret_name     = each.key
  plaintext_value = each.value
}

resource "github_actions_environment_secret" "environment" {
  for_each = local.environment_secrets_flat

  repository      = var.repository_name
  environment     = each.value.environment_name
  secret_name     = each.value.secret_name
  plaintext_value = each.value.secret_value

  depends_on = [github_repository_environment.managed]
}
