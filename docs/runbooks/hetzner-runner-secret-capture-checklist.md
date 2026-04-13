# Hetzner Runner Secret Capture Checklist

Owner: Platform / Infra  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: old Hetzner NixOS GitHub Actions runner path in `infra/nix/hetzner-runner/`

## Purpose

Use this checklist before wiping or reimaging the legacy Hetzner runner host. It preserves the
secret material, encrypted source files, and runtime state that still matter for migration, audit,
or rollback.

Run the capture commands from `nix develop` or the repo shell so `age-keygen`, `sops`, and
`ssh-to-age` are available.

This checklist is the operator companion to
[Hetzner runner secret capture](hetzner-runner-secret-capture.md) and the
[ARC runner migration matrix](../migration/arc-runner-migration-matrix.md).

## Source Of Truth

- [infra/nix/hetzner-runner/configuration.nix](../../infra/nix/hetzner-runner/configuration.nix)
- [infra/nix/hetzner-runner/disko-config.nix](../../infra/nix/hetzner-runner/disko-config.nix)
- [infra/nix/hetzner-runner/secrets/README.md](../../infra/nix/hetzner-runner/secrets/README.md)
- [infra/nix/hetzner-runner/secrets/hetzner.yaml.template](../../infra/nix/hetzner-runner/secrets/hetzner.yaml.template)
- [docs/setup/scoped-credentials.md](../setup/scoped-credentials.md)
- [docs/migration/README.md](../migration/README.md)
- [docs/migration/parallel-workstreams.md](../migration/parallel-workstreams.md)
- [docs/runbooks/hetzner-runner-secret-capture.md](hetzner-runner-secret-capture.md)
- [docs/migration/arc-runner-migration-matrix.md](../migration/arc-runner-migration-matrix.md)
- [docs/adr/adr-0024-ci-runner-strategy.md](../adr/adr-0024-ci-runner-strategy.md)

## Preserve First

### 1. Capture the host age / SSH material

The runner host uses `/etc/ssh/ssh_host_ed25519_key` as the sops-nix age source
(`sops.age.sshKeyPaths` in [configuration.nix](../../infra/nix/hetzner-runner/configuration.nix)).
Preserve both the private host key and the derived public recipient before the disk is wiped.

```bash
sudo install -d -m 0700 /root/evidara-hetzner-archive
sudo cp /etc/ssh/ssh_host_ed25519_key /etc/ssh/ssh_host_ed25519_key.pub /root/evidara-hetzner-archive/
ssh-keyscan 88.99.26.120 2>/dev/null | ssh-to-age > /root/evidara-hetzner-archive/hetzner-host.age.pub
```

If the host is already gone, stop here and treat the host key as unrecoverable.

### 2. Capture the admin age identity

The repo’s sops bootstrap expects a personal age identity, usually at
`~/.config/sops/age/keys.txt` ([secrets README](../../infra/nix/hetzner-runner/secrets/README.md)).
Preserve the private identity and the public recipient used for `.sops.yaml`.

```bash
mkdir -p ~/evidara-hetzner-archive
cp ~/.config/sops/age/keys.txt ~/evidara-hetzner-archive/admin.age.keys.txt
age-keygen -y ~/.config/sops/age/keys.txt > ~/evidara-hetzner-archive/admin.age.pub
```

If your admin identity is SSH-based instead of age-native, convert the SSH key with
`ssh-to-age` from the repo shell and archive the resulting public recipient alongside it.

### 3. Preserve the encrypted secret source

The encrypted secret payload for the Hetzner host should be kept as the canonical reference.
If `infra/nix/hetzner-runner/secrets/hetzner.yaml` exists in your workspace, archive that file
without decrypting it.

```bash
if [ -f infra/nix/hetzner-runner/secrets/hetzner.yaml ]; then
  cp infra/nix/hetzner-runner/secrets/hetzner.yaml ~/evidara-hetzner-archive/
fi
```

## What To Archive Before Wiping

- `/etc/ssh/ssh_host_ed25519_key*`
- `infra/nix/hetzner-runner/secrets/hetzner.yaml` if present
- `/var/lib/github-runners`
- `/var/lib/openhands`
- `/var/lib/temporal`
- `/etc/evidara-coordinator`
- Any local `/run/secrets/*` material that was generated from sops and is still needed for audit
- Current system/service logs for the runner host

Example archive command:

```bash
sudo tar -C / -czf /root/evidara-hetzner-archive/hetzner-runner-state.tgz \
  var/lib/github-runners \
  var/lib/openhands \
  var/lib/temporal \
  etc/evidara-coordinator
```

## Exact Keys To Preserve

The legacy host secret file in [secrets/hetzner.yaml.template](../../infra/nix/hetzner-runner/secrets/hetzner.yaml.template)
defines the payloads that existed on the old runner path:

- `github_runner_token`
- `coordinator_slack_bot_token`
- `coordinator_slack_signing_secret`
- `coordinator_linear_api_key`
- `coordinator_linear_webhook_secret`
- `coordinator_github_token`
- `openhands_llm_api_key`
- `openhands_llm_model`
- `tailscale_auth_key`

## Where Each Secret Should Go

| Secret / material | Target | Notes |
| --- | --- | --- |
| `github_runner_token` | MacConfig + 1Password | Runner registration material for the replacement Actions Runner Controller path. |
| `coordinator_*` secrets | `rocky-agents` or archive-only | Move to `rocky-agents` if that repo owns the OpenHands/coordinator stack; otherwise keep only in archive until a new owner exists. |
| `openhands_llm_api_key` | `rocky-agents` or archive-only | Same split as the coordinator secrets because it is part of the agent stack, not the runner host itself. |
| `openhands_llm_model` | `rocky-agents` or archive-only | Configuration value, not a credential, but still part of the service envelope. |
| `tailscale_auth_key` | `rocky-agents` or archive-only | Only move if the replacement host stack needs the same mesh identity. |
| `/etc/ssh/ssh_host_ed25519_key*` | Archive-only | Host identity for decryption and SSH access; do not reuse in a new host. |
| `infra/nix/hetzner-runner/secrets/hetzner.yaml` | Archive-only | Keep the encrypted source as evidence and rollback reference. |

## Completion Criteria

- [ ] Host SSH private key and public recipient are archived
- [ ] Admin age identity and public recipient are archived
- [ ] Encrypted `hetzner.yaml` is archived if it exists
- [ ] `github_runner_token` and the coordinator / OpenHands secret set are classified into
      MacConfig, `rocky-agents`, or archive-only
- [ ] Runner state directories and service data are archived
- [ ] A wipe/reimage ticket can point to this checklist and the archive bundle without any missing
      secret input

## Related

- [CI Actions duration and runner tuning](./ci-actions-duration-metrics.md)
- [Git reconcile checklist](../migration/git-reconcile-checklist.md)
- [Parallel workstreams](../migration/parallel-workstreams.md)
- [Runner strategy ADR](../adr/adr-0024-ci-runner-strategy.md)
