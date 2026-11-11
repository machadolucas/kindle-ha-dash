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
    : "${RTC_ROOT:=/sys/class/rtc}" "${POWER_STATE_PATH:=/sys/power/state}"
    : "${PIDFILE:=$STATE_DIR/dash.pid}" "${TEMP_DIR:=$STATE_DIR/work}"
    : "${IMAGE_FILE:=$STATE_DIR/image.png}"
    : "${FRAMEWORK_MARKER:=$STATE_DIR/framework-stopped}"
    : "${DEBUG_FILE:=/mnt/us/kindle-ha-dash.debug}"
    : "${STOP_FILE:=/mnt/us/kindle-ha-dash.stop}"
    : "${LOG_FILE:=$EXT_DIR/dashboard.log}" "${LOG_MAX_BYTES:=131072}"
    : "${LIPC_SET_BIN:=lipc-set-prop}" "${LIPC_GET_BIN:=lipc-get-prop}"
    : "${GASGAUGE_BIN:=gasgauge-info}" "${EIPS_BIN:=eips}"
    : "${USB_POWER_PATH:=/sys/devices/system/wario_charger/wario_charger0/connected}"
    : "${CHARGING_PATH:=/sys/devices/system/wario_charger/wario_charger0/charging}"
    : "${START_BIN:=start}" "${STOP_BIN:=stop}" "${SLEEP_BIN:=sleep}"
    : "${DATE_BIN:=date}" "${KILL_BIN:=kill}"
    : "${EIPS_STATUS_COL:=0}" "${EIPS_STATUS_ROW:=auto}"
    : "${FRAMEWORK_JOBS:=framework lab126_gui}"
    if [ -z "${RTC_DEVICE:-}" ]; then
        if [ -e "$RTC_ROOT/rtc1/wakealarm" ]; then
            RTC_DEVICE=$RTC_ROOT/rtc1
        else
            RTC_DEVICE=$RTC_ROOT/rtc0
        fi
    fi
    if [ -z "${HTTP_CLIENT_BIN:-}" ]; then
        HTTP_CLIENT_BIN=$(khd_find_tool "$EXT_DIR/bin/curl" /mnt/us/usbnet/bin/curl curl) || HTTP_CLIENT_BIN=
    fi
    if [ "${FBINK_BIN:-auto}" = auto ]; then
        FBINK_BIN=$(khd_find_tool fbink /mnt/us/libkh/bin/fbink /mnt/us/koreader/fbink /mnt/us/koreader/bin/fbink) || FBINK_BIN=
    fi
    KHD_BATTERY= KHD_CHARGING=0 KHD_USB_POWERED=0 KHD_CHILD_PID= KHD_OWNS_PID=0
    KHD_WIFI_OFF=0 KHD_HEADER_SLEEP= KHD_FULL_REFRESH=0
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
    for khd_setting in FALLBACK_SLEEP_SECONDS MIN_SLEEP_SECONDS MAX_SLEEP_SECONDS AWAKE_INTERVAL_SECONDS WIFI_TIMEOUT_SECONDS WIFI_RETRIES HTTP_TIMEOUT_SECONDS LOW_BATTERY_PERCENT LOG_MAX_BYTES RESUME_DELAY_SECONDS WIFI_TOGGLE_DELAY_SECONDS; do
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
        [ "$LOG_MAX_BYTES" -ge 1024 ] || {
        printf '%s\n' 'Invalid configuration limits (see config.sh.example).' >&2
        return 1
    }
    case $STOP_FRAMEWORK:$INSECURE_TLS in 0:0|0:1|1:0|1:1) ;; *) return 1 ;; esac
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
khd_write_node() { printf '%s\n' "$2" > "$1"; }
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
        khd_sleep "$khd_pause_slice" &
        khd_wait_child || return 1
        khd_pause_left=$((khd_pause_left - khd_pause_slice))
    done
}

khd_wifi_set() {
    if khd_lipc_set com.lab126.cmd wirelessEnable "$1" >/dev/null 2>&1; then
        if [ "$1" = 0 ]; then KHD_WIFI_OFF=1; else KHD_WIFI_OFF=0; fi
        return 0
    fi
    KHD_WIFI_OFF=0
    khd_log "wifi command failed (requested=$1)"
    return 1
}
khd_wifi_state() { khd_lipc_get com.lab126.wifid cmState 2>/dev/null | tr -d '\r\n'; }
khd_wifi_connect() {
    khd_wifi_attempt=0
    while [ "$khd_wifi_attempt" -le "$WIFI_RETRIES" ]; do
        khd_stop_requested && return 1
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
            [ "$(khd_wifi_state)" = CONNECTED ] && return 0
            khd_pause 1 || return 1
            khd_wifi_waited=$((khd_wifi_waited + 1))
        done
        khd_wifi_attempt=$((khd_wifi_attempt + 1))
    done
    khd_log 'wifi connection timeout'
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
    khd_read_battery
    khd_log "wake battery=${KHD_BATTERY:-unknown} charging=$KHD_CHARGING usb_power=$KHD_USB_POWERED"
    KHD_HEADER_SLEEP= KHD_FULL_REFRESH=0 khd_shown=0
    if khd_low_battery; then
        khd_log 'low battery: fetch skipped'
        khd_status 'battery low, please charge'
        KHD_NEXT_SLEEP=$MAX_SLEEP_SECONDS
    else
        if khd_wifi_connect && khd_fetch; then
            if khd_display; then khd_shown=1; else khd_log 'display failed'; khd_status "display failed $(khd_date +%H:%M)"; fi
        else
            khd_status "no connection $(khd_date +%H:%M)"
        fi
        KHD_NEXT_SLEEP=$(khd_sleep_seconds "$KHD_HEADER_SLEEP")
    fi
    # Recheck power/debug after a possibly long request.
    khd_read_battery
    if khd_awake; then
        khd_wifi_set 1 || :
        [ "$KHD_NEXT_SLEEP" -le "$AWAKE_INTERVAL_SECONDS" ] || KHD_NEXT_SLEEP=$AWAKE_INTERVAL_SECONDS
        khd_log "awake mode interval=$KHD_NEXT_SLEEP"
    else
        khd_wifi_set 0 || :
        # The stock UI paints an airplane-mode icon over our image when wifi
        # goes off; wait for it, then repaint (partial refresh, no flash).
        if [ "$khd_shown" = 1 ] && [ "${WIFI_OFF_REDRAW_DELAY_SECONDS:-3}" -gt 0 ]; then
            khd_sleep "${WIFI_OFF_REDRAW_DELAY_SECONDS:-3}"
            KHD_FULL_REFRESH=0
            khd_display || :
        fi
    fi
}

