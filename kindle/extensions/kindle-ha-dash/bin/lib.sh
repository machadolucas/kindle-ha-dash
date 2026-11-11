#!/bin/sh
# Definitions only. Device I/O starts only when a caller invokes a function.

khd_init() {
    EXT_DIR=$1
    if [ -f "$EXT_DIR/config.sh" ]; then
        # This is trusted, user-edited shell configuration.
        # shellcheck disable=SC1090,SC1091
        . "$EXT_DIR/config.sh" || return 1
    fi
    : "${CLIENT_VERSION:=1.0.0}" "${BASE_URL:=}" "${TOKEN:=}"
    : "${FALLBACK_SLEEP_SECONDS:=1800}" "${MIN_SLEEP_SECONDS:=60}"
    : "${MAX_SLEEP_SECONDS:=7200}" "${AWAKE_INTERVAL_SECONDS:=300}"
    : "${WIFI_TIMEOUT_SECONDS:=30}" "${WIFI_RETRIES:=2}"
    : "${HTTP_TIMEOUT_SECONDS:=45}" "${LOW_BATTERY_PERCENT:=10}"
    : "${STOP_FRAMEWORK:=0}" "${INSECURE_TLS:=0}" "${CA_BUNDLE:=}"
    : "${RESUME_DELAY_SECONDS:=3}" "${WIFI_TOGGLE_DELAY_SECONDS:=2}"
    : "${STATE_DIR:=/tmp/kindle-ha-dash}" "${PROC_ROOT:=/proc}"
    : "${RTC_ROOT:=/sys/class/rtc}" # Read-only selftest listing only.
    : "${PIDFILE:=$STATE_DIR/dash.pid}" "${TEMP_DIR:=$STATE_DIR/work}"
    : "${IMAGE_FILE:=$STATE_DIR/image.png}"
    : "${FRAMEWORK_MARKER:=$STATE_DIR/framework-stopped}"
    : "${DEBUG_FILE:=/mnt/us/kindle-ha-dash.debug}"
    : "${STOP_FILE:=/mnt/us/kindle-ha-dash.stop}"
    : "${LOG_FILE:=$EXT_DIR/dashboard.log}" "${LOG_MAX_BYTES:=131072}"
    : "${LIPC_SET_BIN:=lipc-set-prop}" "${LIPC_GET_BIN:=lipc-get-prop}"
    : "${LIPC_WAIT_BIN:=lipc-wait-event}" "${POWERD_TEST_BIN:=powerd_test}" "${DMESG_BIN:=dmesg}"
    : "${AUTO_SCREENSAVER:=1}" "${SCREENSAVER_REDRAW_DELAY_SECONDS:=3}"
    : "${SCREENSAVER_WAIT_SECONDS:=20}" "${WIFI_OFF_REDRAW_DELAY_SECONDS:=3}"
    : "${EVENT_LOG_VERBOSE:=0}" "${EVENT_WAIT_SECONDS:=5}" "${POLL_INTERVAL_SECONDS:=5}"
    : "${WAKE_TOLERANCE_SECONDS:=2}" "${WAKE_REDRAW:=1}"
    : "${FRONTLIGHT_OFF:=1}" "${FRONTLIGHT_STATE_FILE:=$EXT_DIR/frontlight.saved}"
    : "${RTC_WAKEUP_MODE:=relative}" "${RTC_WAKEUP_USE_INT:=1}" "${RTC_WAKEUP_CANCEL_MODE:=none}"
    : "${SUSPEND_DEFER_MODE:=none}" "${CYCLE_ABORT_SUSPEND:=1}"
    : "${GASGAUGE_BIN:=gasgauge-info}" "${EIPS_BIN:=eips}"
    : "${USB_POWER_PATH:=/sys/devices/system/wario_charger/wario_charger0/connected}"
    : "${CHARGING_PATH:=/sys/devices/system/wario_charger/wario_charger0/charging}"
    : "${START_BIN:=start}" "${STOP_BIN:=stop}" "${SLEEP_BIN:=sleep}"
    : "${DATE_BIN:=date}" "${KILL_BIN:=kill}"
    : "${EIPS_STATUS_COL:=0}" "${EIPS_STATUS_ROW:=auto}"
    : "${FRAMEWORK_JOBS:=framework lab126_gui}"
    if [ -z "${HTTP_CLIENT_BIN:-}" ]; then
        HTTP_CLIENT_BIN=$(khd_find_tool "$EXT_DIR/bin/curl" /mnt/us/usbnet/bin/curl curl) || HTTP_CLIENT_BIN=
    fi
    if [ "${FBINK_BIN:-auto}" = auto ]; then
        FBINK_BIN=$(khd_find_tool fbink /mnt/us/libkh/bin/fbink /mnt/us/koreader/fbink /mnt/us/koreader/bin/fbink) || FBINK_BIN=
    fi
    KHD_BATTERY= KHD_CHARGING=0 KHD_USB_POWERED=0 KHD_CHILD_PID= KHD_OWNS_PID=0
    KHD_WIFI_OFF=0 KHD_HEADER_SLEEP= KHD_FULL_REFRESH=0
    KHD_MODE=--loop KHD_INITIAL_CYCLE=0 KHD_GUARD_PID= KHD_LAST_POWER_CLASS=
    KHD_POWER_STATE= KHD_POWER_STATUS= KHD_POWER_CLASS=unknown KHD_POWER_PHASE=unknown
    KHD_TARGET_EPOCH=0 KHD_SCREENSAVER_SINCE= KHD_EVENT_TEXT= KHD_EVENT_RC=0
    KHD_AWAKE_MODE=0 KHD_POLL_NOTICE=0 KHD_LAST_WIFI_STATE= KHD_AUTO_ENTERED=0
    KHD_LAST_READY_EPOCH= KHD_LAST_EVENT_ELAPSED=0
    khd_validate_numbers
}

khd_find_tool() {
    for khd_tool do
        if command -v "$khd_tool" >/dev/null 2>&1; then
            command -v "$khd_tool"
            return 0
        fi
    done
    return 1
}

# Limit intervals to nine decimal digits before shell arithmetic; normalize 08.
khd_uint() {
    case ${1:-} in ''|*[!0-9]*) return 1 ;; esac
    [ "${#1}" -le 9 ] || return 1
    printf '%s\n' "$1" | awk '{ printf "%.0f\n", $0 + 0 }'
}

