# Mammotion OpenAPI – Architecture

## Scope and principles

This project will be a Home Assistant custom integration that talks **only**
to Mammotion's official Open API.  API transport and authentication will be
isolated from Home Assistant entities. The first implemented surface used
these previously exercised endpoints:

- `POST https://id.mammotion.com/oauth2/token` for client-credentials tokens
- `GET https://api-open.mammotion.com/v1/mowers`
- `GET https://api-open.mammotion.com/v1/mower/{deviceId}`
- `GET https://api-open.mammotion.com/v1/mower/{deviceId}/plan`
- `POST https://api-open.mammotion.com/v1/mower/action`

The subsequent read-only layer also implements the five officially published
work-parameter, work-report and error-code endpoints listed in the README.
Those newer response shapes are still based on the public specification and
mocked tests, not live device samples. Material upload and subscriptions are
excluded.

No undocumented endpoints or response fields should be assumed.  Entity
features are enabled only when supported by these documented/tested responses.

## Repository layout

```text
Mammotion-OpenAPI-HA/
├── custom_components/
│   └── mammotion_openapi/
│       ├── __init__.py                 # Integration setup/unload
│       ├── manifest.json               # HA and HACS metadata/dependencies
│       ├── const.py                    # Domain, defaults, stable constants
│       ├── config_flow.py              # Client ID/Secret configuration flow
│       ├── coordinator.py              # Per-entry DataUpdateCoordinator
│       ├── read_only_coordinator.py    # Hourly optional read-only API data
│       ├── diagnostics.py              # Redacted diagnostics export
│       ├── lawn_mower.py               # One mower entity per API mower
│       ├── button.py                    # Known command buttons per mower
│       ├── text.py                      # Local task-name input for START
│       ├── select.py                    # Local selection of returned plan names
│       ├── sensor.py                   # Battery, signal and supported details
│       ├── binary_sensor.py            # Online/network availability states
│       ├── brand/
│       │   ├── icon.png                 # Square local HA/HACS icon
│       │   └── logo.png                 # Local HA integration logo
│       ├── translations/
│       │   └── en.json                 # Initial UI strings; extensible later
│       └── api/
│           ├── __init__.py
│           ├── client.py               # Async HTTP client and endpoint methods
│           ├── auth.py                 # Token acquisition/refresh lifecycle
│           ├── models.py               # Typed, API-shaped response models
│           ├── extended_models.py      # Documented report/parameter/error models
│           └── exceptions.py           # API/auth/transport error types
├── tests/
│   ├── __init__.py
│   ├── ha/                              # HA adapter tests and lightweight stubs
│   └── api/
│       ├── test_auth.py
│       └── test_client.py
├── README.md                           # Install, configuration and support
├── hacs.json                           # HACS validation/configuration
├── LICENSE
├── CONTRIBUTING.md
└── .github/workflows/validate.yml      # Mocked tests and HACS validation
```

## Runtime design

Each Home Assistant config entry represents one Mammotion account and stores
the Client ID and Client Secret in Home Assistant's config-entry storage.  The
secret is never placed in entity attributes, logs, exception text, diagnostics,
or test fixtures.

Setup creates one asynchronous `MammotionApiClient` and one
`MammotionDataUpdateCoordinator` for that entry.  The client owns `aiohttp`
communication, token acquisition via the client-credentials grant, authorization
headers, timeout handling, and conversion of responses into API models.  It
exposes methods corresponding only to the endpoints listed above and the five
additional documented read-only paths.

The coordinator polls `GET /v1/mowers`, then retrieves detail for every device
returned by that list. For mower records, it also retrieves the confirmed plan
list so a local saved-task selector can show returned task names. Empty lists
are valid; RTK stations are not queried for plans. Coordinator data is keyed
by the official device `id`, so one account supports multiple devices.

A second coordinator polls optional historical reports and recorded error codes
at most hourly; the manual Refresh data button can request an earlier update.
The documented `/work-params` GET unexpectedly triggered mowing on a real
device and is never called automatically. Each optional endpoint fails
independently so an unsupported model or transient failure cannot disable
basic mower controls. The RTK station is never queried for mower work history.
Report map URLs and other media resources are not exposed as HA entity
attributes or diagnostics.

The `/v1/mowers` response can also contain an RTK reference station. Keep it
registered as a Home Assistant device; future mower platforms must not attach
mower controls to it. No undocumented device-type field is assumed.

Platforms subscribe to that coordinator rather than making their own requests:

- `lawn_mower`: one entity for each device not identified as the observed RTK
  station model. Home Assistant's start, pause, and dock controls use the known
  official `CMD_START`/`RESUME`, `PAUSE`, and `RETURN` actions respectively.
  `START` requires a saved task name and is not used as a generic start action.
  Separate mower-targeted Home Assistant actions expose all seven confirmed
  Open API commands. Native `STOP` is enabled only on HA versions that support
  it; older versions retain the integration's stop action.
- `sensor`: detail values already observed, such as battery level, Wi-Fi RSSI,
  cellular RSSI, version, model, and status, where suitable for HA entities.
- `binary_sensor`: observed boolean-style availability values, including online
  state and network availability. A returned RTK station remains a device and
  may receive these entities when the API actually supplies their values.
- `button`: one per confirmed mower command, visible on each mower device;
  the RTK has no command buttons. Every device has a read-only Refresh data
  button that triggers coordinator polling, not a mower command.
- `text`: a local per-mower task-name input for the named `START` button. It
  sends no command when edited and is cleared on integration reload.
- `select`: a local per-mower choice of plan names returned by the API. It is
  absent for empty plan lists; the text input remains available as fallback.

The integration must derive entity unique IDs from the immutable API mower
`id`, never the user-editable name or nickname.  Names and nicknames are
display metadata only.

## Configuration and errors

The config flow asks for Client ID and Client Secret, validates them by
obtaining a token and making an allowed authenticated request, and prevents
duplicate account entries using an account identity only if the official API
provides a stable one.  Until such an identity is confirmed, duplicate handling
must not be invented.

Authentication failures, connectivity failures, timeouts, and malformed API
responses are represented by API-layer exception classes and translated into
Home Assistant setup/update behavior in the coordinator and config flow.

## Diagnostics and testing

Diagnostics contain an allowlisted set of integration and coordinator fields
useful for support. Client ID and Client Secret are redacted; token material,
authorization headers, device IDs/names, task names, raw HTTP headers, and
credential-bearing request bodies are never included.

Tests use mocked HTTP responses captured from the official endpoint shapes and
sanitized before committing.  Coverage should include auth, API error handling,
multiple-mower discovery, config-flow validation, coordinator refreshes,
entities, commands, unload behavior, and diagnostics redaction.
