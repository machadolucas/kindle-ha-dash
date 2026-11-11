#!/bin/sh
# Run explicitly over SSH. Never suspends, draws, toggles Wi-Fi or logs a token.
EXT_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd) || exit 1
# shellcheck source=kindle/extensions/kindle-ha-dash/bin/lib.sh
. "$EXT_DIR/bin/lib.sh"
khd_init "$EXT_DIR" || exit 1
if ! khd_claim_pid; then
    echo 'Stop the dashboard/other selftest before running diagnostics.' >&2
    exit 1
fi
khd_selftest_alarm=0
khd_selftest_cleanup() {
    khd_cancel_child
    [ "$khd_selftest_alarm" != 1 ] || khd_clear_alarm || :
    rm -f "$TEMP_DIR/selftest.$$.headers" "$TEMP_DIR/selftest.$$.png" "$TEMP_DIR/selftest.$$.code"
    khd_release_pid
}
trap 'khd_selftest_cleanup' 0
trap 'exit 1' HUP INT TERM
khd_selftest_failed=0
printf '%s\n' 'Kindle HA Dashboard diagnostics (NO suspend)' "Client: $CLIENT_VERSION"
printf '\nFirmware:\n'
khd_read_node "${FIRMWARE_FILE:-/etc/prettyversion.txt}" 2>/dev/null || echo '(unavailable)'
printf '\nDisplay (eips -i):\n'
khd_eips -i 2>&1 || echo '(unavailable)'
printf '\nRTC nodes:\n'
for khd_rtc in "$RTC_ROOT"/rtc*; do
    [ -d "$khd_rtc" ] || continue
    printf '%s wakealarm=' "$khd_rtc"
    khd_read_node "$khd_rtc/wakealarm" 2>/dev/null || echo '(unavailable)'
done
printf 'Selected RTC: %s\n' "$RTC_DEVICE"
khd_existing_alarm=$(khd_read_node "$RTC_DEVICE/wakealarm" 2>/dev/null | tr -d ' \t\r\n')
case $khd_existing_alarm in
    ''|0)
        # Set cleanup BEFORE writing, including the failed-readback case.
        khd_selftest_alarm=1
        if khd_arm_alarm 120; then
            printf 'RTC write/readback: PASS (epoch %s); clearing now\n' "$khd_alarm_epoch"
        else
            echo 'RTC write/readback: FAIL (missing node, permissions, busy clock or mismatch)'
            khd_selftest_failed=1
        fi
        if khd_clear_alarm; then
            khd_after_clear=$(khd_read_node "$RTC_DEVICE/wakealarm" 2>/dev/null | tr -d ' \t\r\n')
            case $khd_after_clear in ''|0) echo 'RTC cleared: PASS'; khd_selftest_alarm=0 ;; *) echo 'RTC cleared: FAIL'; khd_selftest_failed=1 ;; esac
        else
            echo 'RTC clear: FAIL'
            khd_selftest_failed=1
        fi
        ;;
    *) echo 'RTC test: SKIPPED (an existing alarm belongs to another application)'; khd_selftest_failed=1 ;;
esac
printf '\nWi-Fi state (no changes made): %s\n' "$(khd_wifi_state)"
khd_read_battery
printf 'Battery: %s%%; charging: %s\n' "${KHD_BATTERY:-unknown}" "$KHD_CHARGING"
printf 'USB-powered: %s (node: %s)\n' "$KHD_USB_POWERED" "$USB_POWER_PATH"
printf 'Awake/debug flag: '; if khd_awake; then echo yes; else echo no; fi
printf 'FBInk: %s\n' "${FBINK_BIN:-not found (using eips)}"
printf 'HTTP client: %s\n' "${HTTP_CLIENT_BIN:-not found}"
if [ -n "$HTTP_CLIENT_BIN" ]; then "$HTTP_CLIENT_BIN" --version 2>/dev/null | sed -n '1,2p'; fi
printf 'CA bundle: %s; insecure TLS: %s\n' "${CA_BUNDLE:-client default trust store}" "$INSECURE_TLS"
printf '\nHTTPS probe to BASE_URL root (no token sent; enable Wi-Fi first):\n'
if khd_validate_server && mkdir -p "$TEMP_DIR"; then
    if khd_http_request "${BASE_URL%/}/" "$TEMP_DIR/selftest.$$"; then
        khd_probe_code=$(cat "$TEMP_DIR/selftest.$$.code")
        case $khd_probe_code in
            [1-5][0-9][0-9])
                printf 'Transport/TLS: PASS; root HTTP status %s (not an image endpoint test)\n' "$khd_probe_code"
                [ "$INSECURE_TLS" != 1 ] || echo 'WARNING: TLS identity verification was DISABLED.'
                ;;
            *) echo 'Transport/TLS: FAIL (no HTTP status)'; khd_selftest_failed=1 ;;
        esac
    else
        khd_probe_rc=$?
        printf 'Transport/TLS: FAIL; client exit %s (check time, Wi-Fi, CA and TLS support)\n' "$khd_probe_rc"
        khd_selftest_failed=1
    fi
else
    echo 'Probe skipped: configure BASE_URL, TOKEN and HTTP client first.'
    khd_selftest_failed=1
fi
echo 'Use Refresh once for an authenticated image/display test. No suspend was attempted.'
exit "$khd_selftest_failed"
