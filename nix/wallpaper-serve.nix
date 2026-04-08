{
  lib,
  fetchFromGitHub,
  python3,
  writeShellApplication,
}:

let
  glslSrc = fetchFromGitHub {
    owner = "andthedropout";
    repo = "glsl_backgrounds";
    rev = "8e9f4bbf3ff2b0a0d0c56a09bfa7a389e6995058";
    sha256 = "0myh5cpddkpnd86lpampv1gh44vcfxwgc65781wfgih8z6z00shy";
  };
in
writeShellApplication {
  name = "evidara-wallpaper-serve";
  meta = with lib; {
    description = "Serve GLSL wallpaper pack over HTTP for Plash (or any browser)";
    homepage = "https://github.com/andthedropout/glsl_backgrounds";
    license = licenses.mit;
    platforms = platforms.all;
  };
  text = ''
    set -euo pipefail
    PORT="''${EVIDARA_WALLPAPER_PORT:-8765}"
    cd ${glslSrc}
    exec ${python3}/bin/python3 -m http.server "$PORT"
  '';
}
