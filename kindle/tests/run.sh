#!/bin/sh
# Host-side tests for kindle-ha-dash/bin/lib.sh. Safe to run without a Kindle.
set -u

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
LIB="$SCRIPT_DIR/../extensions/kindle-ha-dash/bin/lib.sh"
if [ ! -f "$LIB" ]; then
    echo "missing client library: $LIB" >&2
    exit 2
fi

TMP_BASE=${TMPDIR:-/tmp}
TEST_TMP=$(mktemp -d "$TMP_BASE/khd-tests.XXXXXX") || exit 2
cleanup() { rm -rf "$TEST_TMP"; }
trap cleanup 0
trap 'exit 1' HUP INT TERM

mkdir -p "$TEST_TMP/bin" "$TEST_TMP/proc"
cat >"$TEST_TMP/bin/curl" <<'EOF'
#!/bin/sh
header_file=
body_file=
http_code=${FAKE_HTTP_CODE:-200}
while [ "$#" -gt 0 ]; do
    case $1 in
        -D) shift; header_file=${1-} ;;
        -o) shift; body_file=${1-} ;;
        -w) shift ;;
    esac
    shift
done
[ -n "$header_file" ] && [ -n "$body_file" ] || exit 90
printf '%s\n' called >>"$FAKE_CURL_LOG"
cp "$FAKE_HEADERS" "$header_file" || exit 91
cp "$FAKE_BODY" "$body_file" || exit 92
printf '%s' "$http_code"
exit "${FAKE_CURL_EXIT:-0}"
EOF
cat >"$TEST_TMP/bin/eips" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$FAKE_EIPS_LOG"
EOF
cat >"$TEST_TMP/bin/lipc-set-prop" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$FAKE_LIPC_SET_LOG"
[ "${1-}" != -i ] || shift
[ "${2-}" != "${FAKE_FAIL_PROPERTY:-}" ] || exit 17
case ${2-} in
    flIntensity) printf '%s\n' "${3-}" >"$FAKE_FRONTLIGHT_FILE" ;;
    deferSuspend)
        [ "${FAKE_DEFER_ACTIVE:-0}" != 1 ] || printf 'active\n' >"$FAKE_POWER_STATE_FILE"
        ;;
    powerButton)
        [ "${FAKE_POWER_BUTTON_RC:-0}" -eq 0 ] || exit "$FAKE_POWER_BUTTON_RC"
        [ -z "${FAKE_POWER_STATE_FILE:-}" ] || printf 'screenSaver\n' >"$FAKE_POWER_STATE_FILE"
        ;;
esac
EOF
cat >"$TEST_TMP/bin/lipc-get-prop" <<'EOF'
#!/bin/sh
case ${2-} in
    state) [ -z "${FAKE_POWER_STATE_FILE:-}" ] || cat "$FAKE_POWER_STATE_FILE" ;;
    status) printf '%s\n' "${FAKE_POWER_STATUS:-Screen Saver}" ;;
    flIntensity) cat "$FAKE_FRONTLIGHT_FILE" ;;
    isCharging) printf '%s\n' "${FAKE_CHARGING:-0}" ;;
    cmState)
        if [ -n "${FAKE_WIFI_STATE_SEQUENCE:-}" ]; then
            wifi_index=$(cat "$FAKE_WIFI_STATE_COUNT" 2>/dev/null || printf '0')
            wifi_index=$((wifi_index + 1))
            printf '%s\n' "$wifi_index" >"$FAKE_WIFI_STATE_COUNT"
            sed -n "${wifi_index}p" "$FAKE_WIFI_STATE_SEQUENCE"
        else
            printf '%s\n' "${FAKE_WIFI_STATE:-}"
        fi
        ;;
esac
EOF
cat >"$TEST_TMP/bin/gasgauge-info" <<'EOF'
#!/bin/sh
printf '%s\n' "${FAKE_GASGAUGE_OUTPUT:-Battery level: 77%}"
EOF
cat >"$TEST_TMP/bin/kill" <<'EOF'
#!/bin/sh
case ${1-} in
    -0) [ "${2-}" = "${FAKE_LIVE_PID:-}" ] ;;
    *) exit 2 ;;
esac
EOF
cat >"$TEST_TMP/bin/sleep" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$FAKE_SLEEP_LOG"
if [ -n "${FAKE_SLEEP_EVENT_FILE:-}" ]; then printf 'sleep:%s\n' "$1" >>"$FAKE_SLEEP_EVENT_FILE"; fi
if [ -n "${FAKE_SLEEP_WAKE_FILE:-}" ]; then : >"$FAKE_SLEEP_WAKE_FILE"; fi
if [ -n "${FAKE_SLEEP_POWER_STATE:-}" ]; then printf '%s\n' "$FAKE_SLEEP_POWER_STATE" >"$FAKE_POWER_STATE_FILE"; fi
if [ "${FAKE_SLEEP_ADVANCE:-0}" = 1 ]; then
    clock=$(cat "$FAKE_CLOCK_FILE")
    advance=${FAKE_SLEEP_ADVANCE_VALUE:-$1}
    printf '%s\n' "$((clock + advance))" >"$FAKE_CLOCK_FILE"
fi
EOF
cat >"$TEST_TMP/bin/lipc-wait-event" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$FAKE_EVENT_LOG"
if [ -n "${FAKE_EVENT_CLOCK:-}" ]; then printf '%s\n' "$FAKE_EVENT_CLOCK" >"$FAKE_CLOCK_FILE"; fi
printf '%s\n' "${FAKE_EVENT_TEXT:-}"
exit "${FAKE_EVENT_RC:-0}"
EOF
cat >"$TEST_TMP/bin/powerd_test" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$FAKE_POWERD_LOG"
case ${1-} in
    -s) printf '%s\n' "${FAKE_POWER_STATUS:-Screen Saver}" ;;
    -p) printf 'screenSaver\n' >"$FAKE_POWER_STATE_FILE" ;;
