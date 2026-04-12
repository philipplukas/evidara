# Encrypted Secrets for Hetzner Runner

This directory contains sops-encrypted YAML files that are decrypted at NixOS
activation time into `/run/secrets/`.

## Setup (one-time)

1. **Get the server's age public key:**

   ```bash
   ssh-keyscan 88.99.26.120 2>/dev/null | ssh-to-age
   ```

   Put this in `.sops.yaml` as `&hetzner_host`.

2. **Generate your personal age key** (if you don't have one):

   ```bash
   age-keygen -o ~/.config/sops/age/keys.txt
   age-keygen -y ~/.config/sops/age/keys.txt  # prints public key
   ```

   Put the public key in `.sops.yaml` as `&admin`.

3. **Create the secrets file:**

   ```bash
   sops infra/nix/hetzner-runner/secrets/hetzner.yaml
   ```

   This opens your editor. Fill in the values from the template below.

4. **Re-encrypt after key changes:**

   ```bash
   sops updatekeys infra/nix/hetzner-runner/secrets/hetzner.yaml
   ```

## Secret keys

See `hetzner.yaml.template` for the expected keys and their descriptions.
The actual `hetzner.yaml` is encrypted and safe to commit to git.
