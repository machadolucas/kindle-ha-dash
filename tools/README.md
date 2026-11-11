# Development and offline previews

The development environment pins CPython 3.14.2, Home Assistant 2026.11.0,
Pillow 13.0.0 (HA's core pin), and pytest-homeassistant-custom-component 0.13.375.
`uv.lock` locks the complete environment. The integration itself does not ship
or pin a second Pillow installation.

```sh
uv sync --locked
uv run ruff check
uv run mypy
uv run pytest
uv run python tools/preview.py --fixtures tests/fixtures --now 2026-11-11T14:31:00+02:00 --out out/preview.png
uv run python tools/preview.py --fixtures tests/fixtures --now 2026-11-11T14:31:00+02:00 --next-wake-minutes 45 --out out/preview.png
uv run python tools/preview.py --fixtures tests/fixtures --now 2026-11-11T14:31:00+02:00 --all
```

`--next-wake-minutes` sets the viewing window used to round the dishwasher's
whole-hour delay from its midpoint. It defaults to 30; use 60 for a night refresh.

`out/` is ignored by git. All nine scenarios derive copies of captured fixtures;
none modify `tests/fixtures/*.json`. The preview loader imports only the pure
models, parser and renderer, so it can also run in a Pillow-only environment
without Home Assistant installed.

## Temporary test-plugin compatibility boundary

As of this implementation, the latest published custom-component plugin,
0.13.375, targets HA 2026.10.4; there is no published 2026.11-matching release.
The uv dependency override deliberately tests the real HA 2026.11.0 package.
`tests/conftest.py` supplies only two import adapters:

1. Load HA before respx so HA can install its required httpx2 aliases.
2. Supply the plugin's removed logger-test helper, which raises if used. None of
   these tests exercise that helper.

There are no compatibility patches to integration behavior or mocked substitutes
for HA config flows/entities/HTTP routing. Replace the plugin pin and remove the
adapters when a compatible release is published. The old plugin's unused
Voluptuous dependency is not used by the integration, whose schemas use probatio.
Third-party HA/aiohttp/backoff deprecation warnings are visible in pytest output.

## Validation

`.github/workflows/validate.yml` runs official hassfest, HACS integration validation,
Ruff, mypy, pytest, and all preview scenarios. The tests use local HA fixtures and
an unauthenticated loopback HTTP client, never an external Home Assistant or a
Kindle on the network.

The HA 2026.11.0 source validator was also run locally against this integration:
24 integration validation plugins completed with **0 invalid integrations**.
The upstream HACS manifest schemas and local brand asset presence passed locally.
The full HACS action additionally checks public GitHub repository metadata
(description/topics/issues/license) and the repository information file; those
checks require the code to be present on GitHub and are not a local pass claim.