esac
EOF
cat >"$TEST_TMP/bin/guard-sleep" <<'EOF'
#!/bin/sh
printf '%s\n' "$$" >>"$FAKE_GUARD_SLEEP_PIDS"
exec /bin/sleep "$@"
EOF
cat >"$TEST_TMP/bin/date" <<'EOF'
#!/bin/sh
case ${1-} in
    +%s) cat "$FAKE_CLOCK_FILE" ;;
    *) printf '2026-11-11T12:00:00+0000\n' ;;
esac
EOF
cat >"$TEST_TMP/bin/dmesg" <<'EOF'
#!/bin/sh
printf 'PM: simulated powerd wake diagnostic\n'
EOF
chmod +x "$TEST_TMP/bin/"*

export PATH="$TEST_TMP/bin:$PATH"
export FAKE_CURL_LOG="$TEST_TMP/curl.log" FAKE_EIPS_LOG="$TEST_TMP/eips.log"
export FAKE_LIPC_SET_LOG="$TEST_TMP/lipc-set.log"
export FAKE_SLEEP_LOG="$TEST_TMP/sleep.log"
export FAKE_FRONTLIGHT_FILE="$TEST_TMP/frontlight"
export FAKE_POWER_STATE_FILE="$TEST_TMP/power-state"
export FAKE_EVENT_LOG="$TEST_TMP/event.log" FAKE_POWERD_LOG="$TEST_TMP/powerd.log"
export FAKE_CLOCK_FILE="$TEST_TMP/clock"
printf '100\n' >"$FAKE_CLOCK_FILE"
printf 'screenSaver\n' >"$FAKE_POWER_STATE_FILE"
printf '12\n' >"$FAKE_FRONTLIGHT_FILE"
export FAKE_HEADERS="$TEST_TMP/headers" FAKE_BODY="$TEST_TMP/body"
export FAKE_LIVE_PID="$$"

# shellcheck source=../extensions/kindle-ha-dash/bin/lib.sh
. "$LIB"

EXT_DIR="$TEST_TMP/ext"
mkdir -p "$EXT_DIR/bin"
khd_init "$EXT_DIR"

TEMP_DIR="$TEST_TMP/work"
mkdir -p "$TEMP_DIR" "$TEST_TMP/proc/$$"
IMAGE_FILE="$TEMP_DIR/image.png"
PIDFILE="$TEMP_DIR/client.pid"
LOG_FILE="$TEMP_DIR/client.log"
DEBUG_FILE="$TEMP_DIR/debug.log"
STOP_FILE="$TEMP_DIR/stop"
LIPC_SET_BIN="$TEST_TMP/bin/lipc-set-prop"
LIPC_GET_BIN="$TEST_TMP/bin/lipc-get-prop"
GASGAUGE_BIN="$TEST_TMP/bin/gasgauge-info"
EIPS_BIN="$TEST_TMP/bin/eips"
FBINK_BIN=
HTTP_CLIENT_BIN="$TEST_TMP/bin/curl"
KILL_BIN="$TEST_TMP/bin/kill"
SLEEP_BIN="$TEST_TMP/bin/sleep"
PROC_ROOT="$TEST_TMP/proc"
USB_POWER_PATH="$TEMP_DIR/usb-powered"
CHARGING_PATH="$TEMP_DIR/charging"
printf '0\n' >"$USB_POWER_PATH"
printf '0\n' >"$CHARGING_PATH"
BASE_URL='https://example.invalid'
TOKEN='test_token'
printf '%s\000' "$EXT_DIR/bin/dash.sh" >"$PROC_ROOT/$$/cmdline"

PASS=0
FAIL=0
check() {
    label=$1
    if [ "$2" = "$3" ]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        printf 'FAIL: %s (expected <%s>, got <%s>)\n' "$label" "$3" "$2" >&2
    fi
}
has_event() { grep -F -- "$2" "$1" >/dev/null 2>&1; }

printf 'HTTP/1.1 302 Found\r\nx-sleep-seconds: 12\r\nx-full-refresh: 1\r\nHTTP/2 200\r\ncontent-type: image/png\r\nx-sleep-seconds: 00045\r\nx-full-refresh: invalid\r\n\r\n' >"$FAKE_HEADERS"
khd_parse_headers "$FAKE_HEADERS"
check 'header sleep' "${KHD_HEADER_SLEEP-}" 00045
check 'invalid full-refresh defaults off' "${KHD_FULL_REFRESH-}" 0
printf 'HTTP/1.1 302 Found\r\nx-sleep-seconds: 23\r\nx-full-refresh: 1\r\nHTTP/2 200\r\ncontent-type: image/png\r\n\r\n' >"$FAKE_HEADERS"
khd_parse_headers "$FAKE_HEADERS"
check 'final header block clears prior sleep' "${KHD_HEADER_SLEEP-}" ''
check 'final header block clears prior refresh' "${KHD_FULL_REFRESH-}" 0

MIN_SLEEP_SECONDS=10 MAX_SLEEP_SECONDS=300 FALLBACK_SLEEP_SECONDS=60
check 'sleep normalizes leading zeroes' "$(khd_sleep_seconds 00042)" 42
check 'sleep clamps low' "$(khd_sleep_seconds 1)" 10
check 'sleep clamps high' "$(khd_sleep_seconds 999999999)" 300
check 'sleep clamps arbitrarily large decimal' "$(khd_sleep_seconds 999999999999999999999999999999)" 300
check 'long leading zero sleep remains valid' "$(khd_sleep_seconds 00000000000000000000000000000042)" 42
check 'sleep fallback for invalid input' "$(khd_sleep_seconds 1x)" 60
check 'sleep fallback for missing input' "$(khd_sleep_seconds '')" 60