khd_clear_alarm() {
    [ -e "$RTC_DEVICE/wakealarm" ] || return 1
    khd_write_node "$RTC_DEVICE/wakealarm" 0 2>/dev/null
}
khd_arm_alarm() {
    khd_alarm_epoch=$(( $(khd_now) + $1 ))
    khd_clear_alarm && khd_write_node "$RTC_DEVICE/wakealarm" "$khd_alarm_epoch" 2>/dev/null || return 1
    khd_alarm_read=$(khd_read_node "$RTC_DEVICE/wakealarm" 2>/dev/null | tr -d ' \r\n\t')
    [ "$khd_alarm_read" = "$khd_alarm_epoch" ]
}
khd_sleep_cycle() {
    khd_sleep_target=$1
    khd_sleep_start=$(khd_clock)
    khd_read_battery
    if khd_awake; then
        khd_wifi_set 1 || :
        [ "$khd_sleep_target" -le "$AWAKE_INTERVAL_SECONDS" ] || khd_sleep_target=$AWAKE_INTERVAL_SECONDS
        khd_pause "$khd_sleep_target" || return 1
    else
        # A failed wirelessDisable prohibits suspend, even with a valid alarm.
        if [ "$KHD_WIFI_OFF" = 1 ] && khd_wifi_set 0 && khd_arm_alarm "$khd_sleep_target"; then
            khd_log "suspend requested seconds=$khd_sleep_target alarm=$khd_alarm_epoch rtc=$RTC_DEVICE"
            khd_stop_requested && { khd_clear_alarm || :; return 1; }
            khd_read_battery
            # Deliberately separate from the RTC programming step. Never rtcwake.
            if khd_awake; then
                khd_log 'awake override appeared after RTC programming; canceling suspend'
            elif ! khd_write_node "$POWER_STATE_PATH" mem 2>/dev/null; then
                khd_log 'suspend write failed; sleeping remainder'
            fi
            khd_sleep_elapsed=$(( $(khd_clock) - khd_sleep_start ))
            [ "$khd_sleep_elapsed" -ge 0 ] || khd_sleep_elapsed=0
            khd_log "resume elapsed=$khd_sleep_elapsed requested=$khd_sleep_target drift=$((khd_sleep_elapsed - khd_sleep_target))"
            khd_clear_alarm || :
            khd_pause "$RESUME_DELAY_SECONDS" || return 1
        else
            khd_log 'suspend unavailable (wifi-off/RTC verification); sleeping remainder'
            khd_clear_alarm || :
        fi
        khd_sleep_elapsed=$(( $(khd_clock) - khd_sleep_start ))
        [ "$khd_sleep_elapsed" -ge 0 ] || khd_sleep_elapsed=0
        khd_sleep_remaining=$((khd_sleep_target - khd_sleep_elapsed))
        khd_read_battery
        if khd_awake; then
            khd_wifi_set 1 || :
            [ "$khd_sleep_remaining" -le "$AWAKE_INTERVAL_SECONDS" ] || khd_sleep_remaining=$AWAKE_INTERVAL_SECONDS
        fi
        [ "$khd_sleep_remaining" -le 0 ] || khd_pause "$khd_sleep_remaining" || return 1
    fi
    khd_log "sleep complete elapsed=$(( $(khd_clock) - khd_sleep_start )) requested=$khd_sleep_target"
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
    khd_lipc_set com.lab126.powerd preventScreenSaver 1 >/dev/null 2>&1 || khd_log 'preventScreenSaver failed'
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
    khd_clear_alarm || khd_log 'restore: RTC clear failed or wakealarm unavailable'
    khd_wifi_set 1 || :
    khd_lipc_set com.lab126.powerd preventScreenSaver 0 >/dev/null 2>&1 || khd_log 'preventScreenSaver restore failed'
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
    rm -f "$TEMP_DIR/fetch.$$.headers" "$TEMP_DIR/fetch.$$.png" "$TEMP_DIR/fetch.$$.code"
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