khd_validate_numbers() {
    # Fixed names only: no config values are ever evaluated as code here.
    for khd_setting in FALLBACK_SLEEP_SECONDS MIN_SLEEP_SECONDS MAX_SLEEP_SECONDS AWAKE_INTERVAL_SECONDS WIFI_TIMEOUT_SECONDS WIFI_RETRIES HTTP_TIMEOUT_SECONDS LOW_BATTERY_PERCENT LOG_MAX_BYTES RESUME_DELAY_SECONDS WIFI_TOGGLE_DELAY_SECONDS WIFI_OFF_REDRAW_DELAY_SECONDS SCREENSAVER_REDRAW_DELAY_SECONDS SCREENSAVER_WAIT_SECONDS EVENT_WAIT_SECONDS POLL_INTERVAL_SECONDS WAKE_TOLERANCE_SECONDS; do
        eval 'khd_value=${'"$khd_setting"'}'
        khd_value=$(khd_uint "$khd_value") || {
            printf 'Invalid numeric configuration: %s\n' "$khd_setting" >&2
            return 1
        }
        eval "$khd_setting=\$khd_value"
    done
    [ "$MIN_SLEEP_SECONDS" -ge 1 ] &&
        [ "$MAX_SLEEP_SECONDS" -ge "$MIN_SLEEP_SECONDS" ] &&
        [ "$AWAKE_INTERVAL_SECONDS" -ge 1 ] &&
        [ "$WIFI_TIMEOUT_SECONDS" -ge 1 ] &&
        [ "$WIFI_RETRIES" -le 20 ] &&
        [ "$HTTP_TIMEOUT_SECONDS" -ge 1 ] &&
        [ "$LOW_BATTERY_PERCENT" -le 100 ] &&
        [ "$LOG_MAX_BYTES" -ge 1024 ] &&
        [ "$EVENT_WAIT_SECONDS" -ge 1 ] && [ "$EVENT_WAIT_SECONDS" -le 60 ] &&
        [ "$POLL_INTERVAL_SECONDS" -ge 1 ] && [ "$POLL_INTERVAL_SECONDS" -le 60 ] &&
        [ "$SCREENSAVER_WAIT_SECONDS" -le 120 ] || {
        printf '%s\n' 'Invalid configuration limits (see config.sh.example).' >&2
        return 1
    }
    case $STOP_FRAMEWORK:$INSECURE_TLS in 0:0|0:1|1:0|1:1) ;; *) return 1 ;; esac
    for khd_setting in AUTO_SCREENSAVER EVENT_LOG_VERBOSE FRONTLIGHT_OFF RTC_WAKEUP_USE_INT WAKE_REDRAW CYCLE_ABORT_SUSPEND; do
        eval 'khd_value=${'"$khd_setting"'}'
        case $khd_value in 0|1) ;; *) printf 'Invalid boolean configuration: %s\n' "$khd_setting" >&2; return 1 ;; esac
    done
    case $RTC_WAKEUP_MODE in relative|epoch) ;; *) return 1 ;; esac
    case $RTC_WAKEUP_CANCEL_MODE in none|zero) ;; *) return 1 ;; esac
    case $SUSPEND_DEFER_MODE in none|deferSuspend) ;; *) return 1 ;; esac
}

khd_validate_server() {
    # Reject URL credentials/query/fragment; never echo configuration values.
    case $BASE_URL in https://?*) ;; *) return 1 ;; esac
    case ${BASE_URL#https://} in *[\ @\?\#]*|'') return 1 ;; esac
    [ -n "$TOKEN" ] || return 1
    [ -n "$HTTP_CLIENT_BIN" ] && command -v "$HTTP_CLIENT_BIN" >/dev/null 2>&1 || return 1
    [ -z "$CA_BUNDLE" ] || [ -r "$CA_BUNDLE" ]
}

khd_date() { "$DATE_BIN" "$@"; }
khd_sleep() { "$SLEEP_BIN" "$@"; }
khd_lipc_set() { "$LIPC_SET_BIN" "$@"; }
khd_lipc_get() { "$LIPC_GET_BIN" "$@"; }
khd_gasgauge() { "$GASGAUGE_BIN" "$@"; }
khd_eips() { "$EIPS_BIN" "$@"; }
khd_fbink() { [ -n "$FBINK_BIN" ] && "$FBINK_BIN" "$@"; }
khd_kill() { "$KILL_BIN" "$@"; }
khd_start_job() { "$START_BIN" "$1"; }
khd_stop_job() { "$STOP_BIN" "$1"; }
khd_read_node() { cat "$1"; }
khd_now() { khd_date +%s; }
khd_clock() {
    # Old Kindle kernels differ on whether uptime includes time in suspend.
    # Wall epoch is also the RTC timebase; negative jumps are clamped below.
    khd_now
}

khd_log() {
    [ -n "$LOG_FILE" ] || return 0
    if [ -f "$LOG_FILE" ]; then
        khd_log_bytes=$(wc -c < "$LOG_FILE" | tr -d ' ')
        if [ "$khd_log_bytes" -gt "$LOG_MAX_BYTES" ]; then
            mv -f "$LOG_FILE" "$LOG_FILE.old" || return 0
        fi
    fi
    printf '%s %s\n' "$(khd_date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$LOG_FILE" || :
}

khd_parse_headers() {
    # A proxy's CONNECT or a 1xx block must not supply final-response headers.
    khd_headers=$(awk '
        { sub(/\r$/, "") }
        /^HTTP\// { s=""; f="0"; next }
        { p=index($0, ":"); if (!p) next
          n=tolower(substr($0,1,p-1)); v=substr($0,p+1)
          gsub(/^[ \t]+|[ \t]+$/, "", v)
          if (n=="x-sleep-seconds") s=v
          if (n=="x-full-refresh") f=v }
        END { print s; print f }
    ' "$1") || return 1
    KHD_HEADER_SLEEP=$(printf '%s\n' "$khd_headers" | sed -n '1p')
    KHD_FULL_REFRESH=$(printf '%s\n' "$khd_headers" | sed -n '2p')
    [ "$KHD_FULL_REFRESH" = 1 ] || KHD_FULL_REFRESH=0
}

khd_sleep_seconds() {
    case ${1:-} in
        ''|*[!0-9]*) khd_seconds=$(khd_uint "$FALLBACK_SLEEP_SECONDS") || khd_seconds=1800 ;;
        *) khd_seconds=$1 ;;
    esac
    # Clamp before converting to shell integers, even for huge numeric headers.
    printf '%s\n' "$khd_seconds" | awk -v low="$MIN_SLEEP_SECONDS" -v high="$MAX_SLEEP_SECONDS" '
        { n=$0+0; if(n<low) n=low; if(n>high) n=high; printf "%.0f\n", n }'
}

khd_png_valid() {
    [ -f "$1" ] || return 1
    khd_magic=$(od -An -tx1 -N8 "$1" 2>/dev/null | tr -d ' \n\r\t')
    [ "$khd_magic" = 89504e470d0a1a0a ]
}
khd_urlencode() {
    # Encode bytes, including URL syntax characters in arbitrary server tokens.
    LC_ALL=C od -An -v -tx1 | awk '{ for (i=1;i<=NF;i++) printf "%%%s", toupper($i) } END { print "" }'
}

