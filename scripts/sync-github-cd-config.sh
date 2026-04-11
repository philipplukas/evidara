#!/usr/bin/env bash
set -euo pipefail

# Sync GitHub CD environments/variables/secrets from gcloud/databricks context.
# - Dry-run by default
# - --apply to write
# - --interactive to select gcloud account/projects
# - --preflight to verify access only

usage() {
  cat <<'EOF'
Usage:
  scripts/sync-github-cd-config.sh [options]

Required (non-interactive mode):
  --dev-project <id>
  --prod-project <id>

Options:
  --interactive
  --preflight
  --apply
  --sync-secrets
  --repo <owner/name>
  --region <region>
  --artifact-project <id>
  --artifact-repo <name>
  --platform-control-service <name>
  --legal-search-api-service <name>
  --wif-provider <resource>
  --wif-project <id>
  --wif-pool-id <id>
  --wif-provider-id <id>
  --service-account-dev <email>
  --service-account-staging <email>
  --service-account-prod <email>
  --staging-project <id>            GCP project for GitHub environment "staging" (optional)
  --databricks-host-dev <url>
  --databricks-host-staging <url>
  --databricks-host-prod <url>
  --databricks-profile-dev <name>   (default: dev)
  --databricks-profile-staging <name> (default: staging)
  --databricks-profile-prod <name>  (default: prod)
  --databricks-token-source <mode>  (gsm|profile, default: gsm)
  --gsm-token-secret-dev <name>
  --gsm-token-secret-staging <name>
  --gsm-token-secret-prod <name>
  --sync-databricks-compute-policy-ids
                                    With --sync-secrets: set DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID per env
                                    from databricks cluster-policies list (warn if missing)
  --compute-policy-name <string>    (default: Evidara compute guardrails)
  -h, --help

Examples:
  scripts/ensure-evidara-cli-auth.sh

  scripts/sync-github-cd-config.sh --interactive --preflight --sync-secrets

  scripts/sync-github-cd-config.sh \
    --interactive \
    --staging-project evidara-staging \
    --region europe-west6 \
    --artifact-repo evidara-images \
    --platform-control-service platform-control-api \
    --legal-search-api-service legal-search-api \
    --databricks-token-source profile \
    --sync-databricks-compute-policy-ids \
    --sync-secrets \
    --apply
EOF
}

log() { echo "[$(date +'%H:%M:%S')] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "Missing required command: $cmd"
}

run_cmd() {
  if [[ "$APPLY" == "true" ]]; then
    "$@"
  else
    printf 'DRY-RUN:'
    printf ' %q' "$@"
    printf '\n'
  fi
}

require_gh_auth() {
  gh auth status >/dev/null 2>&1 || die "gh is not authenticated. Run: gh auth login"
}

confirm_yes() {
  local prompt="$1"
  local answer=""
  read -r -p "$prompt [y/N]: " answer
  [[ "$answer" == "y" || "$answer" == "Y" ]]
}

