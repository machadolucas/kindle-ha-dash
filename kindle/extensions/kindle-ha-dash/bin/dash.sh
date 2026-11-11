#!/bin/sh
EXT_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd) || exit 1
# shellcheck source=kindle/extensions/kindle-ha-dash/bin/lib.sh
. "$EXT_DIR/bin/lib.sh"
khd_init "$EXT_DIR" || exit 1
case ${1:---loop} in --loop|--once) khd_mode=${1:---loop} ;; *) echo 'Usage: sh dash.sh [--loop|--once]' >&2; exit 1 ;; esac
if ! khd_validate_server; then
    khd_log 'startup refused: configure HTTPS BASE_URL, TOKEN and HTTP client'
    exit 1
fi
if ! khd_claim_pid; then
    khd_log 'startup refused: another instance or lock recovery in progress'
    exit 1
fi
trap 'khd_cleanup' 0
trap 'exit 0' HUP INT TERM
khd_stop_requested && exit 0
khd_prepare_ui || exit 1
khd_log "dashboard started version=$CLIENT_VERSION mode=$khd_mode"
while ! khd_stop_requested; do
    khd_cycle_start=$(khd_clock)
    khd_cycle
    khd_log "cycle complete elapsed=$(( $(khd_clock) - khd_cycle_start )) next_sleep=$KHD_NEXT_SLEEP"
    [ "$khd_mode" != --once ] || break
    khd_stop_requested && break
    khd_sleep_cycle "$KHD_NEXT_SLEEP" || break
done
