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
EOF
cat >"$TEST_TMP/bin/lipc-get-prop" <<'EOF'
#!/bin/sh
case ${2-} in
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
EOF
chmod +x "$TEST_TMP/bin/"*

export PATH="$TEST_TMP/bin:$PATH"
export FAKE_CURL_LOG="$TEST_TMP/curl.log" FAKE_EIPS_LOG="$TEST_TMP/eips.log"
export FAKE_LIPC_SET_LOG="$TEST_TMP/lipc-set.log"
export FAKE_SLEEP_LOG="$TEST_TMP/sleep.log"
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
run_suspend_case() {
    suspend_case=$1
    (
        RTC_DEVICE="$TEST_TMP/rtc-$suspend_case"
        POWER_STATE_PATH="$TEST_TMP/power-$suspend_case"
        DEBUG_FILE="$TEST_TMP/debug-$suspend_case"
        LOG_FILE="$TEST_TMP/suspend-$suspend_case.log"
        EVENT_FILE="$TEST_TMP/events-$suspend_case"
        mkdir -p "$RTC_DEVICE"
        : >"$RTC_DEVICE/wakealarm"
        KHD_WIFI_OFF=1
        KHD_BATTERY=50
        KHD_CHARGING=0
        KHD_USB_POWERED=0
        AWAKE_INTERVAL_SECONDS=4
        RESUME_DELAY_SECONDS=1
        SIM_ALARM=0
        SIM_READ_BAD=0
        SIM_MEM_RC=0
        SIM_READ_COUNT=0
        case $suspend_case in
            wifi_off_failure) : ;;
            alarm_readback_failure) SIM_READ_BAD=1 ;;
            mem_failure) SIM_MEM_RC=1 ;;
            debug_awake) : >"$DEBUG_FILE" ;;
            usb_awake) KHD_BATTERY=100; KHD_USB_POWERED=1 ;;
            debug_after_alarm) : ;;
            wake_during_fallback)
                SIM_READ_BAD=1
                FAKE_SLEEP_WAKE_FILE="$TEST_TMP/wake-during-fallback"
                FAKE_SLEEP_EVENT_FILE="$TEST_TMP/events-$suspend_case"
                export FAKE_SLEEP_WAKE_FILE FAKE_SLEEP_EVENT_FILE
                ;;
        esac
        khd_log() { :; }
        khd_clock() { printf '%s\n' 100; }
        khd_now() { printf '%s\n' 100; }
        khd_read_battery() {
            SIM_READ_COUNT=$((SIM_READ_COUNT + 1))
            case $suspend_case in
                usb_awake) KHD_BATTERY=100; KHD_CHARGING=0; KHD_USB_POWERED=1 ;;
                wake_during_fallback)
                    KHD_BATTERY=50; KHD_CHARGING=0
                    if [ -e "$FAKE_SLEEP_WAKE_FILE" ]; then KHD_USB_POWERED=1; else KHD_USB_POWERED=0; fi
                    ;;
                debug_after_alarm)
                    KHD_BATTERY=50; KHD_CHARGING=0; KHD_USB_POWERED=0
                    [ "$SIM_READ_COUNT" -lt 2 ] || : >"$DEBUG_FILE"
                    ;;
                *) KHD_BATTERY=50; KHD_CHARGING=0; KHD_USB_POWERED=0 ;;
            esac
        }
        khd_stop_requested() { return 1; }
        if [ "$suspend_case" != wake_during_fallback ]; then
            khd_pause() { printf 'pause:%s\n' "$1" >>"$EVENT_FILE"; }
        fi
        khd_sleep() {
            printf 'sleep:%s\n' "$1" >>"$EVENT_FILE"
            if [ -n "${FAKE_SLEEP_WAKE_FILE:-}" ]; then : >"$FAKE_SLEEP_WAKE_FILE"; fi
        }
        khd_wifi_set() {
            printf 'wifi:%s\n' "$1" >>"$EVENT_FILE"
            if [ "$suspend_case" = wifi_off_failure ] && [ "$1" = 0 ]; then
                KHD_WIFI_OFF=0
                return 1
            fi
            if [ "$1" = 0 ]; then KHD_WIFI_OFF=1; else KHD_WIFI_OFF=0; fi
            return 0
        }
        khd_write_node() {
            printf 'write:%s:%s\n' "$1" "$2" >>"$EVENT_FILE"
            if [ "$1" = "$RTC_DEVICE/wakealarm" ]; then SIM_ALARM=$2; fi
            if [ "$1" = "$POWER_STATE_PATH" ]; then return "$SIM_MEM_RC"; fi
            return 0
        }
        khd_read_node() {
            printf 'read:%s\n' "$1" >>"$EVENT_FILE"
            if [ "$SIM_READ_BAD" = 1 ]; then printf '%s\n' wrong; else printf '%s\n' "$SIM_ALARM"; fi
        }
        khd_sleep_cycle 10
    ) >"$TEST_TMP/suspend-$1.out" 2>&1
}
has_event() { grep -F "$2" "$1" >/dev/null 2>&1; }

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

