#!/bin/sh
EXT_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd) || exit 1
# shellcheck source=kindle/extensions/kindle-ha-dash/bin/lib.sh
. "$EXT_DIR/bin/lib.sh"
khd_init "$EXT_DIR" || { printf '%s\n' 'startup refused: invalid configuration; run Self-test for the setting name' >> "$EXT_DIR/dashboard.log"; exit 1; }
case ${1:---loop} in --loop|--once) khd_mode=${1:---loop} ;; *) echo 'Usage: sh dash.sh [--loop|--once]' >&2; exit 1 ;; esac
KHD_MODE=$khd_mode
if ! khd_validate_server; then
    khd_log 'startup refused: configure HTTPS BASE_URL, TOKEN and HTTP client'
    exit 1
fi
if ! khd_claim_pid; then
    khd_log 'startup refused: another instance or lock recovery in progress'
    exit 1
fi
trap 'khd_cleanup' 0
trap 'trap "" HUP INT TERM; khd_cancel_child; khd_guard_stop; exit 0' HUP INT TERM
khd_stop_requested && exit 0
khd_prepare_ui || exit 1
khd_log "dashboard started version=$CLIENT_VERSION mode=$khd_mode"
KHD_INITIAL_CYCLE=1
khd_run_cycle
[ "$khd_mode" != --once ] || exit 0
while ! khd_stop_requested; do khd_loop_turn || break; done
