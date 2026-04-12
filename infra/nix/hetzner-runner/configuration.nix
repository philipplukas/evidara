{
  config,
  pkgs,
  lib,
  ...
}:
let
  runnerUrl = "https://github.com/philipplukas/evidara";
  tokenFile = "/etc/github-runner-token";

  commonRunnerPackages = with pkgs; [
    bash
    coreutils
    curl
    docker
    gawk
    gh
    git
    gnugrep
    gnused
    gnutar
    gzip
    jq
    nodejs_20
    openssh
    python3
    terraform
    unzip
    wget
    xz
    zstd
  ];

  mkRunner = name: labels: {
    enable = true;
    url = runnerUrl;
    inherit name tokenFile;
    extraLabels = labels;
    ephemeral = true;
    replace = true;
    extraPackages = commonRunnerPackages;
    workDir = "/var/lib/github-runners/${name}";
    serviceOverrides = {
      SupplementaryGroups = [ "docker" ];
    };
  };
in
{
  imports = [ ./disko-config.nix ];

  boot.loader.grub = {
    enable = true;
    devices = [
      "/dev/nvme0n1"
      "/dev/nvme1n1"
    ];
  };
  boot.initrd.availableKernelModules = [
    "ahci"
    "nvme"
    "sd_mod"
    "xhci_pci"
  ];
  boot.swraid.enable = true;

  nixpkgs.hostPlatform = "x86_64-linux";
  powerManagement.cpuFreqGovernor = "ondemand";

  networking = {
    hostName = "evidara-runner";
    useDHCP = false;
    usePredictableInterfaceNames = true;
    interfaces.enp0s31f6 = {
      ipv4.addresses = [
        {
          address = "88.99.26.120";
          prefixLength = 26;
        }
      ];
      ipv6.addresses = [
        {
          address = "2a01:4f8:10a:284::2";
          prefixLength = 64;
        }
      ];
    };
    defaultGateway = "88.99.26.65";
    defaultGateway6 = {
      address = "fe80::1";
      interface = "enp0s31f6";
    };
    nameservers = [
      "185.12.64.1"
      "185.12.64.2"
      "2a01:4ff:ff00::add:1"
    ];
    firewall = {
      enable = true;
      allowedTCPPorts = [ 22 ];
    };
  };

  time.timeZone = "UTC";

  users.users.root = {
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIClWghD3AWBGzRw86VYC8ntOXg4ol/EczMx/4l8Y1QVR"
    ];
  };

  services.openssh = {
    enable = true;
    settings = {
      PermitRootLogin = "prohibit-password";
      PasswordAuthentication = false;
    };
  };

  virtualisation.docker = {
    enable = true;
    autoPrune = {
      enable = true;
      dates = "weekly";
    };
  };

  nix = {
    settings = {
      experimental-features = [
        "nix-command"
        "flakes"
      ];
      auto-optimise-store = true;
    };
    gc = {
      automatic = true;
      dates = "weekly";
      options = "--delete-older-than 14d";
    };
  };

  services.github-runners = {
    light-1 = mkRunner "evidara-light-1" [ "light" ];
    light-2 = mkRunner "evidara-light-2" [ "light" ];
    heavy-1 = mkRunner "evidara-heavy-1" [ "heavy" ];
    heavy-2 = mkRunner "evidara-heavy-2" [ "heavy" ];
  };

  environment.systemPackages = with pkgs; [
    git
    htop
    jq
    vim
  ];

  system.stateVersion = "24.11";
}