printf '\211PNG\r\n\032\ntrailer' >"$TEST_TMP/png"
printf '\211PNG\r\n\032' >"$TEST_TMP/truncated"
printf 'not a png' >"$TEST_TMP/not-png"
if khd_png_valid "$TEST_TMP/png"; then a=1; else a=0; fi
check 'PNG signature accepted' "$a" 1
if khd_png_valid "$TEST_TMP/truncated"; then a=1; else a=0; fi
check 'truncated PNG rejected' "$a" 0
if khd_png_valid "$TEST_TMP/not-png"; then a=1; else a=0; fi
check 'wrong PNG signature rejected' "$a" 0

# Display refresh flags select distinct eips command sequences.
cp "$TEST_TMP/png" "$IMAGE_FILE"
printf 'HTTP/1.1 200 OK\r\nx-full-refresh: 1\r\n\r\n' >"$FAKE_HEADERS"
khd_parse_headers "$FAKE_HEADERS"
check 'valid full-refresh header enables refresh' "$KHD_FULL_REFRESH" 1
: >"$FAKE_EIPS_LOG"
if khd_display; then a=1; else a=0; fi
check 'full refresh display succeeds' "$a" 1
check 'full refresh clears display first' "$(sed -n '1p' "$FAKE_EIPS_LOG")" '-c'
check 'full refresh uses forced image draw' "$(sed -n '2p' "$FAKE_EIPS_LOG")" "-f -g $IMAGE_FILE"
: >"$FAKE_EIPS_LOG"
KHD_FULL_REFRESH=0
if khd_display; then a=1; else a=0; fi
check 'partial refresh display succeeds' "$a" 1
check 'partial refresh draws without clear' "$(cat "$FAKE_EIPS_LOG")" "-g $IMAGE_FILE"

check 'URL encoding escapes reserved characters' "$(printf '%s' 'a/b?c#d &%' | khd_urlencode)" '%61%2F%62%3F%63%23%64%20%26%25'

cp "$TEST_TMP/png" "$FAKE_BODY"
printf 'HTTP/1.1 200 OK\r\n\r\n' >"$FAKE_HEADERS"
cp "$FAKE_BODY" "$IMAGE_FILE"
if khd_fetch; then a=1; else a=0; fi
check 'fetch succeeds for HTTP 200 PNG' "$a" 1
check 'fetch invokes curl stub' "$(wc -l <"$FAKE_CURL_LOG" | tr -d ' ')" 1
cp "$IMAGE_FILE" "$TEST_TMP/image.before"
printf 'HTTP/1.1 200 OK\r\n\r\n' >"$FAKE_HEADERS"
printf 'bad image' >"$FAKE_BODY"
if khd_fetch; then a=1; else a=0; fi
check 'fetch rejects non-PNG body' "$a" 0
cmp -s "$IMAGE_FILE" "$TEST_TMP/image.before"; if [ $? -eq 0 ]; then a=1; else a=0; fi
check 'failed fetch preserves prior image' "$a" 1

FAKE_GASGAUGE_OUTPUT='15%'
export FAKE_GASGAUGE_OUTPUT
khd_read_battery
check 'battery percentage parsed' "${KHD_BATTERY-}" 15
check 'charging defaults to zero' "${KHD_CHARGING-}" 0
LOW_BATTERY_PERCENT=20
if khd_low_battery; then a=1; else a=0; fi
check 'low battery detected' "$a" 1
FAKE_GASGAUGE_OUTPUT='80%'
khd_read_battery
if khd_low_battery; then a=1; else a=0; fi
check 'healthy battery not low' "$a" 0

GASGAUGE_BIN="$TEST_TMP/bin/missing-gasgauge"
khd_read_battery
check 'missing gasgauge yields unknown battery' "${KHD_BATTERY-}" ''
GASGAUGE_BIN="$TEST_TMP/bin/gasgauge-info"

# Charging and the debug marker both override low-battery sleep behavior.
FAKE_GASGAUGE_OUTPUT='5%'
FAKE_CHARGING=1
FAKE_WIFI_STATE=CONNECTED
export FAKE_GASGAUGE_OUTPUT FAKE_CHARGING FAKE_WIFI_STATE
khd_read_battery
if khd_low_battery; then a=1; else a=0; fi
check 'charging overrides low battery' "$a" 0
AWAKE_INTERVAL_SECONDS=7
printf '\211PNG\r\n\032\nawake-cycle' >"$FAKE_BODY"
before=$(wc -l <"$FAKE_CURL_LOG" | tr -d ' ')
khd_cycle
after=$(wc -l <"$FAKE_CURL_LOG" | tr -d ' ')
check 'charging low battery cycle fetches' "$after" "$((before + 1))"
check 'charging cycle caps awake interval' "$KHD_NEXT_SLEEP" 7

FAKE_CHARGING=0
export FAKE_CHARGING
: >"$DEBUG_FILE"
khd_cycle
check 'debug marker caps awake interval' "$KHD_NEXT_SLEEP" 7
rm -f "$DEBUG_FILE"

# A disconnected first attempt is retried and the simulated next state connects.
: >"$FAKE_LIPC_SET_LOG"
: >"$FAKE_SLEEP_LOG"
printf 'DISCONNECTED\nCONNECTED\n' >"$TEST_TMP/wifi-sequence"
: >"$TEST_TMP/wifi-sequence-count"
FAKE_WIFI_STATE_SEQUENCE="$TEST_TMP/wifi-sequence"
FAKE_WIFI_STATE_COUNT="$TEST_TMP/wifi-sequence-count"
export FAKE_WIFI_STATE_SEQUENCE FAKE_WIFI_STATE_COUNT
FAKE_GASGAUGE_OUTPUT='50%'
FAKE_CHARGING=0
export FAKE_GASGAUGE_OUTPUT FAKE_CHARGING
WIFI_RETRIES=1 WIFI_TIMEOUT_SECONDS=1 WIFI_TOGGLE_DELAY_SECONDS=2
KHD_BATTERY=50 KHD_CHARGING=0 KHD_USB_POWERED=0 KHD_WIFI_OFF=0
if khd_wifi_connect; then a=1; else a=0; fi
check 'Wi-Fi reconnect succeeds after retry' "$a" 1
if grep -q 'wirelessEnable 0' "$FAKE_LIPC_SET_LOG" && grep -q 'wirelessEnable 1' "$FAKE_LIPC_SET_LOG"; then a=1; else a=0; fi
check 'Wi-Fi retry toggles radio off then on' "$a" 1
check 'Wi-Fi retry uses stubbed sleep' "$(wc -l <"$FAKE_SLEEP_LOG" | tr -d ' ')" 2
unset FAKE_WIFI_STATE_SEQUENCE FAKE_WIFI_STATE_COUNT
WIFI_RETRIES=2 WIFI_TIMEOUT_SECONDS=30 WIFI_TOGGLE_DELAY_SECONDS=2

