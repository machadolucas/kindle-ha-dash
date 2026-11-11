# Kindle HA Dashboard client

KUAL extension for a jailbroken Paperwhite 3 (7th generation, 1072×1448,
firmware 5.x). Downloads an already rendered PNG; it does not run a browser.
No boot hooks, bundled binaries, or changes to the Home Assistant integration.
All device scripts run through `sh`; FAT execute bits and symlinks are unnecessary.

## Install and configure

On your Mac, from the repository root, **stop an existing dashboard before an
upgrade**, then run:

```sh
kindle/install.sh root@<kindle-ip>
```

The installer uses SSH and SCP, creates `/mnt/us/extensions/kindle-ha-dash/`,
copies only the shipped scripts/descriptors/example, preserves an existing
`config.sh`, and creates one from the example on first install. It neither
starts the client nor installs startup hooks. New OpenSSH uses SFTP by default;
the installer selects legacy SCP with `-O`. For an old Mac client without `-O`,
use `SCP_LEGACY=0 sh kindle/install.sh root@<kindle-ip>`.

Alternatively, copy `extensions/kindle-ha-dash/` from this directory into the
Kindle's `/mnt/us/extensions/` over USB, and copy `config.sh.example` to
`config.sh` there. Safely eject USB storage before running the extension.

Edit the **device's** `config.sh` over SSH. Set `BASE_URL` to the HTTPS origin
(or the configured base path) and `TOKEN` to the integration's token. Do not add
the `/api/kindle_dash/...` endpoint to `BASE_URL`. Quote shell values; the config
is sourced as trusted shell code. Keep the config private. The local config
path is ignored by `kindle/.gitignore` and is never uploaded by the installer.
Configuration is read at launch; stop the client before changing runtime paths
or command overrides so Stop can still locate the original process and state.

The example documents every required option. Defaults are 30-minute fallback,
60-second minimum, 2-hour maximum, 30-second Wi-Fi connection timeout, two
retries after the first attempt, 45-second HTTP timeout, 10% low-battery cutoff,
and 5-minute maximum intervals when awake. Configured numeric values must be
unsigned decimal integers of at most nine digits. Invalid limits stop startup
with a diagnostic; leading zeros are accepted.

## First device test

Keep USB power connected and create the debug flag before experimenting:

```sh
touch /mnt/us/kindle-ha-dash.debug
sh /mnt/us/extensions/kindle-ha-dash/bin/selftest.sh
sh /mnt/us/extensions/kindle-ha-dash/bin/start.sh --once
tail -f /mnt/us/extensions/kindle-ha-dash/dashboard.log
```

`selftest.sh` requires the dashboard to be stopped and shares its singleton lock.
It reports firmware, `eips -i`, RTC nodes, Wi-Fi state, battery, USB power, FBInk,
curl version and an HTTPS request to the **BASE_URL root without the token**.
Any valid root HTTP status demonstrates transport completion; even a root 404
does not test the authenticated image endpoint. In insecure mode it explicitly
reports that identity checking is disabled. Missing/failed RTC or TLS checks
produce a nonzero exit status.

The RTC test clears, programs an alarm 120 seconds ahead, verifies its readback,
and clears it again, **without writing to `/sys/power/state`**. It refuses to
overwrite an existing nonzero alarm. Do not run another RTC-owning application
concurrently. SIGKILL or power loss cannot execute shell cleanup; if interrupted
that way, check/clear the alarm before testing further.

KUAL exposes **Start dashboard**, **Stop dashboard**, and **Refresh once**.
Start returns immediately; check for `dashboard started` in the log to confirm
the background process actually started. Refresh once is also detached, fetches
and displays one cycle, and never suspends or waits for a refresh interval. It
restores normal power/UI settings and enables Wi-Fi when done. Stop the loop
before Refresh once; a second instance is refused.

For the continuous loop:

```sh
sh /mnt/us/extensions/kindle-ha-dash/bin/start.sh
# When finished:
sh /mnt/us/extensions/kindle-ha-dash/bin/stop.sh
```

Always use the full installed script path, as above. PID ownership is checked
against `/proc/<pid>/cmdline` before signaling a process; unrelated reused PIDs
are never killed. A stale PID/lock is recovered on the next launch. If two
launches race, retry Start after a second. State and the last downloaded image
live in RAM under `/tmp/kindle-ha-dash/`; logs live alongside the extension.

## Escape hatches and power behavior

* **Debug flag**: `/mnt/us/kindle-ha-dash.debug` keeps the device awake with Wi-Fi
  enabled. Charging or detected USB power does the same, including a full battery
  that is no longer charging. Awake sleep intervals are capped by
  `AWAKE_INTERVAL_SECONDS`. Radio off/on retries are suppressed while awake;
  enable/wait retries still run. Remove the debug flag **and** unplug power to
  exercise real suspend. Plugging USB into a computer can invoke the stock USB
  storage screen; prefer a wall charger or established USBNetwork setup for SSH.
