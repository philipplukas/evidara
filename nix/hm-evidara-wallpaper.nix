{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.programs.evidaraWallpaper;
  evidara-wallpaper-serve = pkgs.callPackage ./wallpaper-serve.nix { };
in
{
  options.programs.evidaraWallpaper = {
    enable = lib.mkEnableOption ''
      Evidara GLSL wallpaper HTTP server (macOS: pair with Plash → http://127.0.0.1:<port>/sync.html)
    '';

    port = lib.mkOption {
      type = lib.types.port;
      default = 8765;
      description = "TCP port for python3 -m http.server.";
    };

    launchd = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Run the server as a LaunchAgent at login (macOS only). Disable if you prefer
        `nix run` / manual start.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ evidara-wallpaper-serve ];

    launchd.agents.evidara-wallpaper-serve = lib.mkIf (pkgs.stdenv.isDarwin && cfg.launchd) {
      enable = true;
      config = {
        ProgramArguments = [ (lib.getExe evidara-wallpaper-serve) ];
        EnvironmentVariables = {
          EVIDARA_WALLPAPER_PORT = toString cfg.port;
        };
        RunAtLoad = true;
        KeepAlive = true;
        StandardOutPath = "${config.home.homeDirectory}/Library/Logs/evidara-wallpaper-serve.stdout.log";
        StandardErrorPath = "${config.home.homeDirectory}/Library/Logs/evidara-wallpaper-serve.stderr.log";
      };
    };
  };
}
