#!/bin/sh
EXT_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd) || exit 1
# shellcheck source=kindle/extensions/kindle-ha-dash/bin/lib.sh
. "$EXT_DIR/bin/lib.sh"
khd_init "$EXT_DIR" || exit 1
case ${1:---loop} in --loop|--once) khd_mode=${1:---loop} ;; *) echo 'Usage: sh start.sh [--loop|--once]' >&2; exit 1 ;; esac
if khd_find_pid >/dev/null; then
    echo 'Dashboard is already running. Stop it before Refresh once.'
    exit 1
fi
if ! khd_validate_server; then
    echo 'Configure BASE_URL, TOKEN and a working curl client in config.sh first.' >&2
    exit 1
fi
mkdir -p "$STATE_DIR" || exit 1
# Explicit Start / Refresh once acknowledges a previous USB stop request.
rm -f "$STOP_FILE" || exit 1
if command -v setsid >/dev/null 2>&1; then
    if command -v nohup >/dev/null 2>&1; then
        nohup setsid sh "$EXT_DIR/bin/dash.sh" "$khd_mode" </dev/null >/dev/null 2>&1 &
    else
        setsid sh "$EXT_DIR/bin/dash.sh" "$khd_mode" </dev/null >/dev/null 2>&1 &
    fi
elif command -v nohup >/dev/null 2>&1; then
    nohup sh "$EXT_DIR/bin/dash.sh" "$khd_mode" </dev/null >/dev/null 2>&1 &
else
    echo 'Neither setsid nor nohup is available; refusing an attached launch.' >&2
    exit 1
fi
khd_log "launch requested mode=$khd_mode (check log for started)"
echo 'Launch requested; check dashboard.log for startup diagnostics.'