choose_from_list() {
  local prompt="$1"
  shift
  local options=("$@")
  local idx choice

  [[ ${#options[@]} -gt 0 ]] || die "No options available for selection."
  echo "$prompt" >&2
  for idx in "${!options[@]}"; do
    echo "  $((idx + 1))) ${options[$idx]}" >&2
  done

  while true; do
    read -r -p "Choose 1-${#options[@]}: " choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
      echo "${options[$((choice - 1))]}"
      return
    fi
    echo "Invalid selection." >&2
  done
}

preflight_check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  [PASS] $label"
    return 0
  fi
  echo "  [FAIL] $label"
  return 1
}

check_project_access() {
  local project_id="$1"
  gcloud projects describe "$project_id" --format='value(projectId)' >/dev/null 2>&1
}

detect_region() {
  local detected
  detected="$(gcloud config get-value run/region 2>/dev/null || true)"
  if [[ -z "$detected" || "$detected" == "(unset)" ]]; then
    detected="$(gcloud config get-value compute/region 2>/dev/null || true)"
  fi
  if [[ -n "$detected" && "$detected" != "(unset)" ]]; then
    echo "$detected"
    return
  fi
  # Fallback default for this repo; override with --region when needed.
  echo "${EVIDARA_DEFAULT_GCP_REGION:-europe-west6}"
}

detect_artifact_repo() {
  local project_id="$1"
  local region="$2"
  local repos preferred
  repos="$(gcloud artifacts repositories list --project "$project_id" --location "$region" --format='value(name.basename())' 2>/dev/null || true)"
  [[ -n "$repos" ]] || die "Unable to detect artifact repo. Provide --artifact-repo."
  preferred="$(printf '%s\n' "$repos" | awk '/evidara|image/ {print; exit}')"
  [[ -n "$preferred" ]] && echo "$preferred" || printf '%s\n' "$repos" | awk 'NR==1 {print}'
}

detect_platform_control_service() {
  local project_id="$1"
  local region="$2"
  local services preferred fallback_name
  fallback_name="${EVIDARA_DEFAULT_PLATFORM_CONTROL_SERVICE:-platform-control-api}"
  services="$(gcloud run services list --project "$project_id" --region "$region" --format='value(metadata.name)' 2>/dev/null || true)"
  if [[ -z "$services" ]]; then
    log "Cloud Run service auto-detect unavailable; using fallback '$fallback_name'."
    echo "$fallback_name"
    return
  fi
  preferred="$(printf '%s\n' "$services" | awk '/platform-control/ {print; exit}')"
  if [[ -n "$preferred" ]]; then
    printf '%s\n' "$preferred" | sed -E 's/-(dev|staging|prod)$//'
    return
  fi
  printf '%s\n' "$services" | awk 'NR==1 {print}' | sed -E 's/-(dev|staging|prod)$//'
}

detect_legal_search_api_service() {
  local project_id="$1"
  local region="$2"
  local services preferred fallback_name
  fallback_name="${EVIDARA_DEFAULT_LEGAL_SEARCH_API_SERVICE:-legal-search-api}"
  services="$(gcloud run services list --project "$project_id" --region "$region" --format='value(metadata.name)' 2>/dev/null || true)"
  if [[ -z "$services" ]]; then
    log "Cloud Run service auto-detect unavailable; using fallback '$fallback_name'."
    echo "$fallback_name"
    return
  fi
  preferred="$(printf '%s\n' "$services" | awk '/legal-search-api/ {print; exit}')"
  if [[ -n "$preferred" ]]; then
    printf '%s\n' "$preferred" | sed -E 's/-(dev|staging|prod)$//'
    return
  fi
  echo "$fallback_name"
}

detect_service_account() {
  local project_id="$1"
  local suffix="$2"
  local matches found
  matches="$(gcloud iam service-accounts list --project "$project_id" --format='value(email)' 2>/dev/null || true)"
  [[ -n "$matches" ]] || die "Unable to list service accounts in '$project_id'."
  found="$(printf '%s\n' "$matches" | awk -v sfx="$suffix" '$0 ~ ("gha-deployer-" sfx) {print; exit}')"
  [[ -n "$found" ]] || die "Could not auto-detect deployer SA for '$project_id'. Provide --service-account-$suffix."
  echo "$found"
}

detect_databricks_host_from_profile() {
  local profile_name="$1"
  local payload
  payload="$(databricks auth env --profile "$profile_name" --output json 2>/dev/null || true)"
  [[ -n "$payload" ]] || return 0
  printf '%s' "$payload" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("env",{}).get("DATABRICKS_HOST",""))'
}

get_databricks_token_from_profile() {
  local profile_name="$1"
  local payload
  payload="$(databricks auth env --profile "$profile_name" --output json 2>/dev/null || true)"
  [[ -n "$payload" ]] || die "Unable to read Databricks auth env for profile '$profile_name'."
  printf '%s' "$payload" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("env",{}).get("DATABRICKS_TOKEN",""))'
}

# Prints policy id or empty string if not found / JSON parse error.
get_cluster_policy_id_from_profile() {
  local profile_name="$1"
  local policy_name="$2"
  local json
  json="$(databricks cluster-policies list --profile "$profile_name" --output json 2>/dev/null || true)"
  [[ -n "$json" ]] || {
    echo ""
    return 0
  }
  printf '%s' "$json" | POLICY_NAME="$policy_name" python3 -c '
import json, os, sys
name = os.environ.get("POLICY_NAME", "").strip()
raw = json.load(sys.stdin)

def candidates(r):
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        for key in ("policies", "items", "cluster_policies"):
            if key in r and isinstance(r[key], list):
                return r[key]
    return []

rows = candidates(raw)
for row in rows:
    if not isinstance(row, dict):
        continue
    if row.get("name") != name:
        continue
    pid = row.get("policy_id") or row.get("id")
    if pid:
        print(pid)
        sys.exit(0)
' 2>/dev/null || true
}

upsert_gsm_secret_version() {
  local secret_name="$1"
  local project_id="$2"
  local secret_value="$3"
  if [[ "$APPLY" == "true" ]]; then
    printf '%s' "$secret_value" | CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud secrets versions add "$secret_name" --project "$project_id" --data-file=- >/dev/null
  else
    echo "DRY-RUN: gcloud secrets versions add $secret_name --project $project_id --data-file=- <hidden>"
  fi
}

