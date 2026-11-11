# Kindle HA Dashboard client

Target: jailbroken Kindle Paperwhite 3 (7th generation, 1072×1448), firmware
**5.16.2.1.1**, using library scriptlets and USB storage. The client downloads an
already rendered PNG; it does not run a browser. No SSH, boot hook, bundled binary,
or change to the Home Assistant integration is required. Scripts run through `sh`;
FAT execute bits and symlinks are unnecessary.

## Install over USB

Stop an existing dashboard using **Dashboard: Stop** before upgrading. Connect
USB storage, then run on the Mac from the repository root:

```sh
sh kindle/install-usb.sh /Volumes/Kindle
```

The installer copies scripts into `extensions/kindle-ha-dash/` and four library
scriptlets into `documents/`. It preserves an existing `config.sh`, or creates
one from the example. Edit `extensions/kindle-ha-dash/config.sh` on the mounted
Kindle: set `BASE_URL` to the HTTPS origin/base path and `TOKEN` to the integration
token. Do not append `/api/kindle_dash/...` to the base URL. Keep Unix LF endings,
quote shell values, and keep this trusted shell configuration private.

Safely eject and disconnect USB storage. The library entries are **Dashboard:
Self-test**, **Refresh once**, **Start**, and **Stop**. Use the stock Wi-Fi settings
to save a usable network first; the client does not provision networks.

Read `kindle-ha-dash-selftest.txt` and
`extensions/kindle-ha-dash/dashboard.log` by reconnecting USB. Preserve the log
and its `.old` rotation when investigating. USB storage can invoke the stock
USB screen; it is not a reliable way to observe an unplugged suspend cycle.

The older SSH installer (`install.sh`) and KUAL descriptors remain optional
legacy tooling. They are not the installation or recovery path for this target.

## First test and recovery

1. Tap **Self-test** while the dashboard is stopped and Wi-Fi is enabled.
2. Reconnect USB and read `kindle-ha-dash-selftest.txt`.
3. Eject, tap **Refresh once**, then check the image and log. This fetches and
   draws once, restores settings, and exits without auto-entering screensaver.
4. Tap **Start** for the continuous loop. It launches in the background; confirm
   `dashboard started` in the log. Stop the loop before running another test.
5. Test several unplugged timed wakes before relying on unattended operation.

Self-test shares the singleton lock and refuses a running dashboard. It reads
firmware, display info, RTC nodes, exact powerd state/status, frontlight, Wi-Fi,
battery, USB power and tool versions. **RTC checks are read-only:** no alarm is
cleared/programmed and no suspend, redraw, Wi-Fi toggle or light change occurs.
The HTTPS probe sends no token to the BASE_URL root. A root 404 can demonstrate
transport completion; it does not validate the authenticated image endpoint.
A failed probe/configuration returns nonzero. Self-test cannot prove timed wake.

**Stop** sets `/mnt/us/kindle-ha-dash.stop`, signals only a PID verified against
its command line, waits up to ten seconds, then may kill that verified process.
It requests Wi-Fi on, restores frontlight and `preventScreenSaver=0`, and restores
any jobs recorded by a legacy once-only framework experiment. A new explicit
Start/Refresh once removes an old stop flag. If needed, create the stop flag over
USB; a suspended CPU cannot inspect it until the next wake. No startup hook is
installed, so rebooting does not launch the dashboard.

The original light setting survives crashes in
`extensions/kindle-ha-dash/frontlight.saved`. Stop restores it even when no
process remains; successful restoration removes the file, and failure retains
it for another Stop attempt. Do not delete it before restoration. SIGKILL/power
loss cannot run a shell cleanup trap, so use Stop after a crash.

## Powerd cycle

Raw kernel suspend was removed after the real device failed around suspend/wake
with VFP/undefined-instruction and Wi-Fi trouble. The loop does **not** write
`/sys/power/state`, call `rtcwake`, or program `/sys/class/rtc/*/wakealarm`.
Amazon's powerd and framework own suspend/resume.