khd_read_battery() {
    KHD_BATTERY=$(khd_gasgauge -c 2>/dev/null | awk '
        /^[ \t]*[0-9]+%[ \t]*$/ { gsub(/[% \t]/, ""); if ($0+0<=100) print $0+0; exit }')
    KHD_CHARGING=$(khd_lipc_get com.lab126.powerd isCharging 2>/dev/null | tr -d ' \t\r\n')
    case $KHD_CHARGING in 0|1) ;; *)
        KHD_CHARGING=$(khd_read_node "$CHARGING_PATH" 2>/dev/null | tr -d ' \t\r\n')
    ;; esac
    case $KHD_CHARGING in 0|1) ;; *)
        # Some gasgauge variants expose a textual charging status; others do not.
        KHD_CHARGING=$(khd_gasgauge -s 2>/dev/null | awk '
            { s=tolower($0) }
            s ~ /discharging|not charging/ { print 0; exit }
            s ~ /charging|full/ { print 1; exit }')
        [ "$KHD_CHARGING" = 1 ] || KHD_CHARGING=0
    ;; esac
    KHD_USB_POWERED=$(khd_read_node "$USB_POWER_PATH" 2>/dev/null | tr -d ' \t\r\n')
    case $KHD_USB_POWERED in 0|1) ;; *) KHD_USB_POWERED=unknown ;; esac
}

khd_low_battery() {
    [ -n "$KHD_BATTERY" ] && [ "$KHD_BATTERY" -lt "$LOW_BATTERY_PERCENT" ] && [ "$KHD_CHARGING" != 1 ]
}
khd_awake() { [ "$KHD_CHARGING" = 1 ] || [ "$KHD_USB_POWERED" = 1 ] || [ -e "$DEBUG_FILE" ]; }
khd_stop_requested() { [ -e "$STOP_FILE" ]; }

# Background + wait lets TERM interrupt sleep/curl promptly in ash and dash.
khd_wait_child() {
    KHD_CHILD_PID=$!
    wait "$KHD_CHILD_PID"
    khd_child_rc=$?
    KHD_CHILD_PID=
    return "$khd_child_rc"
}
khd_pause() {
    khd_pause_left=$1
    while [ "$khd_pause_left" -gt 0 ]; do
        khd_stop_requested && return 1
        # A debug/USB escape should also work during a fallback plain sleep.
        if [ "$KHD_WIFI_OFF" = 1 ]; then
            khd_read_battery
            if khd_awake; then
                khd_wifi_set 1 || :
                [ "$khd_pause_left" -le "$AWAKE_INTERVAL_SECONDS" ] || khd_pause_left=$AWAKE_INTERVAL_SECONDS
            fi
        fi
        khd_pause_slice=5
        [ "$khd_pause_left" -ge 5 ] || khd_pause_slice=$khd_pause_left
        # Launch the binary directly so TERM reaches sleep, not a wrapper shell.
        "$SLEEP_BIN" "$khd_pause_slice" &
        khd_wait_child || return 1
        khd_pause_left=$((khd_pause_left - khd_pause_slice))
    done
}

khd_wifi_set() {
    khd_wifi_set_start=$(khd_now)
    khd_power_snapshot "before-wifi:$1"
    khd_wifi_output=$(khd_lipc_set com.lab126.cmd wirelessEnable "$1" 2>&1)
    khd_wifi_rc=$?
    khd_log "wifi set requested=$1 rc=$khd_wifi_rc elapsed=$(( $(khd_now) - khd_wifi_set_start )) output=[$khd_wifi_output]"
    khd_power_snapshot "after-wifi:$1"
    if [ "$khd_wifi_rc" = 0 ]; then
        if [ "$1" = 0 ]; then KHD_WIFI_OFF=1; else KHD_WIFI_OFF=0; fi
        return 0
    fi
    KHD_WIFI_OFF=0
    khd_log "wifi command failed (requested=$1)"
    return 1
}
khd_wifi_state() { khd_lipc_get com.lab126.wifid cmState 2>/dev/null | tr -d '\r\n'; }
khd_wifi_connect() {
    khd_wifi_start=$(khd_now)
    khd_wifi_attempt=0
    while [ "$khd_wifi_attempt" -le "$WIFI_RETRIES" ]; do
        khd_stop_requested && return 1
        khd_cycle_can_draw || return 1
        if [ "$khd_wifi_attempt" -gt 0 ]; then
            khd_log "wifi reconnect retry=$khd_wifi_attempt"
            khd_read_battery
            # An awake device must retain its radio; retry enable without off.
            if ! khd_awake; then
                khd_wifi_set 0 || :
                khd_pause "$WIFI_TOGGLE_DELAY_SECONDS" || return 1
            fi
        fi
        khd_wifi_set 1 || :
        khd_wifi_waited=0
        while [ "$khd_wifi_waited" -lt "$WIFI_TIMEOUT_SECONDS" ]; do
            khd_cycle_can_draw || return 1
            khd_wifi_current=$(khd_wifi_state)
            if [ "$khd_wifi_current" != "$KHD_LAST_WIFI_STATE" ] || [ "$EVENT_LOG_VERBOSE" = 1 ]; then
                khd_log "wifi state=[$khd_wifi_current] retry=$khd_wifi_attempt waited=$khd_wifi_waited elapsed=$(( $(khd_now) - khd_wifi_start ))"
                KHD_LAST_WIFI_STATE=$khd_wifi_current
            fi
            [ "$khd_wifi_current" != CONNECTED ] || { khd_log "wifi CONNECTED elapsed=$(( $(khd_now) - khd_wifi_start ))"; return 0; }
            khd_pause 1 || return 1
            khd_wifi_waited=$((khd_wifi_waited + 1))
        done
        khd_wifi_attempt=$((khd_wifi_attempt + 1))
    done
    khd_log "wifi connection timeout elapsed=$(( $(khd_now) - khd_wifi_start ))"
    return 1
}

