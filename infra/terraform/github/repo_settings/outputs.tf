output "environments" {
  value = {
    for env_name, env in github_repository_environment.managed :
    env_name => env.environment
  }
}

output "repository_variable_names" {
  value = sort(keys(github_actions_variable.repository))
}

output "environment_variable_names" {
  value = {
    for env_name in var.environments :
    env_name => sort([
      for key, value in local.environment_variables_flat :
      value.variable_name if value.environment_name == env_name
    ])
  }
}

output "repository_secret_names" {
  value = sort(keys(github_actions_secret.repository))
}

output "environment_secret_names" {
  value = {
    for env_name in var.environments :
    env_name => sort([
      for key, value in local.environment_secrets_flat :
      value.secret_name if value.environment_name == env_name
    ])
  }
}