detect_gsm_token_secret_name() {
  local project_id="$1"
  local env_hint="$2"
  local names preferred broad
  names="$(gcloud secrets list --project "$project_id" --format='value(name)' 2>/dev/null || true)"
  [[ -n "$names" ]] || die "Unable to list secrets in '$project_id'."
  preferred="$(printf '%s\n' "$names" | awk -v env="$env_hint" 'tolower($0) ~ /databricks/ && tolower($0) ~ /token/ && tolower($0) ~ env {print; exit}')"
  if [[ -n "$preferred" ]]; then echo "$preferred"; return; fi
  broad="$(printf '%s\n' "$names" | awk 'tolower($0) ~ /databricks/ && tolower($0) ~ /token/ {print; exit}')"
  [[ -n "$broad" ]] && echo "$broad" || die "Could not auto-detect Databricks token secret in '$project_id'."
}

detect_wif_provider() {
  local project_id="$1"
  local pool_hint="$2"
  local provider_hint="$3"
  local pools providers match first

  if [[ -n "$pool_hint" && -n "$provider_hint" ]]; then
    gcloud iam workload-identity-pools providers describe "$provider_hint" \
      --project "$project_id" --location global --workload-identity-pool "$pool_hint" \
      --format='value(name)' 2>/dev/null || true
    return
  fi

  if [[ -n "$pool_hint" ]]; then
    providers="$(gcloud iam workload-identity-pools providers list --project "$project_id" --location global --workload-identity-pool "$pool_hint" --format='value(name)' 2>/dev/null || true)"
    if [[ -n "$providers" ]]; then
      match="$(printf '%s\n' "$providers" | awk '/providers\/(evidara|github)/ {print; exit}')"
      [[ -n "$match" ]] && echo "$match" || printf '%s\n' "$providers" | awk 'NR==1 {print}'
      return
    fi
  fi

  pools="$(gcloud iam workload-identity-pools list --project "$project_id" --location global --format='value(name.basename())' 2>/dev/null || true)"
  [[ -n "$pools" ]] || die "Unable to list workload identity pools in '$project_id'."
  while IFS= read -r pool; do
    providers="$(gcloud iam workload-identity-pools providers list --project "$project_id" --location global --workload-identity-pool "$pool" --format='value(name)' 2>/dev/null || true)"
    [[ -n "$providers" ]] || continue
    match="$(printf '%s\n' "$providers" | awk '/providers\/(evidara|github)/ {print; exit}')"
    if [[ -n "$match" ]]; then echo "$match"; return; fi
    first="$(printf '%s\n' "$providers" | awk 'NR==1 {print}')"
    if [[ -n "$first" ]]; then echo "$first"; return; fi
  done <<< "$pools"
  die "Could not auto-detect WIF provider in '$project_id'."
}

get_gsm_secret() {
  local secret_name="$1"
  local project_id="$2"
  gcloud secrets versions access latest --project "$project_id" --secret "$secret_name"
}

set_repo_var() {
  local name="$1"
  local value="$2"
  run_cmd gh variable set "$name" --repo "$REPO" --body "$value"
}

set_env_secret() {
  local env_name="$1"
  local secret_name="$2"
  local secret_value="$3"
  if [[ "$APPLY" == "true" ]]; then
    printf '%s' "$secret_value" | gh secret set "$secret_name" --repo "$REPO" --env "$env_name"
  else
    echo "DRY-RUN: gh secret set $secret_name --repo $REPO --env $env_name <hidden>"
  fi
}

maybe_sync_compute_policy_id() {
  local env_name="$1"
  local profile_name="$2"
  [[ "$SYNC_COMPUTE_POLICY_IDS" == "true" ]] || return 0
  local pid
  pid="$(get_cluster_policy_id_from_profile "$profile_name" "$COMPUTE_POLICY_NAME")"
  pid="$(echo "$pid" | tr -d '[:space:]')"
  if [[ -z "$pid" ]]; then
    log "WARN: cluster policy '$COMPUTE_POLICY_NAME' not found for profile '$profile_name'; skipping DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID for $env_name"
    return 0
  fi
  log "Syncing DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID → GitHub environment '$env_name'"
  set_env_secret "$env_name" "DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID" "$pid"
}

