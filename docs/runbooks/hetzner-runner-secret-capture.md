# Hetzner Runner Secret Capture

Owner: Platform / Infra  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: old Hetzner NixOS GitHub Actions runner path and pre-rebuild secret preservation

> **Superseded — historical record.** The rebuild this runbook precedes has already happened: the
> dedicated server now runs the single-node k3s cluster (ADR-0029), and the `infra/nix/` tree,
> `flake.nix`, and `.sops.yaml` referenced below have been removed from the repo. Paths named here
> resolve only in git history prior to the Nix removal. Kept as migration and audit evidence —
> **do not execute**. Runners now run on ARC; see [infra/hetzner/README.md](../../infra/hetzner/README.md).

This runbook preserves the old Hetzner runner host source of truth before the
dedicated server is rebuilt into the single-node k3s platform.

Use this before any destructive install.

Related docs:

- [Migration README](../migration/README.md)
- [ARC runner migration matrix](../migration/arc-runner-migration-matrix.md)
- [Hetzner runner secret capture checklist](hetzner-runner-secret-capture-checklist.md)

## Why This Exists

The old Hetzner host carries more than GitHub runner registration:

- SOPS key routing in `.sops.yaml`
- host secret wiring in `infra/nix/hetzner-runner/configuration.nix`
- the expected secret inventory in `infra/nix/hetzner-runner/secrets/hetzner.yaml.template`
- the old deploy path captured through operator shell history and the host NixOS
  configuration in `infra/nix/hetzner-runner/configuration.nix`

Important: the repo does not contain a tracked
`infra/nix/hetzner-runner/secrets/hetzner.yaml`, only the template and README.
If the real encrypted payload exists only locally, it must be captured before the
machine is wiped.

## Inputs To Preserve

### SOPS identities

Capture the host SSH age material:

```bash
ssh root@88.99.26.120 'cat /etc/ssh/ssh_host_ed25519_key.pub' | ssh-to-age
```

Capture your admin age public key:

```bash
age-keygen -y ~/.config/sops/age/keys.txt
```

These should match the intent described in `.sops.yaml`
and `infra/nix/hetzner-runner/secrets/README.md`.

### Secret keys

Inventory every key modeled by the old host:

- `github_runner_token`
- `coordinator_slack_bot_token`
- `coordinator_slack_signing_secret`
- `coordinator_linear_api_key`
- `coordinator_linear_webhook_secret`
- `coordinator_github_token`
- `openhands_llm_api_key`
- `openhands_llm_model`
- `tailscale_auth_key`

Source references:

- `infra/nix/hetzner-runner/secrets/hetzner.yaml.template`
- `infra/nix/hetzner-runner/configuration.nix`

## Preserve / Move / Archive

### Move To MacConfig / 1Password

- GitHub App credentials for the new ARC runner pools
- single-node k3s admin kubeconfig after rebuild
- new LUKS passphrases for the rebuilt host

Note: `github_runner_token` is legacy host-runner auth and should not be the new
steady-state credential.

### Move To `rocky-agents`

- `coordinator_slack_bot_token`
- `coordinator_slack_signing_secret`
- `coordinator_linear_api_key`
- `coordinator_linear_webhook_secret`
- `coordinator_github_token`
- `openhands_llm_api_key`
- `openhands_llm_model`

These correspond to the old sidecar/runtime concerns that are moving off the
Hetzner runner host.

### Archive Or Retire

- `github_runner_token`
  Keep only as rollback reference while the old host-runner path still exists.
- `tailscale_auth_key`
  Retire from the dedicated runner host unless a separate admin path still needs
  it later.

## Capture Checklist

1. Confirm whether a real local
   `infra/nix/hetzner-runner/secrets/hetzner.yaml` exists anywhere outside git.
2. If it exists, copy it to a safe archive location outside the repo.
3. If it does not exist, recover or recreate the encrypted payload with `sops`
   before the rebuild.
4. Record the SOPS identities used by the old path.
5. Archive the old deploy path:
   shell history, deployment notes, and the host wiring in
   `infra/nix/hetzner-runner/configuration.nix`
6. Archive the sidecar runtime config that `rocky-agents` needs:
   - [`infra/coordinator/compose.yml`](../../infra/coordinator/compose.yml)
   - [`infra/coordinator/README.md`](../../infra/coordinator/README.md)
   - env assembly in `infra/nix/hetzner-runner/configuration.nix`
7. Record the old recovery path:
   initrd SSH on `2222` plus `systemd-tty-ask-password-agent`, as described in
   `infra/nix/hetzner-runner/disko-config.nix`

## Done Criteria

This lane is done when:

- the real old secret payload is located and preserved
- every key is classified as `move`, `archive`, or `retire`
- the old deploy script and sidecar config are archived for rollback/reference
- the destructive rebuild no longer depends on rediscovering local-only secret state
