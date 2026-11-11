# Kindle dashboard

A Home Assistant 2026.11 custom integration for a Kindle Paperwhite 3. It renders
1072×1448 grayscale PNGs containing weather, a prominent dishwasher recommendation,
and quarter-hour electricity prices. It does not control the dishwasher.

## Installation and setup

Copy this `kindle_dash` directory into Home Assistant's `custom_components/`,
restart Home Assistant, then add **Kindle dashboard** in Settings → Devices &
services. HACS custom repositories can install the same directory.

Select the source entities in the setup flow. Defaults target the captured
Nord Pool, LVV, weather and dishwasher entities in this repository. The source
schemas are specific to these entities; another price integration may need an
adapter. Temperatures are displayed in the source installation's Celsius units.
Prices are expected in EUR/kWh and displayed in c/kWh. Forecast values extend
the last official interval and never replace official prices.

Open Configure to see the generated token and the full image/status paths. Add
your Home Assistant base URL before the path, then configure the Kindle client
with it. Treat the URL as a bearer credential. Regenerate it in Configure if
needed, then update the client. Use `?preview=1` for browser previews, including
if supplying battery query parameters: previews never change monitoring or
full-refresh cadence.

The image endpoint accepts optional `battery=0..100`, `charging=0|1`, and a client
identifier up to 128 characters. Only requests containing battery count as Kindle
check-ins. Every non-preview image request advances the full-refresh counter;
the first request and every Nth request request a full refresh. Status requests
never advance it. Rendering errors produce a readable error PNG and a five-minute
retry instruction.

The integration redacts token-bearing paths in HA's view debug logger and the
standard aiohttp access logger. Independently configured reverse proxies must
also redact or omit these paths in their access logs.

## Wake schedule

One period per line, in Home Assistant's configured time zone:

```text
08:30-00:00 30
00:00-08:30 60
```

Each line is `HH:MM-HH:MM interval_minutes`; intervals must be 5–720 minutes.
`00:00` at the end means the end of the day. Wrapping periods such as
`22:00-06:00 60` are valid. Overlapping periods are rejected. Gaps use the default
interval, anchored at each gap's beginning. The default 60-second offset lets
new price slots settle before the client fetches them. A strict two-minute
minimum gap avoids very short sleeps when a client checks in late.

Wall-clock grids skip nonexistent spring times and include both occurrences
of repeated autumn times. The HTTP sleep duration uses elapsed UTC seconds.
Civil-day price charts likewise contain 92 or 100 slots on DST transition days,
rather than forcing a 96-slot day.

## Monitoring and persistence

The single **Kindle dashboard** device represents physical Amazon hardware, so
its device registry `entry_type` is `None`, not `SERVICE`. It has battery,
last-seen and next-expected sensors, plus charging and check-in problem binary
sensors. A problem is raised at next expected check-in plus the configured grace
(default two hours), even if the Kindle sends no more requests.

One private HA Store atomically persists battery, charging, last seen and next
expected check-in. It is loaded before platform setup, so entity restoration
order, disabled entities, reloads and restarts cannot erase the deadline. Entity
base classes support restore state too; the Store remains the authoritative
record. Full-refresh cadence is intentionally reset on integration setup.

Options use `OptionsFlowWithReload`, without an update listener. Runtime state
lives exclusively in the typed config entry's `runtime_data`. Rendering, font
loading and PNG encoding run in HA's executor. Pillow is not an extra requirement:
HA 2026.11.0 already pins Pillow 13.0.0. Noto Sans Regular and Bold are bundled
under the SIL OFL; see `fonts/OFL.txt`.

Remove the integration in Settings → Devices & services to remove its entities
and persisted check-in record. Remove the installed directory/HACS repository
if you also want to uninstall the code.

## API references checked for 2026.11

- [Options flows and automatic reload](https://developers.home-assistant.io/docs/config_entries_options_flow_handler/)
- [Typed config-entry runtime data and platform setup](https://developers.home-assistant.io/docs/config_entries_index/)
- [Device registry identity and entry types](https://developers.home-assistant.io/docs/device_registry_index/)
- [Sensor native-value restoration](https://developers.home-assistant.io/docs/core/entity/sensor/)
- [Blocking operations and executor jobs](https://developers.home-assistant.io/docs/asyncio_blocking_operations/)
- [2026 entity lifecycle hooks and in-place renaming](https://developers.home-assistant.io/blog/2026/10/12/new-entity-lifecycle-hooks/)
- [Do not combine reload flows with entry listeners](https://developers.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/)
- [Store serialization thread opt-in](https://developers.home-assistant.io/blog/2025/11/25/storage-helper-opt-in-serialize-in-executor/)

Implementation was additionally checked against the installed HA 2026.11.0
source for HTTP views, selectors, weather response actions, scheduling callbacks,
entity lifecycle and Store APIs. Entity selectors use the modern nested `filter`
key rather than the legacy top-level domain filter.