khd_http_request() {
    # $1 = URL (never log); $2 = output prefix. No redirects or TLS downgrades.
    khd_request_prefix=$2
    set -- "$HTTP_CLIENT_BIN" -sS --max-time "$HTTP_TIMEOUT_SECONDS" -D "$2.headers" -o "$2.png" -w '%{http_code}' "$1"
    [ -z "$CA_BUNDLE" ] || set -- "$@" --cacert "$CA_BUNDLE"
    [ "$INSECURE_TLS" != 1 ] || set -- "$@" --insecure
    # Do not persist client stderr: diagnostics may include the secret URL.
    "$@" > "$khd_request_prefix.code" 2>/dev/null &
    khd_wait_child
}
khd_fetch() {
    KHD_HEADER_SLEEP= KHD_FULL_REFRESH=0
    khd_validate_server || { khd_log 'HTTP configuration/client invalid'; return 1; }
    mkdir -p "$TEMP_DIR" "$(dirname "$IMAGE_FILE")" || return 1
    KHD_HTTP_PREFIX=$TEMP_DIR/fetch.$$
    rm -f "$KHD_HTTP_PREFIX.headers" "$KHD_HTTP_PREFIX.png" "$KHD_HTTP_PREFIX.code"
    khd_token_path=$(printf '%s' "$TOKEN" | khd_urlencode)
    khd_client_query=$(printf '%s' "$CLIENT_VERSION" | khd_urlencode)
    khd_url=${BASE_URL%/}/api/kindle_dash/$khd_token_path/image.png?battery=$KHD_BATTERY\&charging=$KHD_CHARGING\&client=$khd_client_query
    if khd_http_request "$khd_url" "$KHD_HTTP_PREFIX"; then
        khd_http_code=$(cat "$KHD_HTTP_PREFIX.code")
        if [ "$khd_http_code" = 200 ] && khd_png_valid "$KHD_HTTP_PREFIX.png"; then
            khd_parse_headers "$KHD_HTTP_PREFIX.headers"
            if mv -f "$KHD_HTTP_PREFIX.png" "$IMAGE_FILE"; then
                khd_log "fetch OK full_refresh=$KHD_FULL_REFRESH"
                rm -f "$KHD_HTTP_PREFIX.headers" "$KHD_HTTP_PREFIX.code"
                return 0
            fi
        fi
        # Only numeric HTTP status is safe to log from an arbitrary client.
        case $khd_http_code in [0-9][0-9][0-9]) ;; *) khd_http_code=invalid ;; esac
        khd_log "fetch rejected http=$khd_http_code (status, PNG signature, or storage)"
    else
        khd_transport_rc=$?
        khd_log "fetch failed client_exit=$khd_transport_rc (transport/TLS/client timeout)"
    fi
    rm -f "$KHD_HTTP_PREFIX.headers" "$KHD_HTTP_PREFIX.png" "$KHD_HTTP_PREFIX.code"
    KHD_HEADER_SLEEP= KHD_FULL_REFRESH=0
    return 1
}

khd_display() {
    khd_png_valid "$IMAGE_FILE" || return 1
    if [ -n "$FBINK_BIN" ]; then
        if [ "$KHD_FULL_REFRESH" = 1 ]; then
            khd_fbink -q -f -g "file=$IMAGE_FILE" >/dev/null 2>&1 && return 0
        else
            khd_fbink -q -g "file=$IMAGE_FILE" >/dev/null 2>&1 && return 0
        fi
        khd_log 'fbink failed; trying eips'
    fi
    if [ "$KHD_FULL_REFRESH" = 1 ]; then
        khd_eips -c >/dev/null 2>&1 || :
        khd_eips -f -g "$IMAGE_FILE" >/dev/null 2>&1
    else
        khd_eips -g "$IMAGE_FILE" >/dev/null 2>&1
    fi
}
khd_status() {
    if [ -n "$FBINK_BIN" ]; then
        khd_fbink -q -x 0 -y -1 "$1" >/dev/null 2>&1 && return 0
    fi
    khd_status_row=$EIPS_STATUS_ROW
    if [ "$khd_status_row" = auto ]; then
        khd_status_row=$(khd_eips -i 2>/dev/null | awk '
            /[0-9]+[ \t]+rows/ { for(i=2;i<=NF;i++) if ($i ~ /^rows/) {print $(i-1)-1; exit} }')
        # PW3 default eips 16x24 font: floor(1448/24)-1 = 59.
        case $khd_status_row in ''|*[!0-9]*) khd_status_row=59 ;; esac
    fi
    khd_eips "$EIPS_STATUS_COL" "$khd_status_row" "$1" >/dev/null 2>&1 || :
}

khd_cycle() {
    khd_power_snapshot cycle-start
    khd_cycle_can_draw || return 1
    khd_frontlight_zero || :
    khd_read_battery
    khd_log "wake battery=${KHD_BATTERY:-unknown} charging=$KHD_CHARGING usb_power=$KHD_USB_POWERED"
    KHD_HEADER_SLEEP= KHD_FULL_REFRESH=0 khd_shown=0
    if khd_low_battery; then
        khd_log 'low battery: fetch skipped'
        khd_cycle_can_draw && khd_status 'battery low, please charge'
        KHD_NEXT_SLEEP=$MAX_SLEEP_SECONDS
    else
        if khd_wifi_connect && khd_cycle_can_draw && khd_fetch; then
            if khd_cycle_can_draw; then
                if khd_display; then khd_shown=1; else khd_log 'display failed'; khd_status "display failed $(khd_date +%H:%M)"; fi
            fi
        else
            khd_cycle_can_draw && khd_status "no connection $(khd_date +%H:%M)"
        fi
        KHD_NEXT_SLEEP=$(khd_sleep_seconds "$KHD_HEADER_SLEEP")
    fi
    # Recheck power/debug after a possibly long request.
    khd_read_battery
    khd_power_snapshot cycle-finish
    if khd_awake || { [ "$KHD_INITIAL_CYCLE" = 0 ] && [ "$KHD_POWER_CLASS" != screensaver ]; }; then
        khd_wifi_set 1 || :
        [ "$KHD_NEXT_SLEEP" -le "$AWAKE_INTERVAL_SECONDS" ] || KHD_NEXT_SLEEP=$AWAKE_INTERVAL_SECONDS
        khd_log "awake mode interval=$KHD_NEXT_SLEEP"
    else
        khd_wifi_set 0 || :
        # The stock UI paints an airplane-mode icon over our image when wifi
        # goes off; wait for it, then repaint (partial refresh, no flash).
        if [ "$khd_shown" = 1 ] && [ "$WIFI_OFF_REDRAW_DELAY_SECONDS" -gt 0 ]; then
            khd_log "repaint reason=wifi-off delay=$WIFI_OFF_REDRAW_DELAY_SECONDS"
            khd_pause "$WIFI_OFF_REDRAW_DELAY_SECONDS" || return 1
            KHD_FULL_REFRESH=0
            khd_cycle_can_draw && khd_display || :
        fi
    fi
    khd_power_snapshot cycle-end
}
khd_cycle_can_draw() {
    khd_stop_requested && return 1
    [ "$KHD_MODE" != --once ] || return 0
    [ "$KHD_INITIAL_CYCLE" != 1 ] || return 0
    khd_power_snapshot cycle-draw-check
    [ "$KHD_POWER_CLASS" = screensaver ] || { khd_log 'cycle interrupted: stock UI active/unknown; no draw/fetch'; return 1; }
}