Start performs one initial fetch/display. With `AUTO_SCREENSAVER=1`, its first
successful display may request `powerButton 1` once while Active, falling back
to `powerd_test -p` if the setter fails and state is still Active. It waits for
confirmation and never repeatedly toggles the button. Stock screensaver/airplane
icon painting can overwrite the image, so cached partial repaints run after
entering screensaver, returning to screensaver, wake and Wi-Fi-off delays.
If the initial fetch fails while Active, retries wait for manual or idle
screensaver entry. Use Refresh once after Stop to diagnose the connection.

The loop reads both `com.lab126.powerd state` and `status`, preserving their exact
output in diagnostics. Successful `state` reads classify Active separately from
ScreenSaver/ReadyToSuspend/Suspended. **Scheduled fetches and repaints pause while
Active or unknown**, including debug/USB/charging awake mode. The initial cycle
and Refresh once are explicit exceptions. The power button remains under user
control after initial entry; the loop does not force the user back into sleep.

It waits with:

```sh
lipc-wait-event -s 5 com.lab126.powerd readyToSuspend,wakeupFromSuspend,resuming
```

The timeout is configurable. Events are parsed by their first field; arguments
and raw CLI output are logged. State polling catches transitions missed during
work. A missing event tool falls back to polling, which cannot guarantee catching
the ready window. Broken commands/event storms have a minimum pause to avoid spin.

At ReadyToSuspend the client sets **relative seconds** using
`lipc-set-prop -i com.lab126.powerd rtcWakeup <seconds>`. The value is the remaining
wall time until the scheduled target, with a minimum interval floor. It re-arms
on ready notifications/polls. `RTC_WAKEUP_MODE=epoch` and
`RTC_WAKEUP_USE_INT=0` are experimental compatibility overrides, not target
recommendations. Successful setter exit is not proof that hardware will wake.
After wake it records relevant dmesg lines, settles, rechecks state, and fetches
only when due while still in screensaver. Early wakes can repaint the cache and
skip downloading. A much longer empty event wait also triggers inferred-wake
diagnostics, settling and a state-checked repaint; this can indicate suspend or a
clock correction and is not proof of an RTC wake.

During a scheduled cycle `CYCLE_ABORT_SUSPEND=1` starts a **finite** background
heartbeat. Every five seconds, only while still in screensaver and specifically
ReadyToSuspend, it arms a safety wake then writes `abortSuspend 1`. A cycle that
starts Ready receives the same protection immediately. The guard budget derives
from configured Wi-Fi attempts, HTTP timeout, redraw delays and a margin. It
stops after work or its deadline. No persistent suspend flag is held.
This behavior is researched on other Kindles, **not verified on this PW3
firmware**; inspect setter results and state transitions during device tests.

`SUSPEND_DEFER_MODE=none` is the default; its only alternative is `deferSuspend`.
That optional mode writes a finite computed value and refuses cycle work if it
leaves screensaver. Published projects disagree about its state effect, and units
and behavior require firmware validation. `CYCLE_ABORT_SUSPEND` is a separate
switch; setting defer mode to none does not disable the heartbeat. The client
never uses `suspendGrace`. `STOP_FRAMEWORK=1` is refused for the loop and allowed
only for the legacy Refresh once experiment; retain `0` on this target.

There is no verified powerd alarm cancellation operation.
`RTC_WAKEUP_CANCEL_MODE=none` therefore makes no cancellation write on Stop: a
**single previously armed wake may remain**, but the stopped client cannot fetch.
The optional `zero` mode experimentally writes `rtcWakeup 0`; neither success
nor that value's cancellation semantics are proven on the target firmware.

## Other behavior and configuration

The example config lists all switches, command and path overrides. All numeric
settings accept unsigned decimal values up to nine digits; invalid limits refuse
startup. Defaults are 30-minute fallback, 60-second minimum, two-hour maximum,
30 seconds per Wi-Fi attempt, two retries after the first attempt, 45-second HTTP
timeout, 10% battery cutoff, and a five-minute awake interval cap.