run_preflight_checks() {
  local failures=0
  local active_account="(unset)"
  local adc_status="missing"

  active_account="$(gcloud config get-value core/account 2>/dev/null || true)"
  [[ -n "$active_account" && "$active_account" != "(unset)" ]] || active_account="(unset)"
  if gcloud auth application-default print-access-token >/dev/null 2>&1; then
    adc_status="configured"
  fi

  echo "Auth context:"
  echo "  gcloud active account: $active_account"
  echo "  gcloud ADC status:     $adc_status"
  echo "Preflight checks:"
  preflight_check "GitHub auth available" gh auth status || failures=$((failures + 1))
  preflight_check "GCP account configured" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud auth list --filter=status:ACTIVE --format='value(account)' || failures=$((failures + 1))
  preflight_check "DEV project visible ($DEV_PROJECT)" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud projects describe "$DEV_PROJECT" --format='value(projectId)' || failures=$((failures + 1))
  preflight_check "PROD project visible ($PROD_PROJECT)" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud projects describe "$PROD_PROJECT" --format='value(projectId)' || failures=$((failures + 1))
  if [[ -n "${STAGING_PROJECT:-}" ]]; then
    preflight_check "STAGING project visible ($STAGING_PROJECT)" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud projects describe "$STAGING_PROJECT" --format='value(projectId)' || failures=$((failures + 1))
  fi
  if [[ "$SYNC_SECRETS" == "true" ]]; then
    local wif_check_project="${WIF_PROJECT:-$DEV_PROJECT}"
    preflight_check "WIF pools listable ($wif_check_project)" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud iam workload-identity-pools list --project "$wif_check_project" --location global --limit=1 || failures=$((failures + 1))
    preflight_check "DEV service accounts listable" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud iam service-accounts list --project "$DEV_PROJECT" --limit=1 || failures=$((failures + 1))
    preflight_check "PROD service accounts listable" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud iam service-accounts list --project "$PROD_PROJECT" --limit=1 || failures=$((failures + 1))
    if [[ -n "${STAGING_PROJECT:-}" ]]; then
      preflight_check "STAGING service accounts listable" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud iam service-accounts list --project "$STAGING_PROJECT" --limit=1 || failures=$((failures + 1))
    fi
    preflight_check "DEV secrets listable" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud secrets list --project "$DEV_PROJECT" --limit=1 || failures=$((failures + 1))
    preflight_check "PROD secrets listable" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud secrets list --project "$PROD_PROJECT" --limit=1 || failures=$((failures + 1))
    if [[ -n "${STAGING_PROJECT:-}" ]]; then
      preflight_check "STAGING secrets listable" env CLOUDSDK_CORE_DISABLE_PROMPTS=1 gcloud secrets list --project "$STAGING_PROJECT" --limit=1 || failures=$((failures + 1))
    fi
    preflight_check "Databricks CLI available" databricks --version || failures=$((failures + 1))
    if [[ "$DATABRICKS_TOKEN_SOURCE" == "profile" || "$SYNC_COMPUTE_POLICY_IDS" == "true" ]]; then
      preflight_check "Databricks dev profile auth env readable ($DATABRICKS_PROFILE_DEV)" databricks auth env --profile "$DATABRICKS_PROFILE_DEV" --output json || failures=$((failures + 1))
      preflight_check "Databricks staging profile auth env readable ($DATABRICKS_PROFILE_STAGING)" databricks auth env --profile "$DATABRICKS_PROFILE_STAGING" --output json || failures=$((failures + 1))
      preflight_check "Databricks prod profile auth env readable ($DATABRICKS_PROFILE_PROD)" databricks auth env --profile "$DATABRICKS_PROFILE_PROD" --output json || failures=$((failures + 1))
    fi
  fi
  (( failures == 0 )) || die "Preflight failed with $failures failing checks."
  log "Preflight passed."
}

