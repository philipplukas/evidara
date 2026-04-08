# Nix helpers (optional)

## GLSL wallpaper server (Plash on macOS)

The flake packages [andthedropout/glsl_backgrounds](https://github.com/andthedropout/glsl_backgrounds) and a small wrapper that runs `python3 -m http.server` from that tree. Use it with [Plash](https://sindresorhus.com/plash) (App Store): add a website URL such as `http://127.0.0.1:8765/sync.html` (or `random.html`).

### One-off

From a checkout of this repository:

```bash
nix run .#evidara-wallpaper-serve
```

Override port:

```bash
EVIDARA_WALLPAPER_PORT=9000 nix run .#evidara-wallpaper-serve
```

### Overlay (`pkgs.evidara-wallpaper-serve`)

```nix
nixpkgs.overlays = [ inputs.evidara.overlays.default ];
# ...
environment.systemPackages = [ pkgs.evidara-wallpaper-serve ];
```

Point `inputs.evidara` at this flake (path or Git URL).

### Home Manager

```nix
imports = [ inputs.evidara.homeManagerModules.evidara-wallpaper ];

programs.evidaraWallpaper = {
  enable = true;
  port = 8765;
  launchd = true; # macOS LaunchAgent at login; set false to run manually
};
```

Plash is not in nixpkgs; install the app separately (App Store). On nix-darwin you can also pull the cask via your usual Homebrew bridge if you use one.
