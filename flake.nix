{
  description = "Evidara monorepo — dev shell (Terraform, gcloud, jq, …) and Nix helpers for the GLSL wallpaper server";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
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
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              terraform
              jq
              shellcheck
              uv
              google-cloud-sdk
            ];
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
    };
}