interactive_gcloud_setup() {
  local active_account selected_account selected_project
  local accounts=()
  local projects=()

  while IFS= read -r line; do
    [[ -n "$line" ]] && accounts+=("$line")
  done < <(gcloud auth list --format='value(account)' 2>/dev/null || true)
  if [[ ${#accounts[@]} -eq 0 ]]; then
    echo "No gcloud accounts found."
    if confirm_yes "Run 'gcloud auth login' now?"; then
      gcloud auth login
      while IFS= read -r line; do
        [[ -n "$line" ]] && accounts+=("$line")
      done < <(gcloud auth list --format='value(account)' 2>/dev/null || true)
    fi
  fi
  [[ ${#accounts[@]} -gt 0 ]] || die "No gcloud accounts available after login."

  active_account="$(gcloud config get-value core/account 2>/dev/null || true)"
  selected_account="$(choose_from_list "Select gcloud account (current: ${active_account:-none})" "${accounts[@]}")"
  gcloud config set account "$selected_account" >/dev/null
  log "Using gcloud account: $selected_account"

  while IFS= read -r line; do
    [[ -n "$line" ]] && projects+=("$line")
  done < <(gcloud projects list --format='value(projectId)' 2>/dev/null || true)
  [[ ${#projects[@]} -gt 0 ]] || die "No projects visible for selected account."

  if [[ -z "$DEV_PROJECT" ]] || ! check_project_access "$DEV_PROJECT"; then
    selected_project="$(choose_from_list "Select DEV project" "${projects[@]}")"
    DEV_PROJECT="$selected_project"
  fi
  if [[ -z "$PROD_PROJECT" ]] || ! check_project_access "$PROD_PROJECT"; then
    selected_project="$(choose_from_list "Select PROD project" "${projects[@]}")"
    PROD_PROJECT="$selected_project"
  fi
  if [[ -z "$STAGING_PROJECT" ]] || ! check_project_access "$STAGING_PROJECT"; then
    if confirm_yes "Also select a STAGING GCP project (GitHub environment 'staging' secrets)?"; then
      STAGING_PROJECT="$(choose_from_list "Select STAGING project" "${projects[@]}")"
    else
      STAGING_PROJECT=""
    fi
  fi
  log "Selected projects: dev=$DEV_PROJECT staging=${STAGING_PROJECT:-"(none)"} prod=$PROD_PROJECT"
}

print_plan() {
  cat <<EOF
Configuration plan:
  repo:                        $REPO
  mode:                        $([[ "$APPLY" == "true" ]] && echo "APPLY" || echo "DRY-RUN")
  sync secrets:                $SYNC_SECRETS
  dev project:                 $DEV_PROJECT
  staging project:             ${STAGING_PROJECT:-"(none — staging Databricks secrets skipped if GSM)"}
  prod project:                $PROD_PROJECT
  region:                      $REGION
  artifact project:            $ARTIFACT_PROJECT
  artifact repository:         $ARTIFACT_REPO
  platform-control service:    $PLATFORM_CONTROL_SERVICE
  legal-search-api service:    $LEGAL_SEARCH_API_SERVICE
EOF
  if [[ "$SYNC_SECRETS" == "true" ]]; then
    cat <<EOF
  wif provider:                $WIF_PROVIDER
  service account dev:         $SERVICE_ACCOUNT_DEV
  service account staging:     ${SERVICE_ACCOUNT_STAGING:-"(none)"}
  service account prod:        $SERVICE_ACCOUNT_PROD
  databricks host dev:         $DATABRICKS_HOST_DEV
  databricks host staging:     $DATABRICKS_HOST_STAGING
  databricks host prod:        $DATABRICKS_HOST_PROD
  databricks token source:     $DATABRICKS_TOKEN_SOURCE
  databricks profile dev:      $DATABRICKS_PROFILE_DEV
  databricks profile staging:  $DATABRICKS_PROFILE_STAGING
  databricks profile prod:     $DATABRICKS_PROFILE_PROD
  gsm token secret dev:        $GSM_TOKEN_SECRET_DEV
  gsm token secret staging:    $GSM_TOKEN_SECRET_STAGING
  gsm token secret prod:       $GSM_TOKEN_SECRET_PROD
  sync compute policy ids:     $SYNC_COMPUTE_POLICY_IDS
  compute policy name:         $COMPUTE_POLICY_NAME
EOF
  fi
}

APPLY="false"
SYNC_SECRETS="false"
SYNC_COMPUTE_POLICY_IDS="false"
PREFLIGHT_ONLY="false"
INTERACTIVE="false"
REPO=""
DEV_PROJECT=""
STAGING_PROJECT=""
PROD_PROJECT=""
REGION=""
ARTIFACT_PROJECT=""
ARTIFACT_REPO=""
PLATFORM_CONTROL_SERVICE=""
LEGAL_SEARCH_API_SERVICE=""
WIF_PROVIDER=""
WIF_PROJECT=""
WIF_POOL_ID=""
WIF_PROVIDER_ID=""
SERVICE_ACCOUNT_DEV=""
SERVICE_ACCOUNT_STAGING=""
SERVICE_ACCOUNT_PROD=""
DATABRICKS_HOST_DEV=""
DATABRICKS_HOST_STAGING=""
DATABRICKS_HOST_PROD=""
DATABRICKS_PROFILE_DEV="dev"
DATABRICKS_PROFILE_STAGING="staging"
DATABRICKS_PROFILE_PROD="prod"
DATABRICKS_TOKEN_SOURCE="gsm"
GSM_TOKEN_SECRET_DEV=""
GSM_TOKEN_SECRET_STAGING=""
GSM_TOKEN_SECRET_PROD=""
COMPUTE_POLICY_NAME="Evidara compute guardrails"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --interactive) INTERACTIVE="true"; shift ;;
    --dev-project) DEV_PROJECT="$2"; shift 2 ;;
    --staging-project) STAGING_PROJECT="$2"; shift 2 ;;
    --prod-project) PROD_PROJECT="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --artifact-project) ARTIFACT_PROJECT="$2"; shift 2 ;;
    --artifact-repo) ARTIFACT_REPO="$2"; shift 2 ;;
    --platform-control-service) PLATFORM_CONTROL_SERVICE="$2"; shift 2 ;;
    --legal-search-api-service) LEGAL_SEARCH_API_SERVICE="$2"; shift 2 ;;
    --wif-provider) WIF_PROVIDER="$2"; shift 2 ;;
    --wif-project) WIF_PROJECT="$2"; shift 2 ;;
    --wif-pool-id) WIF_POOL_ID="$2"; shift 2 ;;
    --wif-provider-id) WIF_PROVIDER_ID="$2"; shift 2 ;;
    --service-account-dev) SERVICE_ACCOUNT_DEV="$2"; shift 2 ;;
    --service-account-staging) SERVICE_ACCOUNT_STAGING="$2"; shift 2 ;;
    --service-account-prod) SERVICE_ACCOUNT_PROD="$2"; shift 2 ;;
    --databricks-host-dev) DATABRICKS_HOST_DEV="$2"; shift 2 ;;
    --databricks-host-staging) DATABRICKS_HOST_STAGING="$2"; shift 2 ;;
    --databricks-host-prod) DATABRICKS_HOST_PROD="$2"; shift 2 ;;
    --databricks-profile-dev) DATABRICKS_PROFILE_DEV="$2"; shift 2 ;;
    --databricks-profile-staging) DATABRICKS_PROFILE_STAGING="$2"; shift 2 ;;
    --databricks-profile-prod) DATABRICKS_PROFILE_PROD="$2"; shift 2 ;;
    --databricks-token-source) DATABRICKS_TOKEN_SOURCE="$2"; shift 2 ;;
    --gsm-token-secret-dev) GSM_TOKEN_SECRET_DEV="$2"; shift 2 ;;
    --gsm-token-secret-staging) GSM_TOKEN_SECRET_STAGING="$2"; shift 2 ;;
    --gsm-token-secret-prod) GSM_TOKEN_SECRET_PROD="$2"; shift 2 ;;
    --sync-databricks-compute-policy-ids) SYNC_COMPUTE_POLICY_IDS="true"; shift ;;
    --compute-policy-name) COMPUTE_POLICY_NAME="$2"; shift 2 ;;
    --sync-secrets) SYNC_SECRETS="true"; shift ;;
    --preflight) PREFLIGHT_ONLY="true"; shift ;;
    --apply) APPLY="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [[ "$SYNC_COMPUTE_POLICY_IDS" == "true" && "$SYNC_SECRETS" != "true" ]]; then
  die "--sync-databricks-compute-policy-ids requires --sync-secrets"