# Always log setter output/exit status: powerd properties vary across firmware.
khd_power_set() {
    khd_power_snapshot "before-set:$1"
    if [ "$1" = powerButton ] && [ "$KHD_POWER_CLASS" != active ]; then
        khd_log 'powerButton skipped: state changed before toggle'
        return 0
    fi
    khd_set_property=$1 khd_set_value=$2
    if [ "$khd_set_property" = rtcWakeup ] && [ "$RTC_WAKEUP_USE_INT" = 0 ]; then
        khd_set_output=$(khd_lipc_set com.lab126.powerd "$khd_set_property" "$khd_set_value" 2>&1)
    else
        khd_set_output=$(khd_lipc_set -i com.lab126.powerd "$khd_set_property" "$khd_set_value" 2>&1)
    fi
    khd_set_rc=$?
    khd_log "powerd set property=$khd_set_property value=$khd_set_value rc=$khd_set_rc output=[$khd_set_output]"
    khd_power_snapshot "after-set:$khd_set_property"
    return "$khd_set_rc"
}

khd_power_snapshot() {
    KHD_POWER_STATE=$(khd_lipc_get com.lab126.powerd state 2>&1)
    khd_state_rc=$?
    KHD_POWER_STATUS=$(khd_lipc_get com.lab126.powerd status 2>&1)
    khd_status_rc=$?
    # Classify only a successful state property, never words from an error or
    # the many unrelated fields of status. Preserve both exact strings in logs.
    KHD_POWER_PHASE=unknown KHD_POWER_CLASS=unknown
    if [ "$khd_state_rc" = 0 ]; then
        khd_state_lower=$(printf '%s' "$KHD_POWER_STATE" | tr '[:upper:]' '[:lower:]')
        case $khd_state_lower in
            *ready*) KHD_POWER_PHASE=ready; KHD_POWER_CLASS=screensaver ;;
            *screensaver*|*'screen saver'*) KHD_POWER_PHASE=screensaver; KHD_POWER_CLASS=screensaver ;;
            *suspend*) KHD_POWER_PHASE=suspend; KHD_POWER_CLASS=screensaver ;;
            *active*) KHD_POWER_PHASE=active; KHD_POWER_CLASS=active ;;
        esac
    fi
    if [ "$EVENT_LOG_VERBOSE" = 1 ] || [ "$KHD_POWER_STATE" != "${KHD_LOGGED_POWER_STATE:-}" ]; then
        khd_log "powerd snapshot step=$1 state_rc=$khd_state_rc state=[$KHD_POWER_STATE] status_rc=$khd_status_rc status=[$KHD_POWER_STATUS] class=$KHD_POWER_CLASS phase=$KHD_POWER_PHASE"
        KHD_LOGGED_POWER_STATE=$KHD_POWER_STATE
    fi
}

khd_frontlight_start() {
    [ "$FRONTLIGHT_OFF" = 1 ] || return 0
    # Keep a crash survivor; never replace the original setting with our zero.
    if [ ! -f "$FRONTLIGHT_STATE_FILE" ]; then
        khd_fl_saved=$(khd_lipc_get com.lab126.powerd flIntensity 2>/dev/null)
        khd_fl_saved=$(khd_uint "$khd_fl_saved") || { khd_log 'frontlight save failed; leaving light unchanged'; return 1; }
        (umask 077; printf '%s\n' "$khd_fl_saved" > "$FRONTLIGHT_STATE_FILE.tmp" && mv -f "$FRONTLIGHT_STATE_FILE.tmp" "$FRONTLIGHT_STATE_FILE") || return 1
        khd_log "frontlight saved value=$khd_fl_saved file=$FRONTLIGHT_STATE_FILE"
    else
        khd_fl_saved=$(khd_uint "$(cat "$FRONTLIGHT_STATE_FILE")") || { khd_log 'frontlight saved file invalid; leaving light unchanged'; return 1; }
        khd_log "frontlight retained saved value=$khd_fl_saved"
    fi
    khd_frontlight_zero
}
khd_frontlight_zero() {
    [ "$FRONTLIGHT_OFF" = 1 ] && [ -f "$FRONTLIGHT_STATE_FILE" ] || return 0
    khd_power_set flIntensity 0
}
khd_frontlight_restore() {
    [ -f "$FRONTLIGHT_STATE_FILE" ] || return 0
    khd_fl_restore=$(khd_uint "$(cat "$FRONTLIGHT_STATE_FILE")") || { khd_log 'frontlight restore refused: invalid saved value'; return 1; }
    if khd_power_set flIntensity "$khd_fl_restore"; then
        khd_log "frontlight restored value=$khd_fl_restore"
        rm -f "$FRONTLIGHT_STATE_FILE"
    else
        khd_log 'frontlight restore failed; saved file retained for Stop retry'
        return 1
    fi
}

khd_repaint() {
    khd_png_valid "$IMAGE_FILE" || return 0
    khd_log "repaint reason=$1 delay=$SCREENSAVER_REDRAW_DELAY_SECONDS"
    khd_pause "$SCREENSAVER_REDRAW_DELAY_SECONDS" || return 1
    khd_power_snapshot repaint
    if [ "$KHD_POWER_CLASS" = screensaver ]; then
        KHD_FULL_REFRESH=0
        khd_display || khd_log 'repaint failed'
        khd_power_snapshot after-repaint
    else
        khd_log "repaint skipped class=$KHD_POWER_CLASS (stock UI retained)"
    fi
}
khd_observe_power() {
    khd_power_snapshot "$1"
    if [ "$KHD_POWER_CLASS" != "$KHD_LAST_POWER_CLASS" ]; then
        khd_log "powerd transition from=${KHD_LAST_POWER_CLASS:-startup} to=$KHD_POWER_CLASS"
        if [ "$KHD_LAST_POWER_CLASS" = screensaver ] && [ "$KHD_POWER_CLASS" = active ]; then khd_wake_diagnostics; fi
        KHD_LAST_POWER_CLASS=$KHD_POWER_CLASS
        case $KHD_POWER_CLASS in
            active)
                KHD_SCREENSAVER_SINCE= KHD_LAST_READY_EPOCH=
                khd_log 'active: scheduled fetching paused; power button remains under user control'
                khd_wifi_set 1 || :
                ;;
            screensaver)
                KHD_SCREENSAVER_SINCE=$(khd_now)
                KHD_LAST_READY_EPOCH=
                khd_log "screensaver entered epoch=$KHD_SCREENSAVER_SINCE"
                khd_read_battery
                if ! khd_awake; then khd_wifi_set 0 || :; fi
                khd_repaint screensaver-return || return 1
                ;;
            *) khd_log 'unknown powerd state: scheduled fetching paused' ;;
        esac
    fi
}