# A low-battery cycle renders status without making a network request.
FAKE_GASGAUGE_OUTPUT='5%'
export FAKE_GASGAUGE_OUTPUT
before=$(wc -l <"$FAKE_CURL_LOG" | tr -d ' ')
khd_cycle
after=$(wc -l <"$FAKE_CURL_LOG" | tr -d ' ')
check 'low battery cycle skips curl' "$after" "$before"
check 'low battery cycle uses max sleep' "$KHD_NEXT_SLEEP" "$MAX_SLEEP_SECONDS"
[ -s "$FAKE_EIPS_LOG" ]; if [ $? -eq 0 ]; then a=1; else a=0; fi
check 'status path invokes eips stub' "$a" 1

# A non-200 result must leave a previously valid image untouched.
cp "$TEST_TMP/png" "$FAKE_BODY"
FAKE_HTTP_CODE=503
export FAKE_HTTP_CODE
cp "$IMAGE_FILE" "$TEST_TMP/image.before-503"
if khd_fetch; then a=1; else a=0; fi
check 'fetch rejects non-200 status' "$a" 0
cmp -s "$IMAGE_FILE" "$TEST_TMP/image.before-503"; if [ $? -eq 0 ]; then a=1; else a=0; fi
check 'non-200 fetch preserves prior image' "$a" 1
unset FAKE_HTTP_CODE

# Transport and TLS errors also preserve a previously valid image.
cp "$TEST_TMP/png" "$FAKE_BODY"
cp "$IMAGE_FILE" "$TEST_TMP/image.before-transport"
FAKE_CURL_EXIT=28
export FAKE_CURL_EXIT
if khd_fetch; then a=1; else a=0; fi
check 'transport failure rejected' "$a" 0
cmp -s "$IMAGE_FILE" "$TEST_TMP/image.before-transport"; if [ $? -eq 0 ]; then a=1; else a=0; fi
check 'transport failure preserves prior image' "$a" 1
FAKE_CURL_EXIT=60
export FAKE_CURL_EXIT
if khd_fetch; then a=1; else a=0; fi
check 'TLS failure rejected' "$a" 0
cmp -s "$IMAGE_FILE" "$TEST_TMP/image.before-transport"; if [ $? -eq 0 ]; then a=1; else a=0; fi
check 'TLS failure preserves prior image' "$a" 1
unset FAKE_CURL_EXIT

# The token is present in the request URL but must never reach application logs.
if grep -q 'test_token' "$LOG_FILE"; then a=1; else a=0; fi
check 'HTTP token omitted from logs' "$a" 0

# Log size rollover keeps the previous file as .old.
saved_log=$LOG_FILE
saved_log_max=$LOG_MAX_BYTES
LOG_FILE="$TEMP_DIR/rotate.log"
LOG_MAX_BYTES=10
printf 'previous entry is large\n' >"$LOG_FILE"
khd_log 'new entry'
check 'log rotation retains old content' "$(cat "$LOG_FILE.old")" 'previous entry is large'
if grep -q 'new entry' "$LOG_FILE"; then a=1; else a=0; fi
check 'log rotation writes fresh log' "$a" 1
LOG_FILE=$saved_log
LOG_MAX_BYTES=$saved_log_max