fi

require_cmd gh
require_cmd gcloud
require_cmd awk
require_gh_auth

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"
fi

if [[ "$INTERACTIVE" == "true" ]]; then
  interactive_gcloud_setup
fi

if [[ -z "$DEV_PROJECT" || -z "$PROD_PROJECT" ]]; then
  usage
  die "Both --dev-project and --prod-project are required (or use --interactive)."
fi

if [[ "$PREFLIGHT_ONLY" == "true" ]]; then
  run_preflight_checks
  exit 0
fi

[[ -n "$REGION" ]] || REGION="$(detect_region)"
[[ -n "$ARTIFACT_PROJECT" ]] || ARTIFACT_PROJECT="$DEV_PROJECT"
[[ -n "$ARTIFACT_REPO" ]] || ARTIFACT_REPO="$(detect_artifact_repo "$ARTIFACT_PROJECT" "$REGION")"
[[ -n "$PLATFORM_CONTROL_SERVICE" ]] || PLATFORM_CONTROL_SERVICE="$(detect_platform_control_service "$DEV_PROJECT" "$REGION")"
[[ -n "$LEGAL_SEARCH_API_SERVICE" ]] || LEGAL_SEARCH_API_SERVICE="$(detect_legal_search_api_service "$DEV_PROJECT" "$REGION")"