khd_enter_screensaver() {
    khd_stop_requested && return 1
    [ "$KHD_MODE" != --once ] && [ "$AUTO_SCREENSAVER" = 1 ] && [ "$KHD_AUTO_ENTERED" = 0 ] || return 0
    # Only this first-success path may simulate a button. Never retry a
    # successful toggle: another press could wake the device instead.
    KHD_AUTO_ENTERED=1
    khd_power_snapshot before-enter-screensaver
    [ "$KHD_POWER_CLASS" = active ] || return 0
    khd_power_set preventScreenSaver 0 || return 1
    khd_stop_requested && return 1
    if ! khd_power_set powerButton 1; then
        khd_power_snapshot before-powerd-test
        [ "$KHD_POWER_CLASS" = active ] || return 0
        khd_button_output=$("$POWERD_TEST_BIN" -p 2>&1)
        khd_button_rc=$?
        khd_log "powerd_test -p rc=$khd_button_rc output=[$khd_button_output]"
        khd_power_snapshot after-powerd-test
        [ "$khd_button_rc" = 0 ] || return 1
    fi
    khd_enter_waited=0
    while ! khd_stop_requested; do
        khd_power_snapshot enter-screensaver-wait
        if [ "$KHD_POWER_CLASS" = screensaver ]; then
            khd_log "auto screensaver confirmed waited=$khd_enter_waited"
            khd_observe_power auto-screensaver
            return
        fi
        [ "$khd_enter_waited" -lt "$SCREENSAVER_WAIT_SECONDS" ] || break
        khd_pause 1 || return 1
        khd_enter_waited=$((khd_enter_waited + 1))
    done
    khd_log 'auto screensaver not confirmed; no further button presses; waiting for user/idle'
}

khd_arm_wakeup() {
    khd_stop_requested && return 1
    khd_wakeup_now=$(khd_now)
    khd_remaining=$((KHD_TARGET_EPOCH - khd_wakeup_now))
    [ "$khd_remaining" -ge "$MIN_SLEEP_SECONDS" ] || khd_remaining=$MIN_SLEEP_SECONDS
    khd_wakeup_value=$khd_remaining
    [ "$RTC_WAKEUP_MODE" != epoch ] || khd_wakeup_value=$((khd_wakeup_now + khd_remaining))
    khd_log "rtcWakeup arm target=$KHD_TARGET_EPOCH now=$khd_wakeup_now remaining=$khd_remaining mode=$RTC_WAKEUP_MODE int=$RTC_WAKEUP_USE_INT"
    khd_power_set rtcWakeup "$khd_wakeup_value"
}
khd_cancel_wakeup() {
    if [ "$RTC_WAKEUP_CANCEL_MODE" = zero ]; then
        khd_log 'rtcWakeup cancel: experimental zero requested (firmware semantics unverified)'
        khd_power_set rtcWakeup 0 || :
    else
        khd_log 'rtcWakeup cancel: no verified cancel operation; one pending wake may remain; no fetch after stop'
    fi
}
khd_ready() {
    khd_ready_now=$(khd_now)
    khd_ready_elapsed=unknown
    [ -z "$KHD_SCREENSAVER_SINCE" ] || khd_ready_elapsed=$((khd_ready_now - KHD_SCREENSAVER_SINCE))
    khd_log "readyToSuspend screensaver_elapsed=$khd_ready_elapsed target=$KHD_TARGET_EPOCH"
    khd_read_battery
    if khd_awake && [ "$KHD_POWER_PHASE" = ready ]; then
        khd_log 'readyToSuspend: awake override; arming safety wake (powerd still owns suspend)'
    fi
    # Even if charging, honor a real ready event: do not strand a wake schedule.
    khd_arm_wakeup || khd_log 'rtcWakeup failed: timeout/poll fallback only while CPU runs; timed wake unconfirmed'
    if khd_awake && [ "$KHD_POWER_PHASE" = ready ]; then
        # USB charging normally prevents this transition itself. A debug flag
        # needs an explicit ready-window hold; never hold preventScreenSaver.
        khd_power_set abortSuspend 1
        khd_awake_hold_rc=$?
        khd_log "awake mode: abortSuspend hold rc=$khd_awake_hold_rc (safety wake armed if accepted)"
    fi
    KHD_LAST_READY_EPOCH=$khd_ready_now
}
khd_wake_diagnostics() {
    khd_wake_dmesg=$("$DMESG_BIN" 2>/dev/null)
    khd_dmesg_rc=$?
    khd_wake_tail=$(printf '%s\n' "$khd_wake_dmesg" | grep -Ei 'undefined instruction|ar6003|suspend|PM:' | tail -n 5)
    khd_log "wake dmesg rc=$khd_dmesg_rc last5=[$khd_wake_tail]"
}

# A finite heartbeat aborts only a pending ready transition while work runs.
# This does not hold a persistent flag or use raw kernel suspend. abortSuspend
# behavior is researched on other Kindles; validate the state on this firmware.
khd_guard_start() {
    [ "$KHD_MODE" != --once ] || return 0
    khd_power_snapshot cycle-guard-start
    [ "$KHD_POWER_CLASS" = screensaver ] || return 0
    khd_guard_budget=$(( (WIFI_RETRIES + 1) * (WIFI_TIMEOUT_SECONDS + WIFI_TOGGLE_DELAY_SECONDS) + HTTP_TIMEOUT_SECONDS + WIFI_OFF_REDRAW_DELAY_SECONDS + SCREENSAVER_REDRAW_DELAY_SECONDS + 30 ))
    if [ "$SUSPEND_DEFER_MODE" = deferSuspend ]; then
        khd_log "cycle defer mode=deferSuspend value=$khd_guard_budget (units/state effect require device validation)"
        khd_power_set deferSuspend "$khd_guard_budget" || return 1
        # Never continue drawing/network work if this firmware exits SS.
        [ "$KHD_POWER_CLASS" = screensaver ] || { khd_log 'deferSuspend left screensaver; cycle refused'; return 1; }
    else
        khd_log "cycle defer mode=none abort_guard=$CYCLE_ABORT_SUSPEND budget=$khd_guard_budget"
    fi
    [ "$CYCLE_ABORT_SUSPEND" = 1 ] || return 0
    # Protect immediately if the cycle starts inside the ready window.
    if [ "$KHD_POWER_PHASE" = ready ]; then
        khd_arm_wakeup || :
        [ "$KHD_POWER_CLASS" = screensaver ] || return 1
        if [ "$KHD_POWER_PHASE" = ready ]; then khd_power_set abortSuspend 1 || return 1; fi
    fi
    (
        KHD_CHILD_PID=
        trap 'trap "" HUP INT TERM; khd_cancel_child; exit 0' HUP INT TERM
        trap 'khd_cancel_child' 0
        khd_guard_left=$khd_guard_budget
        while [ "$khd_guard_left" -gt 0 ] && ! khd_stop_requested && khd_kill -0 "$$" 2>/dev/null; do
            "$SLEEP_BIN" 5 &
            khd_wait_child || exit 0
            khd_stop_requested && exit 0
            khd_kill -0 "$$" 2>/dev/null || exit 0
            khd_guard_left=$((khd_guard_left - 5))
            khd_power_snapshot cycle-guard
            [ "$KHD_POWER_CLASS" = screensaver ] || exit 0
            if [ "$KHD_POWER_PHASE" = ready ]; then
                khd_arm_wakeup || :
                [ "$KHD_POWER_CLASS" = screensaver ] || exit 0
                if [ "$KHD_POWER_PHASE" = ready ]; then khd_power_set abortSuspend 1 || exit 0; fi
            fi
        done
        khd_log 'cycle guard expired/stopped; powerd free to suspend'
    ) &
    KHD_GUARD_PID=$!
}
khd_guard_stop() {
    if [ -n "$KHD_GUARD_PID" ]; then
        khd_kill -TERM "$KHD_GUARD_PID" 2>/dev/null || :
        wait "$KHD_GUARD_PID" 2>/dev/null || :
        KHD_GUARD_PID=
        khd_log 'cycle guard released'
    fi
}