# Powerd owns suspend. A deterministic wall clock and stub event source let
# these cases exercise the real deadline, state and event functions off-device.
run_power_case() {
    power_case=$1
    (
        case_dir="$TEST_TMP/powerd-$power_case"
        mkdir -p "$case_dir/ext/bin" "$case_dir/state/work"
        EXT_DIR="$case_dir/ext"
        STATE_DIR="$case_dir/state"
        TEMP_DIR="$STATE_DIR/work"
        IMAGE_FILE="$STATE_DIR/image.png"
        PIDFILE="$STATE_DIR/dash.pid"
        LOG_FILE="$case_dir/client.log"
        STOP_FILE="$case_dir/stop"
        DEBUG_FILE="$case_dir/debug"
        FRAMEWORK_MARKER="$STATE_DIR/framework-stopped"
        FRONTLIGHT_STATE_FILE="$EXT_DIR/frontlight-state"
        FAKE_CURL_LOG="$case_dir/curl.log"
        FAKE_EIPS_LOG="$case_dir/eips.log"
        FAKE_LIPC_SET_LOG="$case_dir/lipc-set.log"
        FAKE_SLEEP_LOG="$case_dir/sleep.log"
        FAKE_EVENT_LOG="$case_dir/events.log"
        FAKE_POWERD_LOG="$case_dir/powerd.log"
        FAKE_CLOCK_FILE="$case_dir/clock"
        FAKE_FRONTLIGHT_FILE="$case_dir/frontlight"
        FAKE_POWER_STATE_FILE="$case_dir/power-state"
        export FAKE_CURL_LOG FAKE_EIPS_LOG FAKE_LIPC_SET_LOG FAKE_SLEEP_LOG
        export FAKE_EVENT_LOG FAKE_POWERD_LOG FAKE_CLOCK_FILE FAKE_FRONTLIGHT_FILE FAKE_POWER_STATE_FILE
        FAKE_GASGAUGE_OUTPUT='50%' FAKE_CHARGING=0 FAKE_WIFI_STATE=CONNECTED
        export FAKE_GASGAUGE_OUTPUT FAKE_CHARGING FAKE_WIFI_STATE
        printf '100\n' >"$FAKE_CLOCK_FILE"
        printf 'screenSaver\n' >"$FAKE_POWER_STATE_FILE"
        printf '12\n' >"$FAKE_FRONTLIGHT_FILE"
        : >"$FAKE_CURL_LOG"; : >"$FAKE_EIPS_LOG"; : >"$FAKE_LIPC_SET_LOG"
        : >"$FAKE_EVENT_LOG"; : >"$FAKE_POWERD_LOG"; : >"$FAKE_SLEEP_LOG"
        cp "$TEST_TMP/png" "$IMAGE_FILE"
        cp "$TEST_TMP/png" "$FAKE_BODY"
        printf 'HTTP/1.1 200 OK\r\nx-sleep-seconds: 60\r\n\r\n' >"$FAKE_HEADERS"
        LIPC_WAIT_BIN="$TEST_TMP/bin/lipc-wait-event"
        POWERD_TEST_BIN="$TEST_TMP/bin/powerd_test"
        DMESG_BIN="$TEST_TMP/bin/dmesg"
        DATE_BIN="$TEST_TMP/bin/date"
        MIN_SLEEP_SECONDS=10 MAX_SLEEP_SECONDS=300 FALLBACK_SLEEP_SECONDS=60
        WIFI_OFF_REDRAW_DELAY_SECONDS=0 RESUME_DELAY_SECONDS=0
        POLL_INTERVAL_SECONDS=5 WAKE_TOLERANCE_SECONDS=2
        AUTO_SCREENSAVER=1 STOP_FRAMEWORK=0 CYCLE_ABORT_SUSPEND=0
        SCREENSAVER_REDRAW_DELAY_SECONDS=0
        KHD_LAST_POWER_CLASS=screensaver
        KHD_MODE=--loop KHD_INITIAL_CYCLE=0 KHD_POWER_CLASS=screensaver
        KHD_POWER_PHASE=screensaver KHD_TARGET_EPOCH=180 KHD_WIFI_OFF=1
        case $power_case in
            ready_remaining)
                printf 'readyToSuspend\n' >"$FAKE_POWER_STATE_FILE"
                printf '110\n' >"$FAKE_CLOCK_FILE"
                khd_handle_event 'readyToSuspend 1'
                ;;
            ready_clamped)
                printf 'readyToSuspend\n' >"$FAKE_POWER_STATE_FILE"
                KHD_TARGET_EPOCH=105
                printf '110\n' >"$FAKE_CLOCK_FILE"
                khd_handle_event 'readyToSuspend 1'
                ;;
            debug_ready)
                : >"$DEBUG_FILE"
                printf 'readyToSuspend\n' >"$FAKE_POWER_STATE_FILE"
                khd_handle_event 'readyToSuspend 1'
                ;;
            wifi_active_switch)
                FAKE_WIFI_STATE=DISCONNECTED FAKE_SLEEP_POWER_STATE=active
                export FAKE_WIFI_STATE FAKE_SLEEP_POWER_STATE
                WIFI_TIMEOUT_SECONDS=1 WIFI_RETRIES=1
                khd_run_cycle
                ;;
            rapid_unknown_events)
                FAKE_EVENT_RC=2 FAKE_EVENT_TEXT='unknownEvent 9'
                export FAKE_EVENT_RC FAKE_EVENT_TEXT
                khd_loop_turn
                khd_loop_turn
                khd_loop_turn
                ;;
            poll_inferred_wake)
                KHD_TARGET_EPOCH=150
                LIPC_WAIT_BIN="$case_dir/missing-event-tool"
                FAKE_SLEEP_ADVANCE=1 FAKE_SLEEP_ADVANCE_VALUE=60
                export FAKE_SLEEP_ADVANCE FAKE_SLEEP_ADVANCE_VALUE
                khd_loop_turn
                ;;
            auto_entry_disabled)
                AUTO_SCREENSAVER=0 KHD_POWER_CLASS=active
                printf 'active\n' >"$FAKE_POWER_STATE_FILE"
                khd_enter_screensaver
                ;;
            early_wake) khd_handle_event 'wakeupFromSuspend 1' ;;
            due_wake)
                KHD_TARGET_EPOCH=100
                khd_handle_event 'resuming 1'
                ;;
            tolerance_wake)
                KHD_TARGET_EPOCH=102
                khd_handle_event 'wakeupFromSuspend 1'
                ;;
            timeout)
                KHD_TARGET_EPOCH=105
                FAKE_EVENT_RC=1 FAKE_EVENT_TEXT= FAKE_EVENT_CLOCK=105
                export FAKE_EVENT_RC FAKE_EVENT_TEXT FAKE_EVENT_CLOCK
                khd_loop_turn
                ;;
            active_pause)
                KHD_TARGET_EPOCH=90
                printf 'active\n' >"$FAKE_POWER_STATE_FILE"
                khd_observe_power test-active
                khd_run_due 0
                printf '%s\n' "$(wc -l <"$FAKE_CURL_LOG" | tr -d ' ')" >"$case_dir/active-fetches"
                : >"$FAKE_EIPS_LOG"
                printf 'screenSaver\n' >"$FAKE_POWER_STATE_FILE"
                khd_observe_power test-return
                cp "$FAKE_EIPS_LOG" "$case_dir/return-repaint"
                khd_run_due 0
                ;;
            guard_lifecycle)
                KHD_POWER_PHASE=ready CYCLE_ABORT_SUSPEND=1
                KILL_BIN=/bin/kill
                SLEEP_BIN="$TEST_TMP/bin/guard-sleep"
                FAKE_GUARD_SLEEP_PIDS="$case_dir/sleep-pids"
                export FAKE_GUARD_SLEEP_PIDS
                printf 'readyToSuspend\n' >"$FAKE_POWER_STATE_FILE"
                khd_guard_start
                saved_guard_pid=$KHD_GUARD_PID
                /bin/sleep 6
                khd_guard_stop
                if /bin/kill -0 "$saved_guard_pid" 2>/dev/null; then printf 'live\n'; else printf 'stopped\n'; fi >"$case_dir/guard-state"
                sleep_live=0
                while IFS= read -r sleep_pid; do
                    if /bin/kill -0 "$sleep_pid" 2>/dev/null; then
                        sleep_live=$((sleep_live + 1))
                        ps -o pid=,ppid=,stat=,command= -p "$sleep_pid" >>"$case_dir/live-processes" 2>/dev/null || :
                    fi
                done <"$FAKE_GUARD_SLEEP_PIDS"
                printf '%s\n' "$sleep_live" >"$case_dir/live-sleeps"
                ;;
            defer_leaves_active)
                KHD_TARGET_EPOCH=90 KHD_POWER_PHASE=ready SUSPEND_DEFER_MODE=deferSuspend
                printf 'readyToSuspend\n' >"$FAKE_POWER_STATE_FILE"
                FAKE_DEFER_ACTIVE=1
                export FAKE_DEFER_ACTIVE
                khd_run_due 0
                ;;
            guard_failure)
                KHD_TARGET_EPOCH=90 KHD_POWER_PHASE=ready CYCLE_ABORT_SUSPEND=1
                printf 'readyToSuspend\n' >"$FAKE_POWER_STATE_FILE"
                FAKE_FAIL_PROPERTY=abortSuspend
                export FAKE_FAIL_PROPERTY
                khd_run_due 0
                ;;
            unknown_pause)
                KHD_TARGET_EPOCH=90
                printf 'unrecognized-state\n' >"$FAKE_POWER_STATE_FILE"
                FAKE_POWER_STATUS='unrecognized status'
                export FAKE_POWER_STATUS
                khd_observe_power test-unknown
                khd_run_due 0
                ;;
            polling)
                KHD_TARGET_EPOCH=105
                LIPC_WAIT_BIN="$case_dir/missing-event-tool"
                FAKE_SLEEP_ADVANCE=1
                export FAKE_SLEEP_ADVANCE
                khd_loop_turn
                ;;
            frontlight)
                khd_frontlight_start
                cp "$FRONTLIGHT_STATE_FILE" "$case_dir/saved-first"
                khd_frontlight_start
                cp "$FRONTLIGHT_STATE_FILE" "$case_dir/saved-second"
                cp "$FAKE_FRONTLIGHT_FILE" "$case_dir/during"
                khd_frontlight_restore
                ;;
            prepare_ui)
                khd_prepare_ui
                ;;
            screen_entry)
                printf 'active\n' >"$FAKE_POWER_STATE_FILE"
                KHD_POWER_CLASS=active
                FAKE_POWER_BUTTON_RC=1
                export FAKE_POWER_BUTTON_RC
                khd_enter_screensaver
                ;;
            stop|once)
                cp "$LIB" "$EXT_DIR/bin/lib.sh"
                cp "$SCRIPT_DIR/../extensions/kindle-ha-dash/bin/stop.sh" "$EXT_DIR/bin/stop.sh"
                cp "$SCRIPT_DIR/../extensions/kindle-ha-dash/bin/dash.sh" "$EXT_DIR/bin/dash.sh"
                # Config is an actual trusted shell file, just as on the Kindle.
                for name in STATE_DIR TEMP_DIR IMAGE_FILE PIDFILE LOG_FILE STOP_FILE DEBUG_FILE FRAMEWORK_MARKER FRONTLIGHT_STATE_FILE PROC_ROOT LIPC_SET_BIN LIPC_GET_BIN LIPC_WAIT_BIN POWERD_TEST_BIN DMESG_BIN DATE_BIN SLEEP_BIN KILL_BIN GASGAUGE_BIN EIPS_BIN HTTP_CLIENT_BIN USB_POWER_PATH CHARGING_PATH; do
                    eval 'value=${'"$name"'}'
                    printf "%s='%s'\n" "$name" "$value" >>"$EXT_DIR/config.sh"
                done
                cat >>"$EXT_DIR/config.sh" <<'CONFIG'
