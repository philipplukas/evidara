# Nix development shell

This repo provides a **flake dev shell** so common CLI tools are available even when they are missing from the host OS (CI sandboxes, minimal laptops, or agents without Homebrew).

## Prerequisites

- [Nix](https://nixos.org/download/) with **flakes** enabled (`experimental-features = nix-command flakes` in `~/.config/nix/nix.conf`, or use the Determinate Nix installer).

## Enter the shell

From the repository root:

```bash
nix develop
```

You get an interactive subshell with the packages listed in `flake.nix` under `devShells.default`.

One-off command without entering a shell:

```bash
nix develop -c terraform version
nix develop -c gcloud version
```

## direnv (optional)

If you use [direnv](https://direnv.net/), add a repo-root `.envrc` containing `use flake` (this file is **gitignored** so each machine can opt in). Run `direnv allow` once in this directory; then your shell picks up the same tools when you `cd` into the repo.

## What is in the shell today

Declared in [`flake.nix`](../../flake.nix) (adjust there when something is still missing):

| Tool | Role |
|------|------|
| `terraform` | `infra/terraform/gcp/runtime_stack` and other stacks |
| `google-cloud-sdk` | `gcloud` for Cloud Run, Pub/Sub, IAM, etc. |
| `jq` | JSON in shell scripts and smoke tests |
| `shellcheck` | Lint shell scripts under `scripts/` |
| `uv` | Python workflows in `platform-control/`, `document-intelligence/`, and tools (see `AGENTS.md`) |

**Not** pinned in Nix (use the stack’s own tooling):

- **Node / npm** — `legal-search/` (`npm install`, `npm run check`)
- **Rust, Docker, etc.** — install separately or extend the flake if the team standardizes on Nix for them

## Adding a missing tool

1. Find the attribute in [NixOS Search](https://search.nixos.org/packages) (channel aligned with `nixos-unstable` is closest to this flake’s input).
2. Add it to the `packages = with pkgs; [ ... ];` list inside `devShells.default` in `flake.nix`.
3. Run `nix flake check` or `nix develop -c <new-tool> --version` to verify.
4. Update the table above in this doc.

Keep the shell lean: prefer **small CLI utilities** in Nix; keep **language ecosystems** on `uv` / `npm` unless there is a strong reason to duplicate them.

## Other flake outputs

The same `flake.nix` still defines **wallpaper** packages and Home Manager modules (`packages.evidara-wallpaper-serve`, etc.). Those are unrelated to the dev shell; see comments in `flake.nix` and `nix/wallpaper-serve.nix`.

## Related docs

- [Infrastructure overview](infrastructure-overview.md) — Terraform layout
- [GCP local Cloud Run auth](gcp-local-cloud-run-auth.md) — identity tokens alongside `gcloud`
- [AGENTS.md](../../AGENTS.md) — language-specific tools (`uv`, `npm`, `ruff`, …)