khd_run_cycle() {
    khd_stop_requested && return 1
    khd_run_start=$(khd_now)
    khd_shown=0
    if khd_guard_start; then
        if [ "$KHD_INITIAL_CYCLE" = 0 ] && [ "$KHD_MODE" != --once ] && [ "$KHD_POWER_CLASS" != screensaver ]; then
            khd_guard_stop
            khd_log 'cycle paused: state changed before work; target retained'
            return 0
        fi
        if ! khd_cycle; then
            khd_guard_stop
            khd_log 'cycle interrupted: target retained'
            return 0
        fi
    else
        khd_log 'cycle skipped: suspend guard failed'
        KHD_NEXT_SLEEP=$MIN_SLEEP_SECONDS
    fi
    khd_guard_stop
    KHD_TARGET_EPOCH=$(( $(khd_now) + KHD_NEXT_SLEEP ))
    khd_log "cycle complete elapsed=$(( $(khd_now) - khd_run_start )) next_sleep=$KHD_NEXT_SLEEP target=$KHD_TARGET_EPOCH"
    if [ "$khd_shown" = 1 ]; then khd_enter_screensaver || :; fi
    KHD_INITIAL_CYCLE=0
}
khd_run_due() {
    khd_due_now=$(khd_now)
    if [ "$khd_due_now" -ge "$((KHD_TARGET_EPOCH - ${1:-0}))" ]; then
        if [ "$KHD_POWER_CLASS" = screensaver ]; then
            khd_log "scheduled fetch due now=$khd_due_now target=$KHD_TARGET_EPOCH tolerance=${1:-0}"
            khd_run_cycle
        elif [ "$EVENT_LOG_VERBOSE" = 1 ]; then
            khd_log "scheduled fetch paused class=$KHD_POWER_CLASS now=$khd_due_now target=$KHD_TARGET_EPOCH"
        fi
    fi
}
khd_handle_event() {
    khd_log "powerd event raw=[$1]"
    # KOReader's CLI listener parses the name followed by space-separated args.
    # Process every line in case a firmware/version emits more than one.
    while IFS= read -r khd_event_line; do
        khd_event_name=$(printf '%s\n' "$khd_event_line" | awk '{print $1}')
        case $khd_event_name in
            readyToSuspend)
                khd_power_snapshot event-ready
                # The state can change between event delivery and inspection.
                [ "$KHD_POWER_CLASS" != active ] || { khd_log 'stale ready event ignored in active'; continue; }
                khd_ready
                ;;
            wakeupFromSuspend|resuming)
                khd_power_snapshot event-wake-received
                khd_wake_diagnostics
                khd_log "wake settling delay=$RESUME_DELAY_SECONDS event=$khd_event_name"
                khd_pause "$RESUME_DELAY_SECONDS" || return 1
                khd_observe_power event-wake || return 1
                if [ "$KHD_POWER_CLASS" = screensaver ]; then
                    KHD_SCREENSAVER_SINCE=$(khd_now)
                    khd_log "screensaver wake epoch=$KHD_SCREENSAVER_SINCE target=$KHD_TARGET_EPOCH delta=$((KHD_SCREENSAVER_SINCE - KHD_TARGET_EPOCH))"
                    khd_frontlight_zero || :
                    if [ "$WAKE_REDRAW" = 1 ]; then khd_repaint wake || return 1; fi
                fi
                khd_due_now=$(khd_now)
                if [ "$khd_due_now" -lt "$((KHD_TARGET_EPOCH - WAKE_TOLERANCE_SECONDS))" ]; then
                    khd_log "early wake: fetch skipped now=$khd_due_now target=$KHD_TARGET_EPOCH"
                fi
                khd_run_due "$WAKE_TOLERANCE_SECONDS"
                ;;
            '') : ;;
            *) khd_log "unrecognized event/output name=[$khd_event_name]; polling state" ;;
        esac
    done <<EOF