Debug flag `/mnt/us/kindle-ha-dash.debug`, charging or detected USB power selects
awake mode: Wi-Fi stays enabled, radio off/on retries are suppressed and the
interval is capped. A real ready event still arms a safety wake. At each
observed ready transition awake mode also
requests `abortSuspend 1` to keep the CPU awake. This hold is independent of
`CYCLE_ABORT_SUSPEND` and lasts while the awake override remains; charging usually
prevents ready itself. Check `awake mode: abortSuspend hold rc=`: if rejected,
CPU-awake behavior is unconfirmed and powerd may suspend despite the flag.
Remove the flag and unplug power to measure ordinary battery behavior. Returning
to screensaver disables Wi-Fi unless an awake override applies. Below the battery
cutoff, downloads are skipped and the next
interval is MAX; awake mode can shorten it. Unknown battery is sent as an empty
value and does not activate the cutoff.

`FRONTLIGHT_OFF=1` saves LIPC `flIntensity` and requests zero at startup and each
cycle. **On PW3, LIPC zero may merely dim the hardware**, according to KOReader's
model-specific handling. This client does not reproduce KOReader's raw hardware
light writes. Check the physical light and stock UI when measuring consumption;
`FRONTLIGHT_OFF=0` disables this client's save/zero step.

Only HTTP 200 plus the complete eight-byte PNG signature replaces the cache.
Failures preserve the previous image and show a status line where drawing is
allowed. This is not full PNG decoding: dimensions, grayscale and integrity are
the server's contract. Header names are case-insensitive; invalid/missing
`X-Sleep-Seconds` uses the fallback and all intervals are clamped. Only
`X-Full-Refresh: 1` requests a flashing full refresh. Time is measured after a
cycle, rather than maintaining a fixed wall-clock grid.

curl discovery checks extension `bin/curl`, `/mnt/us/usbnet/bin/curl`, then PATH.
No curl binary is bundled and USBNetwork is not required. Override
`HTTP_CLIENT_BIN` for a compatible binary and `CA_BUNDLE` for a trust bundle.
`INSECURE_TLS=1` disables identity checks and can expose the token to an
impersonating server; it does not fix unsupported TLS protocols. Redirects are
not followed. Request URLs, tokens and curl stderr are not logged; avoid `sh -x`
and do not paste config into reports.

Cache/PID/temporary files default to RAM under `/tmp/kindle-ha-dash`; logs and
the light recovery file persist in the extension. Keep temp/cache on the same
filesystem for atomic replacement. Stop before changing runtime paths. Stale
locks recover on launch after process-identity checks. Never delete a live lock.

## Troubleshooting over USB

| Log evidence / symptom | Check |
| --- | --- |
| `startup refused: configure HTTPS BASE_URL, TOKEN and HTTP client` | Config values, curl discovery, readable CA bundle; use Self-test. |
| `startup refused: another instance or lock recovery in progress` | Tap Stop, then retry Start. Do not remove a live lock. |
| `startup refused: powerd screensaver mode requires STOP_FRAMEWORK=0` | Set `STOP_FRAMEWORK=0`. |
| `auto screensaver not confirmed; no further button presses; waiting for user/idle` | Inspect exact `powerd snapshot` state/status; manually enter screensaver once. |
| `active: scheduled fetching paused; power button remains under user control` | Expected while using the stock UI, even in awake mode; return to screensaver. |
| `unknown powerd state: scheduled fetching paused` | Inspect state/status output and return codes; do not infer state from other status fields. |
| `rtcWakeup arm target=` and `powerd set property=rtcWakeup` | Check remaining/mode/int and setter rc/output. Test an unplugged timed wake; a successful write alone is insufficient. |
| `rtcWakeup failed: timeout/poll fallback only while CPU runs; timed wake unconfirmed` | Check ready state and LIPC output; ordinary polling cannot wake a suspended CPU. |
| `lipc-wait-event missing: polling state every` | Check self-test tool discovery; polling may miss the ready window. |
| `cycle skipped: suspend guard failed` / `deferSuspend left screensaver; cycle refused` | Inspect abort/defer setter diagnostics and transitions; retain defer mode none. Firmware behavior needs validation. |
| `early wake: fetch skipped` | Expected before target; inspect clock/target and later due event. |
| `awake mode: abortSuspend hold rc=` | Confirm zero and unchanged locked state when testing the debug flag. A failed hold can permit suspend; RTC safety arming is attempted separately. |
| `inferred wake: wait_elapsed=` | Empty wait exceeded its expected wall time; save diagnostics, and distinguish suspend from a clock change. |
| `wake dmesg rc=` | Save undefined-instruction, ar6003, suspend and PM lines with nearby power/event logs. |
| `wifi connection timeout elapsed=` | Check saved network and `wifi state=[...]`; adjust Wi-Fi/resume budgets if needed. |
| `fetch failed client_exit=` / `fetch rejected http=` | Check Self-test time/CA/TLS and authenticated Refresh once. Common curl exits: 6 DNS, 7 connection, 28 timeout, 35 TLS, 60 certificate. |
| Stock image/icon overwrites dashboard | Inspect `repaint reason=` and delays; keep framework running. |
| `frontlight restore failed; saved file retained for Stop retry` | Tap Stop again and inspect setter output; retain `frontlight.saved`. |

