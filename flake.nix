{
  description = "Evidara monorepo — dev shell (Terraform, gcloud, jq, …) and Nix helpers for the GLSL wallpaper server";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      disko,
      sops-nix,
    }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (
        system:
        let
          # Several CLIs in this shell are marked unfree in current nixpkgs (Terraform BSL,
          # Databricks license, 1Password). Restrict unfree allowance to this devShell import only.
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              terraform
              jq
              shellcheck
              uv
              google-cloud-sdk
              sshpass
              _1password-cli
              gh
              databricks-cli
              sops
              age
              ssh-to-age
            ];

            shellHook = ''
              # ── 1Password SSH agent (macOS) ──
              if [[ "$(uname)" == "Darwin" ]]; then
                _op_sock="$HOME/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"
                if [[ -S "$_op_sock" ]]; then
                  export SSH_AUTH_SOCK="$_op_sock"
                fi
                unset _op_sock
              fi

              # ── 1Password shell-plugin aliases (idempotent) ──
              if [[ -z "''${OP_PLUGIN_ALIASES_SOURCED:-}" ]] && command -v op &>/dev/null; then
                alias gh="op plugin run -- gh"   2>/dev/null || true
                alias gcloud="op plugin run -- gcloud" 2>/dev/null || true
                export OP_PLUGIN_ALIASES_SOURCED=1
              fi

              # ── Hint: one-time plugin init (safe to re-run) ──
              if command -v op &>/dev/null; then
                _uninit=""
                for _plug in gh gcloud; do
                  if ! op plugin list 2>/dev/null | grep -q "$_plug"; then
                    _uninit="$_uninit $_plug"
                  fi
                done
                if [[ -n "$_uninit" ]]; then
                  echo "💡 1Password plugins not yet initialised:$_uninit"
                  echo "   Run:  op plugin init <name>  (one-time, interactive)"
                fi
                unset _uninit _plug
              fi
            '';
          };
        }
      );

      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.callPackage ./nix/wallpaper-serve.nix { };
          evidara-wallpaper-serve = pkgs.callPackage ./nix/wallpaper-serve.nix { };
        }
      );

      apps = forAllSystems (
        system:
        let
          pkg = self.packages.${system}.default;
        in
        {
          default = {
            type = "app";
            program = "${pkg}/bin/evidara-wallpaper-serve";
          };
          evidara-wallpaper-serve = {
            type = "app";
            program = "${pkg}/bin/evidara-wallpaper-serve";
          };
        }
      );

      overlays.default = final: prev: {
        evidara-wallpaper-serve = final.callPackage ./nix/wallpaper-serve.nix { };
      };

      homeManagerModules.evidara-wallpaper = ./nix/hm-evidara-wallpaper.nix;

      nixosConfigurations.hetzner-runner = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = [
          disko.nixosModules.disko
          sops-nix.nixosModules.sops
          ./infra/nix/hetzner-runner/configuration.nix
        ];
      };
    };
}