$1
EOF
}
khd_event_wait() {
    KHD_EVENT_TEXT= KHD_EVENT_RC=0
    khd_wait_start=$(khd_now)
    khd_wait_expected=$1
    if command -v "$LIPC_WAIT_BIN" >/dev/null 2>&1; then
        mkdir -p "$TEMP_DIR" || return 1
        khd_event_file=$TEMP_DIR/event.$$
        "$LIPC_WAIT_BIN" -s "$1" com.lab126.powerd readyToSuspend,wakeupFromSuspend,resuming > "$khd_event_file" 2>&1 &
        khd_wait_child
        KHD_EVENT_RC=$?
        KHD_EVENT_TEXT=$(cat "$khd_event_file")
        rm -f "$khd_event_file"
        if [ "$EVENT_LOG_VERBOSE" = 1 ] || [ -n "$KHD_EVENT_TEXT" ]; then
            khd_log "event wait timeout=$1 rc=$KHD_EVENT_RC raw=[$KHD_EVENT_TEXT]"
        fi
    else
        khd_wait_expected=$POLL_INTERVAL_SECONDS
        if [ "$KHD_POLL_NOTICE" = 0 ]; then
            khd_log "lipc-wait-event missing: polling state every $POLL_INTERVAL_SECONDS seconds; ready window/timed wake not guaranteed"
            KHD_POLL_NOTICE=1
        fi
        khd_pause "$POLL_INTERVAL_SECONDS" || return 1
    fi
    KHD_LAST_EVENT_ELAPSED=$(( $(khd_now) - khd_wait_start ))
}
khd_loop_turn() {
    khd_stop_requested && return 1
    khd_read_battery
    khd_observe_power loop || return 1
    if khd_awake; then
        if [ "$KHD_AWAKE_MODE" = 0 ]; then
            khd_log "awake mode entered interval=$AWAKE_INTERVAL_SECONDS"
            khd_wifi_set 1 || :
            khd_awake_target=$(( $(khd_now) + AWAKE_INTERVAL_SECONDS ))
            [ "$KHD_TARGET_EPOCH" -le "$khd_awake_target" ] || KHD_TARGET_EPOCH=$khd_awake_target
        fi
        KHD_AWAKE_MODE=1
    else
        [ "$KHD_AWAKE_MODE" = 0 ] || khd_log 'awake mode ended; powerd manages suspend'
        KHD_AWAKE_MODE=0
    fi
    khd_run_due 0
    # State polling catches a ready event lost while fetching/repainting.
    khd_power_snapshot before-event-wait
    if [ "$KHD_POWER_PHASE" = ready ]; then khd_ready; fi
    khd_wait_seconds=$EVENT_WAIT_SECONDS
    khd_until_target=$((KHD_TARGET_EPOCH - $(khd_now)))
    if [ "$khd_until_target" -gt 0 ] && [ "$khd_until_target" -lt "$khd_wait_seconds" ]; then khd_wait_seconds=$khd_until_target; fi
    khd_event_wait "$khd_wait_seconds" || return 1
    khd_stop_requested && return 1
    if [ "$KHD_LAST_EVENT_ELAPSED" -gt "$((khd_wait_expected + WAKE_TOLERANCE_SECONDS))" ] && [ -z "$KHD_EVENT_TEXT" ]; then
        khd_log "inferred wake: wait_elapsed=$KHD_LAST_EVENT_ELAPSED expected=$khd_wait_expected (suspend or clock correction; no event received)"
        khd_wake_diagnostics
        khd_pause "$RESUME_DELAY_SECONDS" || return 1
        khd_power_snapshot inferred-wake
        if [ "$KHD_POWER_CLASS" = screensaver ]; then
            KHD_SCREENSAVER_SINCE=$(khd_now)
            khd_frontlight_zero || :
            if [ "$WAKE_REDRAW" = 1 ]; then khd_repaint inferred-wake || return 1; fi
        fi
    fi
    [ -z "$KHD_EVENT_TEXT" ] || khd_handle_event "$KHD_EVENT_TEXT" || return 1
    # Both an empty timeout and a failed event command use wall-time fallback.
    khd_observe_power after-event-wait || return 1
    khd_run_due 0
    # Broken CLI tools and event storms must not create a tight loop.
    [ "$KHD_LAST_EVENT_ELAPSED" -ge 1 ] || khd_pause 1 || return 1
}

khd_pid_running() {
    case ${1:-} in ''|*[!0-9]*|0|1) return 1 ;; esac
    khd_kill -0 "$1" 2>/dev/null || return 1
    [ -r "$PROC_ROOT/$1/cmdline" ] || return 1
    tr '\000' '\n' < "$PROC_ROOT/$1/cmdline" | awk -v script="$EXT_DIR/bin/dash.sh" -v diagnostic="$EXT_DIR/bin/selftest.sh" '
        $0 == script || $0 == diagnostic { found=1 } END { exit !found }'
}
khd_find_pid() {
    [ -f "$PIDFILE" ] || return 1
    khd_pid=$(cat "$PIDFILE")
    khd_pid_running "$khd_pid" || return 1
    printf '%s\n' "$khd_pid"
}
khd_claim_pid() {
    mkdir -p "$(dirname "$PIDFILE")" || return 1
    # A live pidfile remains authoritative even if its lock directory vanished.
    khd_find_pid >/dev/null && return 1
    if ! mkdir "$PIDFILE.lock" 2>/dev/null; then
        khd_find_pid >/dev/null && return 1
        # Allow an in-progress launch to publish its PID before stale recovery.
        khd_sleep 1
        khd_find_pid >/dev/null && return 1
        # One stale-lock reaper at a time; recheck the owner after acquiring it.
        mkdir "$PIDFILE.reap" 2>/dev/null || return 1
        if khd_find_pid >/dev/null; then
            rmdir "$PIDFILE.reap"
            return 1
        fi
        rm -f "$PIDFILE"
        rmdir "$PIDFILE.lock" 2>/dev/null || :
        rmdir "$PIDFILE.reap"
        mkdir "$PIDFILE.lock" 2>/dev/null || return 1
    fi
    printf '%s\n' "$$" > "$PIDFILE" || { rmdir "$PIDFILE.lock"; return 1; }
    KHD_OWNS_PID=1
}
khd_release_pid() {
    if [ "$KHD_OWNS_PID" = 1 ] && [ "$(cat "$PIDFILE" 2>/dev/null)" = "$$" ]; then
        rm -f "$PIDFILE"
        rmdir "$PIDFILE.lock" 2>/dev/null || :
    fi
    KHD_OWNS_PID=0
}
khd_prepare_ui() {
    if [ "$STOP_FRAMEWORK" = 1 ] && [ "$KHD_MODE" != --once ]; then
        khd_log 'startup refused: powerd screensaver mode requires STOP_FRAMEWORK=0'
        return 1
    fi
    khd_power_set preventScreenSaver 0 || return 1
    khd_frontlight_start || khd_log 'frontlight setup failed (see preceding diagnostic)'
    if [ "$STOP_FRAMEWORK" = 1 ]; then
        mkdir -p "$(dirname "$FRAMEWORK_MARKER")" || return 1
        # Record BEFORE stop, so a crash or TERM cannot lose restoration state.
        for khd_job in $FRAMEWORK_JOBS; do
            printf '%s\n' "$khd_job" >> "$FRAMEWORK_MARKER" || return 1
            khd_stop_job "$khd_job" >/dev/null 2>&1 || khd_log "job stop failed: $khd_job"
        done
    fi
}
khd_restore_ui() {
    khd_guard_stop
    khd_cancel_wakeup
    khd_wifi_set 1 || :
    khd_frontlight_restore || :
    khd_power_set preventScreenSaver 0 || khd_log 'preventScreenSaver restore failed'
    if [ -f "$FRAMEWORK_MARKER" ]; then
        # The file is generated by us, but never execute its contents.
        while IFS= read -r khd_restore_job; do
            case $khd_restore_job in ''|*[!a-zA-Z0-9_-]*) continue ;; esac
            khd_start_job "$khd_restore_job" >/dev/null 2>&1 || khd_log "job start failed: $khd_restore_job"
        done < "$FRAMEWORK_MARKER"
        rm -f "$FRAMEWORK_MARKER"
    fi
}
khd_cleanup() {
    trap '' HUP INT TERM
    khd_cancel_child
    khd_restore_ui
    rm -f "$TEMP_DIR/fetch.$$.headers" "$TEMP_DIR/fetch.$$.png" "$TEMP_DIR/fetch.$$.code" "$TEMP_DIR/event.$$"
    khd_release_pid
    khd_log 'dashboard stopped; wifi/UI restoration requested'
}
khd_cancel_child() {
    if [ -n "$KHD_CHILD_PID" ]; then
        khd_kill -TERM "$KHD_CHILD_PID" 2>/dev/null || :
        wait "$KHD_CHILD_PID" 2>/dev/null || :
        KHD_CHILD_PID=
    fi
}