if [[ "$SYNC_SECRETS" == "true" ]]; then
  require_cmd databricks
  require_cmd python3
  [[ "$DATABRICKS_TOKEN_SOURCE" == "gsm" || "$DATABRICKS_TOKEN_SOURCE" == "profile" ]] || die "--databricks-token-source must be 'gsm' or 'profile'."
  [[ -n "$WIF_PROJECT" ]] || WIF_PROJECT="$DEV_PROJECT"
  [[ -n "$WIF_PROVIDER" ]] || WIF_PROVIDER="$(detect_wif_provider "$WIF_PROJECT" "$WIF_POOL_ID" "$WIF_PROVIDER_ID")"
  [[ -n "$SERVICE_ACCOUNT_DEV" ]] || SERVICE_ACCOUNT_DEV="$(detect_service_account "$DEV_PROJECT" "dev")"
  [[ -n "$SERVICE_ACCOUNT_PROD" ]] || SERVICE_ACCOUNT_PROD="$(detect_service_account "$PROD_PROJECT" "prod")"
  if [[ -n "$STAGING_PROJECT" ]]; then
    [[ -n "$SERVICE_ACCOUNT_STAGING" ]] || SERVICE_ACCOUNT_STAGING="$(detect_service_account "$STAGING_PROJECT" "staging")"
  fi
  [[ -n "$DATABRICKS_HOST_DEV" ]] || DATABRICKS_HOST_DEV="$(detect_databricks_host_from_profile "$DATABRICKS_PROFILE_DEV")"
  [[ -n "$DATABRICKS_HOST_STAGING" ]] || DATABRICKS_HOST_STAGING="$(detect_databricks_host_from_profile "$DATABRICKS_PROFILE_STAGING")"
  [[ -n "$DATABRICKS_HOST_PROD" ]] || DATABRICKS_HOST_PROD="$(detect_databricks_host_from_profile "$DATABRICKS_PROFILE_PROD")"
  if [[ "$DATABRICKS_TOKEN_SOURCE" == "gsm" || -n "$GSM_TOKEN_SECRET_DEV" || -n "$GSM_TOKEN_SECRET_PROD" ]]; then
    [[ -n "$GSM_TOKEN_SECRET_DEV" ]] || GSM_TOKEN_SECRET_DEV="$(detect_gsm_token_secret_name "$DEV_PROJECT" "dev")"
    [[ -n "$GSM_TOKEN_SECRET_PROD" ]] || GSM_TOKEN_SECRET_PROD="$(detect_gsm_token_secret_name "$PROD_PROJECT" "prod")"
    if [[ -n "$STAGING_PROJECT" ]]; then
      [[ -n "$GSM_TOKEN_SECRET_STAGING" ]] || GSM_TOKEN_SECRET_STAGING="$(detect_gsm_token_secret_name "$STAGING_PROJECT" "staging")"
    fi
  fi
fi

print_plan

log "Ensuring GitHub environments exist"
run_cmd gh api --silent --method PUT "repos/$REPO/environments/dev"
run_cmd gh api --silent --method PUT "repos/$REPO/environments/staging"
run_cmd gh api --silent --method PUT "repos/$REPO/environments/prod"

log "Syncing repository variables"
set_repo_var "GCP_REGION" "$REGION"
set_repo_var "GCP_PROJECT_ID_DEV" "$DEV_PROJECT"
if [[ -n "$STAGING_PROJECT" ]]; then
  set_repo_var "GCP_PROJECT_ID_STAGING" "$STAGING_PROJECT"
fi
set_repo_var "GCP_PROJECT_ID_PROD" "$PROD_PROJECT"
set_repo_var "GCP_ARTIFACT_PROJECT_ID" "$ARTIFACT_PROJECT"
set_repo_var "ARTIFACT_REGISTRY_REPOSITORY" "$ARTIFACT_REPO"
set_repo_var "PLATFORM_CONTROL_SERVICE_NAME" "$PLATFORM_CONTROL_SERVICE"
set_repo_var "LEGAL_SEARCH_API_SERVICE_NAME" "$LEGAL_SEARCH_API_SERVICE"

