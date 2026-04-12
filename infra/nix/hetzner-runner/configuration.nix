{
  config,
  pkgs,
  lib,
  ...
}:
let
  runnerUrl = "https://github.com/philipplukas/evidara";

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
    inherit name;
    tokenFile = config.sops.secrets.github_runner_token.path;
    extraLabels = labels;
    ephemeral = false;
    replace = true;
    extraPackages = commonRunnerPackages;
    serviceOverrides = {
      SupplementaryGroups = [ "docker" ];
    };
  };
in
{
  imports = [ ./disko-config.nix ];

  boot.loader.grub.enable = true;
  boot.initrd.availableKernelModules = [
    "ahci"
    "nvme"
    "sd_mod"
    "xhci_pci"
    "dm_crypt"
    "dm_mod"
    "e1000e"
    "igb"
  ];

  # ---------------------------------------------------------------------------
  # Initrd SSH — remote LUKS unlock on reboot
  # ssh -p 2222 root@88.99.26.120  (from an authorized key)
  # then:  systemd-tty-ask-password-agent
  # ---------------------------------------------------------------------------
  boot.initrd.systemd.enable = true;
  boot.initrd.network = {
    enable = true;
    ssh = {
      enable = true;
      port = 2222;
      authorizedKeys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIClWghD3AWBGzRw86VYC8ntOXg4ol/EczMx/4l8Y1QVR"
      ];
      hostKeys = [ "/etc/ssh/ssh_host_ed25519_key" ];
    };
  };

  nixpkgs.hostPlatform = "x86_64-linux";
  nixpkgs.config.allowUnfree = true;
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
      allowedUDPPorts = [ config.services.tailscale.port ];
      trustedInterfaces = [ "tailscale0" ];
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

  # ---------------------------------------------------------------------------
  # sops-nix — encrypted secrets decrypted at activation into /run/secrets/
  # ---------------------------------------------------------------------------
  sops = {
    defaultSopsFile = ./secrets/hetzner.yaml;
    age.sshKeyPaths = [ "/etc/ssh/ssh_host_ed25519_key" ];

    secrets = {
      github_runner_token = { };
      coordinator_slack_bot_token = { };
      coordinator_slack_signing_secret = { };
      coordinator_linear_api_key = { };
      coordinator_linear_webhook_secret = { };
      coordinator_github_token = { };
      openhands_llm_api_key = { };
      openhands_llm_model = { };
      tailscale_auth_key = { };

      # Composed env files for services that need EnvironmentFile
      openhands_env = {
        sopsFile = ./secrets/hetzner.yaml;
        key = "";
        format = "yaml";
        path = "/run/secrets/openhands.env";
      };
      coordinator_env = {
        sopsFile = ./secrets/hetzner.yaml;
        key = "";
        format = "yaml";
        path = "/run/secrets/coordinator.env";
      };
    };
  };

  # Generate composed env files from individual secrets via a oneshot service.
  # sops-nix decrypts individual keys; this assembles them into env files.
  systemd.services.assemble-openhands-env = {
    description = "Assemble OpenHands env file from sops secrets";
    after = [ "sops-nix.service" ];
    wantedBy = [ "openhands.service" ];
    before = [ "openhands.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      mkdir -p /run/secrets
      cat > /run/secrets/openhands.env <<ENVEOF
      LLM_API_KEY=$(cat ${config.sops.secrets.openhands_llm_api_key.path})
      LLM_MODEL=$(cat ${config.sops.secrets.openhands_llm_model.path})
      ENVEOF
      chmod 600 /run/secrets/openhands.env
    '';
  };

  systemd.services.assemble-coordinator-env = {
    description = "Assemble coordinator env file from sops secrets";
    after = [ "sops-nix.service" ];
    wantedBy = [ "evidara-coordinator.service" ];
    before = [ "evidara-coordinator.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      mkdir -p /run/secrets
      cat > /run/secrets/coordinator.env <<ENVEOF
      COORDINATOR_SLACK_BOT_TOKEN=$(cat ${config.sops.secrets.coordinator_slack_bot_token.path})
      COORDINATOR_SLACK_SIGNING_SECRET=$(cat ${config.sops.secrets.coordinator_slack_signing_secret.path})
      COORDINATOR_LINEAR_API_KEY=$(cat ${config.sops.secrets.coordinator_linear_api_key.path})
      COORDINATOR_LINEAR_WEBHOOK_SECRET=$(cat ${config.sops.secrets.coordinator_linear_webhook_secret.path})
      COORDINATOR_GITHUB_TOKEN=$(cat ${config.sops.secrets.coordinator_github_token.path})
      ENVEOF
      chmod 600 /run/secrets/coordinator.env
    '';
  };

  # ---------------------------------------------------------------------------
  # Tailscale — encrypted WireGuard mesh network
  # Access Temporal UI, OpenHands UI, coordinator via Tailscale instead of SSH tunnels.
  # ---------------------------------------------------------------------------
  services.tailscale = {
    enable = true;
    authKeyFile = config.sops.secrets.tailscale_auth_key.path;
    useRoutingFeatures = "server";
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

  # ---------------------------------------------------------------------------
  # Docker network isolation — internal network for agent containers.
  # Restricts outbound to only GitHub API and LLM endpoints.
  # ---------------------------------------------------------------------------
  systemd.services.docker-agent-network = {
    description = "Create isolated Docker network for agent containers";
    after = [ "docker.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = "${pkgs.docker}/bin/docker network create --internal evidara-agents 2>/dev/null || true";
    };
  };

  # ---------------------------------------------------------------------------
  # GitHub Actions runners — 2 light + 2 heavy
  # ---------------------------------------------------------------------------
  services.github-runners = {
    light-1 = mkRunner "evidara-light-1" [ "light" ];
    light-2 = mkRunner "evidara-light-2" [ "light" ];
    heavy-1 = mkRunner "evidara-heavy-1" [ "heavy" ];
    heavy-2 = mkRunner "evidara-heavy-2" [ "heavy" ];
  };

  # ---------------------------------------------------------------------------
  # Temporal server — durable workflow orchestration for human gates + agent
  # coordination.  gRPC on localhost:7233 (local only).
  # UI on tailscale0:8233 (private mesh) or localhost:8233 (SSH tunnel fallback).
  # ---------------------------------------------------------------------------
  systemd.services.temporal = {
    description = "Temporal server (auto-setup, SQLite)";
    after = [ "docker.service" "network-online.target" ];
    wants = [ "docker.service" "network-online.target" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "exec";
      Restart = "always";
      RestartSec = 10;
      ProtectHome = true;
      PrivateTmp = true;
      NoNewPrivileges = true;
      ExecStartPre = "-${pkgs.docker}/bin/docker rm -f temporal-server";
      ExecStart = lib.concatStringsSep " " [
        "${pkgs.docker}/bin/docker run --rm"
        "--name temporal-server"
        "--network host"
        "-v /var/lib/temporal:/var/lib/temporal"
        "-e DB=sqlite"
        "-e SQLITE_DB_PATH=/var/lib/temporal/default.db"
        "temporalio/auto-setup:latest"
      ];
      ExecStop = "${pkgs.docker}/bin/docker stop temporal-server";
    };
  };

  systemd.services.temporal-ui = {
    description = "Temporal Web UI";
    after = [ "temporal.service" ];
    wants = [ "temporal.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "exec";
      Restart = "always";
      RestartSec = 15;
      ProtectHome = true;
      PrivateTmp = true;
      NoNewPrivileges = true;
      ExecStartPre = "-${pkgs.docker}/bin/docker rm -f temporal-ui";
      ExecStart = lib.concatStringsSep " " [
        "${pkgs.docker}/bin/docker run --rm"
        "--name temporal-ui"
        "-p 127.0.0.1:8233:8233"
        "-e TEMPORAL_ADDRESS=host.docker.internal:7233"
        "-e TEMPORAL_UI_PORT=8233"
        "--add-host host.docker.internal:host-gateway"
        "temporalio/ui:latest"
      ];
      ExecStop = "${pkgs.docker}/bin/docker stop temporal-ui";
    };
  };

  # ---------------------------------------------------------------------------
  # OpenHands — autonomous coding agent platform.
  # UI on localhost:3000 (private mesh via Tailscale).
  # Secrets injected via assembled env file from sops-nix.
  # ---------------------------------------------------------------------------
  systemd.services.openhands = {
    description = "OpenHands autonomous coding agent";
    after = [ "docker.service" "network-online.target" "assemble-openhands-env.service" ];
    wants = [ "docker.service" "network-online.target" ];
    requires = [ "assemble-openhands-env.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "exec";
      Restart = "always";
      RestartSec = 10;
      ProtectHome = true;
      PrivateTmp = true;
      ExecStartPre = "-${pkgs.docker}/bin/docker rm -f openhands-app";
      ExecStart = lib.concatStringsSep " " [
        "${pkgs.docker}/bin/docker run --rm"
        "--name openhands-app"
        "--env-file /run/secrets/openhands.env"
        "-e LOG_ALL_EVENTS=true"
        "-v /var/run/docker.sock:/var/run/docker.sock"
        "-v /var/lib/openhands:/.openhands"
        "-p 127.0.0.1:3000:3000"
        "--add-host host.docker.internal:host-gateway"
        "docker.openhands.dev/openhands/openhands:latest"
      ];
      ExecStop = "${pkgs.docker}/bin/docker stop openhands-app";
    };
  };

  # ---------------------------------------------------------------------------
  # Coordinator — lightweight FastAPI service for Linear → OpenHands → Slack
  # human gates.  Secrets injected via assembled env file from sops-nix.
  # ---------------------------------------------------------------------------
  systemd.services.evidara-coordinator = {
    description = "Evidara autonomous workflow coordinator";
    after = [ "docker.service" "temporal.service" "assemble-coordinator-env.service" ];
    wants = [ "docker.service" "temporal.service" ];
    requires = [ "assemble-coordinator-env.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "exec";
      Restart = "always";
      RestartSec = 10;
      ProtectHome = true;
      PrivateTmp = true;
      NoNewPrivileges = true;
      WorkingDirectory = "/etc/evidara-coordinator";
      Environment = "COORDINATOR_ENV_FILE=/run/secrets/coordinator.env";
      ExecStart = "${pkgs.docker}/bin/docker compose -f /etc/evidara-coordinator/compose.yml up --remove-orphans";
      ExecStop = "${pkgs.docker}/bin/docker compose -f /etc/evidara-coordinator/compose.yml down";
    };
  };

  # Persistent data directories
  systemd.tmpfiles.rules = [
    "d /var/lib/temporal 0750 root root -"
    "d /var/lib/openhands 0750 root root -"
    "d /etc/evidara-coordinator 0750 root root -"
  ];

  environment.systemPackages = with pkgs; [
    age
    docker-compose
    git
    htop
    jq
    sops
    vim
  ];

  system.stateVersion = "24.11";
}
