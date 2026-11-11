#!/bin/sh
EXT_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd) || exit 1
# shellcheck source=kindle/extensions/kindle-ha-dash/bin/lib.sh
. "$EXT_DIR/bin/lib.sh"
khd_init "$EXT_DIR" || exit 1
# Also catches a concurrently launching dash that has not published a PID yet.
: > "$STOP_FILE" || exit 1
if khd_stop_pid=$(khd_find_pid); then
    khd_kill -TERM "$khd_stop_pid" 2>/dev/null || :
    khd_stop_wait=0
    while khd_pid_running "$khd_stop_pid" && [ "$khd_stop_wait" -lt 10 ]; do
        khd_sleep 1
        khd_stop_wait=$((khd_stop_wait + 1))
    done
    if khd_pid_running "$khd_stop_pid"; then
        khd_log 'stop: TERM timed out; killing verified dashboard PID'
        khd_kill -KILL "$khd_stop_pid" 2>/dev/null || :
        khd_sleep 1
    fi
    if khd_pid_running "$khd_stop_pid"; then
        echo 'Dashboard could not be stopped; stop flag remains set. Inspect over SSH.' >&2
        exit 1
    fi
fi
khd_restore_ui
# Leave stale singleton cleanup to the next launch; it verifies process identity.
khd_log 'stop completed; alarm/wifi/UI restoration requested (check preceding errors)'
echo 'Dashboard stopped. Alarm, Wi-Fi and UI restoration requested; check the log for errors.'