BASE_URL='https://example.invalid'
TOKEN='test_token'
FBINK_BIN=''
STOP_FRAMEWORK=0
WIFI_OFF_REDRAW_DELAY_SECONDS=0
CONFIG
                if [ "$power_case" = stop ]; then
                    khd_frontlight_start
                    /bin/sh "$EXT_DIR/bin/stop.sh" >"$case_dir/command.out" 2>&1
                else
                    printf 'active\n' >"$FAKE_POWER_STATE_FILE"
                    /bin/sh "$EXT_DIR/bin/dash.sh" --once >"$case_dir/command.out" 2>&1
                fi
                printf '%s\n' "$?" >"$case_dir/command.rc"
                ;;
        esac
        printf '%s\n' "${KHD_TARGET_EPOCH:-}" >"$case_dir/target"
    ) >"$TEST_TMP/powerd-$1.out" 2>&1
    power_rc=$?
    check "$power_case fixture succeeds" "$power_rc" 0
    if [ "$power_rc" -ne 0 ]; then cat "$TEST_TMP/powerd-$1.out" >&2; fi
}

run_power_case ready_remaining
if has_event "$TEST_TMP/powerd-ready_remaining/lipc-set.log" 'rtcWakeup 70'; then a=1; else a=0; fi
check 'readyToSuspend arms remaining deadline' "$a" 1
if has_event "$TEST_TMP/powerd-ready_remaining/lipc-set.log" '-i com.lab126.powerd rtcWakeup 70'; then a=1; else a=0; fi
check 'default rtcWakeup setter uses integer flag' "$a" 1
if has_event "$TEST_TMP/powerd-ready_remaining/client.log" 'readyToSuspend 1'; then a=1; else a=0; fi
check 'raw event payload is logged' "$a" 1
run_power_case ready_clamped
if has_event "$TEST_TMP/powerd-ready_clamped/lipc-set.log" 'rtcWakeup 10'; then a=1; else a=0; fi
check 'past deadline wake timer clamps to minimum' "$a" 1
run_power_case debug_ready
if has_event "$TEST_TMP/powerd-debug_ready/lipc-set.log" 'rtcWakeup 80' && has_event "$TEST_TMP/powerd-debug_ready/lipc-set.log" 'abortSuspend 1'; then a=1; else a=0; fi
check 'debug ready arms wake timer and holds pending suspend' "$a" 1
rtc_line=$(grep -n 'rtcWakeup 80' "$TEST_TMP/powerd-debug_ready/lipc-set.log" | sed -n '1s/:.*//p')
hold_line=$(grep -n 'abortSuspend 1' "$TEST_TMP/powerd-debug_ready/lipc-set.log" | sed -n '1s/:.*//p')
if [ -n "$rtc_line" ] && [ -n "$hold_line" ] && [ "$rtc_line" -lt "$hold_line" ]; then a=1; else a=0; fi
check 'debug ready arms safety timer before suspend hold' "$a" 1
if has_event "$TEST_TMP/powerd-debug_ready/lipc-set.log" 'wirelessEnable 0'; then a=1; else a=0; fi
check 'debug ready does not disable Wi-Fi' "$a" 0