* **Stop flag**: create `/mnt/us/kindle-ha-dash.stop` from SSH or USB storage.
  The client checks it during Wi-Fi waits, ordinary sleeps, and between cycles.
  A suspended shell cannot inspect files until the device wakes. Stop restores
  the UI, enables Wi-Fi and clears the alarm; explicit Start / Refresh once removes
  a previous stop flag. KUAL Stop and `stop.sh` also signal the verified PID, then
  escalate to KILL after ten seconds if needed. Check the log for restore errors.
* **Low battery**: below the configured cutoff and not charging, the client prints
  `battery low, please charge`, skips all downloads, disables Wi-Fi and requests
  `MAX_SLEEP_SECONDS` before checking again. Debug/USB awake mode takes priority
  over disabling Wi-Fi and caps that interval. Unknown battery percentage is sent
  as `battery=` and does not activate the cutoff.
* **Stock UI**: `preventScreenSaver=1` is held while running and restored to `0`
  on exit. `STOP_FRAMEWORK=0` by default. With `1`, configured Upstart jobs are
  recorded before stopping, and exit/Stop starts them again—even if the option
  is later changed. With the framework stopped, use SSH or the stop flag if KUAL
  is unavailable. A reboot returns to the stock UI: nothing auto-starts.

For ordinary battery operation each cycle enables Wi-Fi, waits for `CONNECTED`,
fetches and displays, disables Wi-Fi, programs the PMIC RTC, verifies its alarm,
then separately writes `mem` to the power-state node. A successful radio-disable
command is required before suspend. After resume it waits a few seconds before
touching Wi-Fi. An early USB/debug wake re-enables Wi-Fi. If suspend is refused,
returns immediately, or RTC verification fails, it sleeps the remaining interval
in interruptible five-second slices; it does not spin. These ordinary sleeps
also notice a new debug/USB override. The RTC is cleared after resume/failure.

Fetches accept **only** HTTP 200 with the complete eight-byte PNG magic, then
move the temporary download over the cached file. Error responses, TLS failures,
timeouts and invalid signatures preserve the previous image; a bottom status
line reports `no connection HH:MM`. This is a signature check, not a full PNG
decoder: dimensions, grayscale format and PNG integrity remain the server's
contract, and display-command errors are logged. Header matching is case
insensitive, strips CRLF, and resets between HTTP response blocks. Missing or
invalid sleep headers use the fallback, with the same min/max clamps. Only
`X-Full-Refresh: 1` requests flashing; other values use partial refresh.

Sleep means time **after** fetch/display, rather than a fixed wall-clock cadence.
Logs record cycle duration, requested sleep, actual suspend time and drift. Epoch
time is used because old kernels differ on whether uptime includes suspend;
clock corrections can affect drift measurements. Negative elapsed values are
clamped when calculating remaining sleep. Rotation keeps one `.old` file after
`LOG_MAX_BYTES` is exceeded. Request URLs, token values and curl stderr are never
logged. Do not run `sh -x` or paste `config.sh` into diagnostic reports.
Transport failures include the numeric curl exit code: common codes are 6 (DNS),
7 (connection), 28 (timeout), 35 (TLS negotiation), and 60 (certificate validation).

## Hardware overrides and troubleshooting