PW3 USB-power detection assumes
`/sys/devices/system/wario_charger/wario_charger0/connected`; charging has a
separate fallback node. Confirm Self-test while powered, including at full battery.
Display assumes 1072×1448 and eips status row 59 when row discovery fails. FBInk
is optional and falls back to eips; verify partial/full output and status text
on the actual device. No RTC device path is needed for normal operation.
Battery age, light, association time and actual suspend dominate consumption;
no weeks/months battery-life claim is validated. Measure unplugged discharge.

## Host verification and sources

```sh
sh kindle/tests/run.sh
dash kindle/tests/run.sh
find kindle -name '*.sh' -exec sh -n {} \;
# If installed:
shellcheck -s sh kindle/install.sh kindle/extensions/kindle-ha-dash/bin/*.sh kindle/tests/run.sh
```

Host tests use temporary fixtures and fake commands, with no Kindle/server
contact. They exercise parsing, fetch preservation, locking, power states,
events and bounded guards. They do not establish PW3 firmware behavior, actual
RTC wake, Wi-Fi recovery, light-off or display correctness.

Primary implementation references:

- [Online Screensaver scheduler](https://github.com/alextrical/KindleOnlineScreensaver/blob/main/bin/scheduler.sh),
  [update](https://github.com/alextrical/KindleOnlineScreensaver/blob/main/bin/update.sh)
  and [event/RTC helpers](https://github.com/alextrical/KindleOnlineScreensaver/blob/main/bin/utils.sh)
  show locked image updates, Wi-Fi handling and ready-window scheduling. Its
  large defer values are not a bounded guard recipe for this firmware.
- [KOReader Kindle power handling](https://github.com/koreader/koreader/blob/master/frontend/device/kindle/powerd.lua)
  establishes relative RTC seconds, ready-only programming, state checks after
  wake, and the PW3 light-zero caveat. [Its event reader](https://github.com/koreader/koreader-base/blob/master/input/input-kindle.h)
  shows `-m -s 0` for an indefinite stream and event names followed by arguments.
  This client's timed single-event waits also poll state.
- [KindleCron abort guard](https://github.com/lennardollesch/KindleCron/blob/main/kron/keepawake.go)
  and [scheduler](https://github.com/lennardollesch/KindleCron/blob/main/kron/daemon.go)
  support the finite abortSuspend approach. The project reports KT4/PW4 tests;
  applying this behavior to PW3 5.16.2.1.1 remains an inference to verify.
- [kindle-dash Paperwhite issue #25](https://github.com/pascalw/kindle-dash/issues/25)
  demonstrates missing framework/RTC paths on a reported PW3. Kindle 4 raw
  suspend assumptions are not portable evidence for this target.

The client is original shell code; no source from these projects is vendored.