run_power_case wifi_active_switch
check 'active switch during Wi-Fi wait prevents HTTP fetch' "$(wc -l <"$TEST_TMP/powerd-wifi_active_switch/curl.log" | tr -d ' ')" 0
check 'active switch during Wi-Fi wait prevents display' "$(wc -l <"$TEST_TMP/powerd-wifi_active_switch/eips.log" | tr -d ' ')" 0
if has_event "$TEST_TMP/powerd-wifi_active_switch/lipc-set.log" 'wirelessEnable 0'; then a=1; else a=0; fi
check 'active switch prevents radio-off retry' "$a" 0
run_power_case rapid_unknown_events
check 'repeated immediate event exits each sleep one second' "$(cat "$TEST_TMP/powerd-rapid_unknown_events/sleep.log")" "$(printf '1\n1\n1')"
check 'immediate unknown events still subscribe each turn' "$(wc -l <"$TEST_TMP/powerd-rapid_unknown_events/events.log" | tr -d ' ')" 3
check 'immediate unknown events do not fetch early' "$(wc -l <"$TEST_TMP/powerd-rapid_unknown_events/curl.log" | tr -d ' ')" 0
run_power_case poll_inferred_wake
if has_event "$TEST_TMP/powerd-poll_inferred_wake/client.log" 'inferred wake: wait_elapsed=60' && has_event "$TEST_TMP/powerd-poll_inferred_wake/client.log" 'PM: simulated powerd wake diagnostic'; then a=1; else a=0; fi
check 'long polling clock gap logs inferred wake and dmesg' "$a" 1
check 'inferred polling wake fetches overdue image' "$(wc -l <"$TEST_TMP/powerd-poll_inferred_wake/curl.log" | tr -d ' ')" 1

run_power_case early_wake
check 'early wake does not fetch' "$(wc -l <"$TEST_TMP/powerd-early_wake/curl.log" | tr -d ' ')" 0
if [ -s "$TEST_TMP/powerd-early_wake/eips.log" ]; then a=1; else a=0; fi
check 'early wake repaints cached image' "$a" 1
if has_event "$TEST_TMP/powerd-early_wake/client.log" 'PM: simulated powerd wake diagnostic'; then a=1; else a=0; fi
check 'wake logs dmesg diagnostics' "$a" 1
run_power_case due_wake
check 'due wake fetches exactly once' "$(wc -l <"$TEST_TMP/powerd-due_wake/curl.log" | tr -d ' ')" 1
check 'successful due cycle schedules next target' "$(cat "$TEST_TMP/powerd-due_wake/target")" 160
run_power_case tolerance_wake
check 'wake within tolerance fetches once' "$(wc -l <"$TEST_TMP/powerd-tolerance_wake/curl.log" | tr -d ' ')" 1
run_power_case timeout
check 'event timeout runs due fetch' "$(wc -l <"$TEST_TMP/powerd-timeout/curl.log" | tr -d ' ')" 1
if [ -s "$TEST_TMP/powerd-timeout/events.log" ]; then a=1; else a=0; fi
check 'loop waits on event source' "$a" 1

run_power_case active_pause
check 'active UI pauses overdue fetch' "$(cat "$TEST_TMP/powerd-active_pause/active-fetches")" 0
if [ -s "$TEST_TMP/powerd-active_pause/return-repaint" ]; then a=1; else a=0; fi
check 'return to screensaver repaints immediately' "$a" 1
check 'return to screensaver resumes due fetch' "$(wc -l <"$TEST_TMP/powerd-active_pause/curl.log" | tr -d ' ')" 1
run_power_case guard_lifecycle
abort_count=$(grep -c 'abortSuspend 1' "$TEST_TMP/powerd-guard_lifecycle/lipc-set.log")
if [ "$abort_count" -ge 2 ]; then a=1; else a=0; fi
check 'guard renews ready transition hold after five seconds' "$a" 1
check 'guard stop reaps guard process' "$(cat "$TEST_TMP/powerd-guard_lifecycle/guard-state")" stopped
check 'guard stop reaps its real sleep child' "$(cat "$TEST_TMP/powerd-guard_lifecycle/live-sleeps")" 0
[ ! -s "$TEST_TMP/powerd-guard_lifecycle/live-processes" ] || cat "$TEST_TMP/powerd-guard_lifecycle/live-processes" >&2
run_power_case defer_leaves_active
check 'defer that leaves screensaver prevents HTTP fetch' "$(wc -l <"$TEST_TMP/powerd-defer_leaves_active/curl.log" | tr -d ' ')" 0
run_power_case guard_failure
check 'failed suspend guard prevents HTTP fetch' "$(wc -l <"$TEST_TMP/powerd-guard_failure/curl.log" | tr -d ' ')" 0
check 'failed guard schedules bounded retry' "$(cat "$TEST_TMP/powerd-guard_failure/target")" 110
run_power_case unknown_pause
check 'unknown UI state pauses overdue fetch' "$(wc -l <"$TEST_TMP/powerd-unknown_pause/curl.log" | tr -d ' ')" 0
run_power_case polling
check 'missing event tool falls back to five second poll' "$(cat "$TEST_TMP/powerd-polling/sleep.log")" 5
check 'poll fallback runs due fetch' "$(wc -l <"$TEST_TMP/powerd-polling/curl.log" | tr -d ' ')" 1