| Assumption / symptom | Config override or check |
| --- | --- |
| PW3 wake clock is `rtc1`, not `rtc0` | `RTC_DEVICE` is an RTC directory. Auto-detection prefers `rtc1` with a `wakealarm` node; otherwise `rtc0`. `RTC_ROOT` changes discovery. Run selftest and verify an actual timed wake yourself. |
| Kernel suspend | `POWER_STATE_PATH` defaults to `/sys/power/state`; `RESUME_DELAY_SECONDS=3`. No `rtcwake`, `powerd_test` or firmware-specific sleep service is required. A successful write can still return early; read the drift log. |
| Wi-Fi fails after resume | Increase `RESUME_DELAY_SECONDS`, `WIFI_TIMEOUT_SECONDS`, `WIFI_RETRIES` or `WIFI_TOGGLE_DELAY_SECONDS`. Connection state comes from `com.lab126.wifid cmState`. A saved usable network is required; the extension does not provision one. |
| TLS fails on old firmware | Set `HTTP_CLIENT_BIN` to a curl-compatible executable. Discovery order: extension `bin/curl`, `/mnt/us/usbnet/bin/curl`, PATH `curl`. Supply your own compatible binary separately; none is bundled. Check date/time, CA trust and supported TLS versions using selftest. |
| CA errors | Set `CA_BUNDLE` to a readable PEM trust bundle. `INSECURE_TLS=1` is a last-resort diagnostic escape hatch: it exposes the token to an impersonating server. Restore `0`; it does not fix an unsupported TLS protocol/cipher. Redirects are deliberately not followed. |
| Battery / full USB-power detection | `GASGAUGE_BIN` supplies percentage; charging comes from LIPC, then `CHARGING_PATH`, then a textual gasgauge status fallback if available. `USB_POWER_PATH` defaults to `/sys/devices/system/wario_charger/wario_charger0/connected`; confirm selftest reports `1` while plugged in, including at 100%. If it reports unknown, set the correct node and keep the debug flag for SSH. |
| FBInk / eips rendering | `FBINK_BIN` auto-searches PATH, `/mnt/us/libkh/bin`, and `/mnt/us/koreader` plus its `bin/`. Set it to an explicit path, or `''` to force eips. Failed FBInk calls fall back to eips. Full eips refresh clears first, then uses `-f -g`. Verify both refresh modes on your firmware. |
| Bottom text is clipped | `EIPS_STATUS_COL` and `EIPS_STATUS_ROW`; auto row uses `eips -i`'s row count if recognizable, otherwise PW3's assumed row 59. FBInk uses `-y -1`. Confirm the font/orientation and bottom line on-device. |
| UI redraws over the image | Experiment with `STOP_FRAMEWORK=1` and `FRAMEWORK_JOBS='framework lab126_gui'`. Job names and stopping effects need device verification. Start with a debug flag and SSH available. |
| Tools installed elsewhere | Override `LIPC_SET_BIN`, `LIPC_GET_BIN`, `GASGAUGE_BIN`, `EIPS_BIN`, `START_BIN`, `STOP_BIN`, `SLEEP_BIN`, `DATE_BIN`, `KILL_BIN`. Each is one command/path, without arguments. Device actions pass through wrapper functions. |
| Runtime paths / lock troubleshooting | `STATE_DIR`, `PIDFILE`, `TEMP_DIR`, `IMAGE_FILE`, `FRAMEWORK_MARKER`, `PROC_ROOT`, `DEBUG_FILE`, `STOP_FILE`, `LOG_FILE`, `LOG_MAX_BYTES`. Keep download temp/cache on the same filesystem for atomic moves. If a launch died during stale recovery and left `.reap`, verify no dashboard/selftest is running before removing that directory. Never delete a live singleton lock. |

Keep the frontlight off using the stock UI when measuring battery use. Battery
life depends on its age, Wi-Fi association time, interval, full-refresh frequency,
and whether suspend truly works. No weeks/months claim is validated here. Measure
unplugged discharge over a day or more and inspect logs for unexpectedly short
suspends. Awake/debug/USB mode and plain-sleep fallbacks consume more energy than
working suspend. The low-battery cutoff reduces activity; it is not a hardware
shutdown or battery-protection guarantee.

Autostart can be added later using a firmware-appropriate startup hook that calls
`sh /mnt/us/extensions/kindle-ha-dash/bin/start.sh` after user storage and LIPC
are ready. First verify recovery, debug/stop flags and several unplugged RTC
cycles. This package deliberately installs no such hook.

## Host verification

Run from the repository root:

```sh
sh kindle/tests/run.sh
dash kindle/tests/run.sh
find kindle -name '*.sh' -exec sh -n {} \;
# If installed:
shellcheck -s sh kindle/install.sh kindle/extensions/kindle-ha-dash/bin/*.sh kindle/tests/run.sh
```

Tests use only temporary fixtures and fake device/HTTP commands; they never
contact a Kindle or HTTP server. They cover header parsing, bounds, magic bytes,
failed-fetch preservation, singleton behavior, low battery, awake overrides and
RTC/suspend fallbacks. Passing host tests does not validate the PW3 kernel,
LIPC properties, USB detection, Upstart jobs or e-ink output.

Technique references: [KOReader KUAL descriptor](https://github.com/koreader/koreader/blob/master/platform/kindle/extensions/koreader/config.xml),
[FBInk CLI](https://github.com/NiLuJe/FBInk/blob/master/CLI.md),
[KOReader PW3 hardware configuration](https://github.com/koreader/koreader/blob/master/frontend/device/kindle/device.lua),
and the author's [Wario USB-power sysfs example](https://www.mobileread.com/forums/showthread.php?t=347934).
The client is original shell code; nothing from these projects is vendored.

## Installing without KUAL (scriptlets, WinterBreak2 and other modern jailbreaks)

Modern jailbreaks replace KUAL with *scriptlets*: `.sh` files in the Kindle's
`documents` folder that show up in the library and run as root when tapped.

1. Connect the Kindle over USB and run `kindle/install-usb.sh /Volumes/Kindle`.
2. Edit `extensions/kindle-ha-dash/config.sh` on the Kindle (`BASE_URL`, `TOKEN`).
3. Eject. The library now has **Dashboard: Start**, **Stop**, **Refresh once**
   and **Self-test** (which writes `kindle-ha-dash-selftest.txt` to the Kindle's
   storage, readable over USB).

No SSH is required; logs and the self-test report are read over USB.
