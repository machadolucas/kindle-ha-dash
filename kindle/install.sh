#!/bin/sh
# Host-only installer. No rsync, activation or boot hooks. Does not copy config.sh.
set -eu
if [ "$#" -ne 1 ]; then
    echo 'Usage: kindle/install.sh root@<kindle-ip>' >&2
    exit 1
fi
case $1 in ''|-*|*[!a-zA-Z0-9_.@:-]*) echo 'Use a plain SSH host or user@host (no options).' >&2; exit 1 ;; esac
KHD_TARGET=$1
KHD_SOURCE=$(CDPATH= cd -P "$(dirname "$0")/extensions/kindle-ha-dash" && pwd)
KHD_REMOTE=/mnt/us/extensions/kindle-ha-dash
# New scp defaults to SFTP; old Kindle SSH servers usually only support SCP.
# Set SCP_LEGACY=0 for an older Mac scp that does not recognize -O.
if [ "${SCP_LEGACY:-1}" = 1 ]; then set -- -O; else set --; fi
echo 'Copying extension. Stop a running dashboard before upgrading.'
ssh "$KHD_TARGET" "mkdir -p '$KHD_REMOTE/bin'"
scp "$@" "$KHD_SOURCE/config.xml" "$KHD_SOURCE/menu.json" "$KHD_SOURCE/config.sh.example" "$KHD_TARGET:$KHD_REMOTE/"
scp "$@" "$KHD_SOURCE/bin/start.sh" "$KHD_SOURCE/bin/stop.sh" "$KHD_SOURCE/bin/dash.sh" "$KHD_SOURCE/bin/lib.sh" "$KHD_SOURCE/bin/selftest.sh" "$KHD_TARGET:$KHD_REMOTE/bin/"
ssh "$KHD_TARGET" "if [ ! -f '$KHD_REMOTE/config.sh' ]; then cp '$KHD_REMOTE/config.sh.example' '$KHD_REMOTE/config.sh'; fi"
echo 'Installed; existing config.sh preserved. Edit config.sh over SSH before starting.'
