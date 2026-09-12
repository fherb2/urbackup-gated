# Test system for urbackup-gated: real systemd, real sudo, real systemctl.
#
# What is deliberately faked instead of installed:
#   - the UrBackup client, replaced by a unit of the same name running sleep,
#     so start/stop/enable/disable behave identically from our side
#   - nmcli, since no container can produce a real wifi association
#   - notify-send, since there is no notification server here and the desktop
#     side belongs to the manual acceptance tests anyway
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV container=docker

RUN apt-get update && apt-get install -y --no-install-recommends \
        systemd systemd-sysv dbus \
        sudo python3 python3-watchdog \
    && rm -rf /var/lib/apt/lists/* \
    && find /etc/systemd/system /lib/systemd/system \
        -path '*.wants/*' -name '*getty*' -delete

# The account urbackup-gated is installed for. No sudo group membership: the
# only privileges it may have are the three the installer grants.
RUN useradd --create-home --shell /bin/bash tester

STOPSIGNAL SIGRTMIN+3
CMD ["/lib/systemd/systemd"]