if [[ "$SYNC_SECRETS" == "true" ]]; then
  DATABRICKS_TOKEN_STAGING=""

  if [[ "$DATABRICKS_TOKEN_SOURCE" == "profile" ]]; then
    log "Reading Databricks tokens from CLI profiles"
    DATABRICKS_TOKEN_DEV="$(get_databricks_token_from_profile "$DATABRICKS_PROFILE_DEV")"
    DATABRICKS_TOKEN_STAGING="$(get_databricks_token_from_profile "$DATABRICKS_PROFILE_STAGING")"
    DATABRICKS_TOKEN_PROD="$(get_databricks_token_from_profile "$DATABRICKS_PROFILE_PROD")"
    [[ -n "$DATABRICKS_TOKEN_DEV" ]] || die "Databricks token is empty for profile '$DATABRICKS_PROFILE_DEV'."
    [[ -n "$DATABRICKS_TOKEN_STAGING" ]] || die "Databricks token is empty for profile '$DATABRICKS_PROFILE_STAGING'."
    [[ -n "$DATABRICKS_TOKEN_PROD" ]] || die "Databricks token is empty for profile '$DATABRICKS_PROFILE_PROD'."

    if [[ -n "$GSM_TOKEN_SECRET_DEV" && -n "$GSM_TOKEN_SECRET_PROD" ]]; then
      log "Rotating Databricks tokens in Secret Manager from CLI profiles"
      upsert_gsm_secret_version "$GSM_TOKEN_SECRET_DEV" "$DEV_PROJECT" "$DATABRICKS_TOKEN_DEV"
      upsert_gsm_secret_version "$GSM_TOKEN_SECRET_PROD" "$PROD_PROJECT" "$DATABRICKS_TOKEN_PROD"
      if [[ -n "$STAGING_PROJECT" && -n "$GSM_TOKEN_SECRET_STAGING" ]]; then
        upsert_gsm_secret_version "$GSM_TOKEN_SECRET_STAGING" "$STAGING_PROJECT" "$DATABRICKS_TOKEN_STAGING"
      fi
    fi
  else
    log "Reading Databricks tokens from Secret Manager"
    DATABRICKS_TOKEN_DEV="$(get_gsm_secret "$GSM_TOKEN_SECRET_DEV" "$DEV_PROJECT")"
    DATABRICKS_TOKEN_PROD="$(get_gsm_secret "$GSM_TOKEN_SECRET_PROD" "$PROD_PROJECT")"
    if [[ -n "$STAGING_PROJECT" ]]; then
      DATABRICKS_TOKEN_STAGING="$(get_gsm_secret "$GSM_TOKEN_SECRET_STAGING" "$STAGING_PROJECT")"
    else
      log "Note: no --staging-project; skipping staging DATABRICKS_* from GSM (use --databricks-token-source profile to sync staging without a staging GCP project)."
    fi
  fi

  log "Syncing dev environment secrets"
  set_env_secret "dev" "GCP_WORKLOAD_IDENTITY_PROVIDER" "$WIF_PROVIDER"
  set_env_secret "dev" "GCP_SERVICE_ACCOUNT_DEV" "$SERVICE_ACCOUNT_DEV"
  set_env_secret "dev" "DATABRICKS_HOST" "$DATABRICKS_HOST_DEV"
  set_env_secret "dev" "DATABRICKS_TOKEN" "$DATABRICKS_TOKEN_DEV"
  maybe_sync_compute_policy_id "dev" "$DATABRICKS_PROFILE_DEV"

  if [[ -n "$STAGING_PROJECT" ]]; then
    log "Syncing staging environment secrets"
    set_env_secret "staging" "GCP_WORKLOAD_IDENTITY_PROVIDER" "$WIF_PROVIDER"
    set_env_secret "staging" "GCP_SERVICE_ACCOUNT_STAGING" "$SERVICE_ACCOUNT_STAGING"
  else
    log "Skipping staging GCP secrets (no --staging-project)."
  fi
  if [[ -n "$DATABRICKS_TOKEN_STAGING" && -n "$DATABRICKS_HOST_STAGING" ]]; then
    log "Syncing staging Databricks secrets"
    set_env_secret "staging" "DATABRICKS_HOST" "$DATABRICKS_HOST_STAGING"
    set_env_secret "staging" "DATABRICKS_TOKEN" "$DATABRICKS_TOKEN_STAGING"
    maybe_sync_compute_policy_id "staging" "$DATABRICKS_PROFILE_STAGING"
  elif [[ "$DATABRICKS_TOKEN_SOURCE" == "gsm" ]]; then
    log "WARN: staging DATABRICKS_HOST/TOKEN not written (need --staging-project for GSM or use profile token source)."
  fi

  log "Syncing prod environment secrets"
  set_env_secret "prod" "GCP_WORKLOAD_IDENTITY_PROVIDER" "$WIF_PROVIDER"
  set_env_secret "prod" "GCP_SERVICE_ACCOUNT_PROD" "$SERVICE_ACCOUNT_PROD"
  set_env_secret "prod" "DATABRICKS_HOST" "$DATABRICKS_HOST_PROD"
  set_env_secret "prod" "DATABRICKS_TOKEN" "$DATABRICKS_TOKEN_PROD"
  maybe_sync_compute_policy_id "prod" "$DATABRICKS_PROFILE_PROD"
fi

log "Done."
