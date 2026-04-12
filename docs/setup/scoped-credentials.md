# Scoped Credentials for Autonomous Workflows

All service tokens should follow the principle of least privilege. This document
defines the minimum required scopes for each integration used by the coordinator
and Hetzner infrastructure.

## GitHub — Fine-Grained Personal Access Token

Create at: <https://github.com/settings/tokens?type=beta>

| Setting | Value |
|---------|-------|
| **Repository access** | `philipplukas/evidara` only |
| **Contents** | Read and write (push to branches) |
| **Pull requests** | Read and write (create, merge) |
| **Checks** | Read (poll CI status) |
| **Metadata** | Read (required by all fine-grained PATs) |

Do **not** grant: Administration, Actions, Environments, Secrets, Webhooks, or
any org-level scope.

Store as: `coordinator_github_token` in sops.

## Slack — Bot Token Scopes

Create at: <https://api.slack.com/apps> → OAuth & Permissions

| Scope | Purpose |
|-------|---------|
| `chat:write` | Post approval messages |
| `commands` | Slash commands (`/evidara status`) |
| `im:write` | Direct messages for urgent gates |

Do **not** grant: `admin.*`, `channels:manage`, `users:read.email`, or any
admin scope.

**Signing secret**: Used to verify incoming interaction payloads. Found in
App Settings → Basic Information → Signing Secret.

Store as: `coordinator_slack_bot_token` and `coordinator_slack_signing_secret` in
sops.

## Linear — API Key

Create at: Settings → API → Personal API keys

| Scope | Purpose |
|-------|---------|
| Read issues | Receive webhook payloads |
| Write issues | Update status, post comments |

Prefer a **workspace-scoped** key over a personal key when Linear supports it.
The webhook secret is configured in Settings → API → Webhooks.

Store as: `coordinator_linear_api_key` and `coordinator_linear_webhook_secret` in
sops.

## Notion — Integration Token

Create at: <https://www.notion.so/my-integrations>

| Capability | Purpose |
|------------|---------|
| Read content | Sync context for approval messages |
| Insert content | Post workflow summaries |

**Important**: Only share specific pages/databases with the integration — do not
grant access to the entire workspace.

Store the token in sops (not in Cursor settings or MCP config files).

## OpenHands — LLM Provider Keys

| Provider | Key type | Notes |
|----------|----------|-------|
| Anthropic | API key (`sk-ant-...`) | Used for coding agent tasks |
| OpenAI | API key (`sk-...`) | Fallback provider |

Set per-key monthly spend limits in the provider dashboard. The coordinator's
`llm_heavy_task` gate prevents uncontrolled spend.

Store as: `openhands_llm_api_key` in sops.

## Tailscale — Auth Key

Create at: <https://login.tailscale.com/admin/settings/keys>

| Setting | Value |
|---------|-------|
| **Type** | Auth key |
| **Reusable** | Yes |
| **Ephemeral** | No (persistent node) |
| **Tags** | `tag:server` (if using ACLs) |
| **Expiry** | 90 days (rotate quarterly) |

Store as: `tailscale_auth_key` in sops.

## Rotation schedule

| Secret | Rotation | Method |
|--------|----------|--------|
| GitHub PAT | 90 days | Regenerate in GitHub, update sops |
| Slack bot token | On compromise only | Rotate in Slack app settings |
| Linear API key | 90 days | Regenerate in Linear settings |
| Tailscale auth key | 90 days | New key in Tailscale admin |
| LLM API keys | 90 days | Rotate in provider dashboard |
| LUKS passphrase | Annually | `cryptsetup luksChangeKey` |

After rotating any secret:

```bash
# Edit the encrypted file
sops infra/nix/hetzner-runner/secrets/hetzner.yaml

# Deploy to server
nixos-rebuild switch --flake .#hetzner-runner --target-host root@88.99.26.120
```
