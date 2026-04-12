# Three NVMe drives:
#   nvme0n1 — root (unencrypted, boots without passphrase)
#   nvme1n1 — Docker state (LUKS-encrypted, unlocked via initrd SSH)
#   nvme2n1 — runners/agent state (LUKS-encrypted, unlocked via initrd SSH)
#
# On reboot, SSH into initrd (port 2222) and run:
#   systemd-tty-ask-password-agent
# to provide the LUKS passphrase for both encrypted drives.
#
# First-time setup with nixos-anywhere:
#   nixos-anywhere --disk-encryption-keys /tmp/luks-docker.key <passphrase-file> \
#                  --disk-encryption-keys /tmp/luks-data.key <passphrase-file> \
#                  --flake .#hetzner-runner root@88.99.26.120
{
  disko.devices = {
    disk = {
      nvme0n1 = {
        type = "disk";
        device = "/dev/nvme0n1";
        content = {
          type = "gpt";
          partitions = {
            bios = {
              size = "1M";
              type = "EF02";
            };
            root = {
              size = "100%";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/";
              };
            };
          };
        };
      };
      nvme1n1 = {
        type = "disk";
        device = "/dev/nvme1n1";
        content = {
          type = "gpt";
          partitions = {
            docker = {
              size = "100%";
              content = {
                type = "luks";
                name = "cryptdocker";
                settings = {
                  allowDiscards = true;
                  keyFile = "/tmp/luks-docker.key";
                };
                content = {
                  type = "filesystem";
                  format = "ext4";
                  mountpoint = "/var/lib/docker";
                };
              };
            };
          };
        };
      };
      nvme2n1 = {
        type = "disk";
        device = "/dev/nvme2n1";
        content = {
          type = "gpt";
          partitions = {
            data = {
              size = "100%";
              content = {
                type = "luks";
                name = "cryptdata";
                settings = {
                  allowDiscards = true;
                  keyFile = "/tmp/luks-data.key";
                };
                content = {
                  type = "filesystem";
                  format = "ext4";
                  mountpoint = "/var/lib/github-runners";
                };
              };
            };
          };
        };
      };
    };
  };
}