# RTC and suspend paths are fully simulated by shell function overrides.
run_suspend_case rtc_suspend
events="$TEST_TMP/events-rtc_suspend"
if has_event "$events" "write:$TEST_TMP/rtc-rtc_suspend/wakealarm:0" &&
   has_event "$events" "write:$TEST_TMP/rtc-rtc_suspend/wakealarm:110" &&
   has_event "$events" "read:$TEST_TMP/rtc-rtc_suspend/wakealarm" &&
   has_event "$events" "write:$TEST_TMP/power-rtc_suspend:mem"; then a=1; else a=0; fi
check 'RTC arm precedes separate mem request' "$a" 1
mem_line=$(grep -n -F "write:$TEST_TMP/power-rtc_suspend:mem" "$events" | sed -n '1s/:.*//p')
readback_line=$(grep -n -F "read:$TEST_TMP/rtc-rtc_suspend/wakealarm" "$events" | sed -n '1s/:.*//p')
if [ -n "$mem_line" ] && [ -n "$readback_line" ] && [ "$mem_line" -gt "$readback_line" ]; then a=1; else a=0; fi
check 'mem request follows alarm readback' "$a" 1
if has_event "$events" 'pause:10'; then a=1; else a=0; fi
check 'immediate suspend return sleeps remaining interval' "$a" 1

run_suspend_case mem_failure
events="$TEST_TMP/events-mem_failure"
if has_event "$events" "write:$TEST_TMP/power-mem_failure:mem" && has_event "$events" 'pause:10'; then a=1; else a=0; fi
check 'failed mem write sleeps remaining interval' "$a" 1

run_suspend_case alarm_readback_failure
events="$TEST_TMP/events-alarm_readback_failure"
if has_event "$events" 'pause:10' && has_event "$events" 'read:'; then a=1; else a=0; fi
check 'alarm readback failure falls back to timed sleep' "$a" 1
if has_event "$events" ':mem'; then a=1; else a=0; fi
check 'alarm readback failure avoids mem request' "$a" 0

run_suspend_case wifi_off_failure
events="$TEST_TMP/events-wifi_off_failure"
if has_event "$events" 'pause:10'; then a=1; else a=0; fi
check 'Wi-Fi off failure falls back to timed sleep' "$a" 1
if has_event "$events" ':mem'; then a=1; else a=0; fi
check 'Wi-Fi off failure avoids mem request' "$a" 0

run_suspend_case debug_awake
events="$TEST_TMP/events-debug_awake"
if has_event "$events" 'pause:4'; then a=1; else a=0; fi
check 'awake marker caps sleep interval' "$a" 1
if has_event "$events" ':mem'; then a=1; else a=0; fi
check 'awake marker avoids mem request' "$a" 0

run_suspend_case debug_after_alarm
events="$TEST_TMP/events-debug_after_alarm"
if has_event "$events" 'read:' && [ -e "$TEST_TMP/debug-debug_after_alarm" ]; then a=1; else a=0; fi
check 'debug override is rechecked after RTC programming' "$a" 1
if has_event "$events" ':mem'; then a=1; else a=0; fi
check 'new debug override cancels mem request' "$a" 0

run_suspend_case usb_awake
events="$TEST_TMP/events-usb_awake"
if has_event "$events" 'pause:4'; then a=1; else a=0; fi
check 'fully charged USB-powered device stays awake' "$a" 1
if has_event "$events" ':mem'; then a=1; else a=0; fi
check 'USB-powered awake device avoids mem request' "$a" 0

run_suspend_case wake_during_fallback
events="$TEST_TMP/events-wake_during_fallback"
if has_event "$events" 'sleep:5' && has_event "$events" 'sleep:4' && has_event "$events" 'wifi:1'; then a=1; else a=0; fi
check 'USB wake during fallback enables Wi-Fi and caps remainder' "$a" 1
if has_event "$events" ':mem'; then a=1; else a=0; fi
check 'fallback USB wake avoids mem request' "$a" 0

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