run_power_case frontlight
check 'frontlight saves original brightness' "$(cat "$TEST_TMP/powerd-frontlight/saved-first")" 12
check 'repeated frontlight start preserves original' "$(cat "$TEST_TMP/powerd-frontlight/saved-second")" 12
check 'frontlight is zero while dashboard runs' "$(cat "$TEST_TMP/powerd-frontlight/during")" 0
check 'frontlight restores original brightness' "$(cat "$TEST_TMP/powerd-frontlight/frontlight")" 12
if [ -e "$TEST_TMP/powerd-frontlight/ext/frontlight-state" ]; then a=1; else a=0; fi
check 'frontlight restore clears saved state' "$a" 0
run_power_case prepare_ui
if has_event "$TEST_TMP/powerd-prepare_ui/lipc-set.log" 'preventScreenSaver 0' && ! has_event "$TEST_TMP/powerd-prepare_ui/lipc-set.log" 'preventScreenSaver 1'; then a=1; else a=0; fi
check 'UI preparation allows powerd screensaver' "$a" 1
run_power_case auto_entry_disabled
if ! has_event "$TEST_TMP/powerd-auto_entry_disabled/lipc-set.log" 'powerButton' && ! has_event "$TEST_TMP/powerd-auto_entry_disabled/powerd.log" '-p'; then a=1; else a=0; fi
check 'disabled automatic entry never presses power button' "$a" 1
run_power_case screen_entry
if has_event "$TEST_TMP/powerd-screen_entry/lipc-set.log" 'powerButton 1' && has_event "$TEST_TMP/powerd-screen_entry/powerd.log" '-p'; then a=1; else a=0; fi
check 'screen entry falls back to powerd_test on command failure' "$a" 1

run_power_case stop
check 'actual stop script succeeds' "$(cat "$TEST_TMP/powerd-stop/command.rc")" 0
check 'actual stop script restores saved frontlight' "$(cat "$TEST_TMP/powerd-stop/frontlight")" 12
if has_event "$TEST_TMP/powerd-stop/lipc-set.log" 'wirelessEnable 1' && has_event "$TEST_TMP/powerd-stop/lipc-set.log" 'preventScreenSaver 0'; then a=1; else a=0; fi
check 'actual stop script restores Wi-Fi and screensaver policy' "$a" 1
run_power_case once
check 'actual once script succeeds' "$(cat "$TEST_TMP/powerd-once/command.rc")" 0
check 'once fetches one image while active' "$(wc -l <"$TEST_TMP/powerd-once/curl.log" | tr -d ' ')" 1
check 'once exit restores original frontlight' "$(cat "$TEST_TMP/powerd-once/frontlight")" 12
if [ ! -s "$TEST_TMP/powerd-once/events.log" ] && ! has_event "$TEST_TMP/powerd-once/lipc-set.log" 'powerButton' && ! has_event "$TEST_TMP/powerd-once/powerd.log" '-p'; then a=1; else a=0; fi
check 'once never enters screensaver or subscribes to events' "$a" 1

# Keep the old raw-suspend mechanism absent, including configurable aliases.
if grep -E '(/sys/power/state|POWER_STATE_PATH|khd_(write_node|arm_alarm|sleep_cycle)|rtcwake)' "$LIB" "$SCRIPT_DIR/../extensions/kindle-ha-dash/bin/dash.sh" >/dev/null; then a=1; else a=0; fi
check 'client has no raw kernel suspend path' "$a" 0

if khd_claim_pid; then a=1; else a=0; fi
check 'PID claim succeeds' "$a" 1
check 'PID file records current process' "$(cat "$PIDFILE")" "$$"
found=$(khd_find_pid); rc=$?
check 'tracked dash process found' "$found:$rc" "$$:0"
khd_release_pid
if [ -e "$PIDFILE" ] || [ -e "$PIDFILE.lock" ]; then a=0; else a=1; fi
check 'release removes owned pid and lock' "$a" 1

printf '%s\n' "$$" >"$PIDFILE"
printf 'unrelated-process\000' >"$PROC_ROOT/$$/cmdline"
found=$(khd_find_pid); rc=$?
if [ "$rc" -eq 0 ]; then a=1; else a=0; fi
check 'unrelated live process rejected' "$a" 0

# Stale singleton state is reclaimed; a live matching process is never replaced.
printf '%s\n' 999999 >"$PIDFILE"
mkdir "$PIDFILE.lock"
if khd_claim_pid; then a=1; else a=0; fi
check 'stale pid and lock are recovered' "$a:$(cat "$PIDFILE")" "1:$$"
khd_release_pid
printf '%s\000' "$EXT_DIR/bin/dash.sh" >"$PROC_ROOT/$$/cmdline"
printf '%s\n' "$$" >"$PIDFILE"
mkdir "$PIDFILE.lock"
if khd_claim_pid; then a=1; else a=0; fi
check 'duplicate live singleton refused' "$a" 0
check 'duplicate refusal preserves pid' "$(cat "$PIDFILE")" "$$"
rmdir "$PIDFILE.lock"

printf '\nTests: %s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
