# Mammotion OpenAPI for Home Assistant

An early-stage Home Assistant custom integration using **only Mammotion's official Open API**. It does not use PyMammotion, MQTT, Bluetooth, reverse-engineered protocols, or another Mammotion integration's code. This is a community project, not an official Mammotion product.

The integration supports multiple devices on one Mammotion account. An observed `RtkRefStationV1` reference station is registered as a device with available diagnostics, but it does **not** receive mower controls.

## Before installing

- Obtain a Mammotion Open API Client ID and Client Secret through Mammotion's developer program.
- Link your devices to the account used for those credentials in the official Mammotion app.
- Use a Home Assistant version with the `lawn_mower` platform. The integration has been tried on Home Assistant Core 2026.9.2; older releases have not yet been verified end-to-end. Native Stop support is feature-detected where available, and the custom Stop action remains available otherwise.
- Treat this as an early-stage integration. `PAUSE`, `RESUME`, `STOP`, `RETURN`, and `START` have been reported to work on a real mower; test any other exposed command carefully at the device.

## Install

### Manually

Copy `custom_components/mammotion_openapi` into your Home Assistant configuration's `custom_components/` directory, restart Home Assistant, then go to **Settings → Devices & services → Add integration → Mammotion OpenAPI**. Enter your Client ID and Client Secret there. Never paste them into an issue or a public repository.

### HACS custom repository

Add [RobertBarbo/Mammotion-OpenAPI-HA](https://github.com/RobertBarbo/Mammotion-OpenAPI-HA) as a **custom repository** in HACS with category **Integration**. Install Mammotion OpenAPI from HACS, restart Home Assistant, and add the integration through **Settings → Devices & services**. Later tagged releases can be installed as normal HACS updates.

## What appears in Home Assistant

- One `lawn_mower` entity per mower, with the supported HA controls.
- Battery/status sensors and observed network/charge diagnostic sensors when the API supplies values.
- Online/network binary sensors where data is present. The RTK reference station currently has an Online diagnostic binary sensor when reported by the API.
- Seven buttons on each mower's device page for the known Open API actions: `CMD_START`, `START`, `PAUSE`, `RESUME`, `STOP`, `RETURN`, and `CANCEL_RETURN`.
- A **Saved task** dropdown when the official plan endpoint returns named tasks. Choosing one only updates a local selection; pressing **Start named task** sends `START` with that task name.
- A local task-name text input remains as fallback for mowers with no returned plans. When both are present, a currently valid dropdown choice takes precedence. The selection and text are cleared when the integration reloads.
- A **Refresh data** button on each device, including RTK. It only polls the API and never sends a mower command. A diagnostic **Last successful update** timestamp shows when device detail was last retrieved successfully.
- Optional mower sensors for documented work totals (count, area, estimated time and carbon savings), recorded error-entry count, and energy from the first returned work report. These are independent of the mower's basic state. "First returned" does not imply newest: the API specification does not promise a sort order.

The same seven actions are available as mower-targeted Home Assistant actions (`mammotion_openapi.cmd_start`, `start_task`, `pause`, `resume`, `stop`, `return_to_dock`, and `cancel_return`). `start_task` requires `task_name`. No action should be tested unless someone is physically near the mower and can stop it safely.

The raw `status` and numeric `chargeStatus` values remain visible. `Mowing`/`Working` map to Mowing, `Returning` to Returning, and `Abnormal` to Error when those Home Assistant activities exist. `TaskPaused`/`Paused` map to Paused with `chargeStatus: 0`, but to Docked with confirmed charging/dock values `1` or `2`; `Standby` maps to Idle with `0` when that Home Assistant activity exists, or to Docked with `1` or `2`. Unknown charge codes remain unmapped. The active network sensor displays Wi-Fi for [documented code `"1"` and Cellular for `"2"`](https://developer.mammotion.com/docs/get-device-informations), and retains any unknown code as-is.

In the integration's **Configure** menu, choose a basic-state polling interval of **5, 10, or 15 minutes** (default: 5). Work history and recorded errors are queried separately once per hour to avoid excessive API use. **Refresh data** also requests those optional values for all account mowers; for RTK it refreshes basic data only. Changing the option reloads the integration, so the local task selection/text will be cleared. Mammotion's API rate limits have not been confirmed. A successful command performs a best-effort core refresh; a transient post-command read failure keeps the last known availability until the next regular poll.

## Official API surface

The integration uses the following endpoints from Mammotion's [official OpenAPI specification](https://api-open.mammotion.com/api-docs). The first five have been used in previous phases; the new read-only paths below are implemented from the published schema and mocked tests, **not yet verified against a real account**:

| Purpose | Method and endpoint |
| --- | --- |
| OAuth client credentials | `POST https://id.mammotion.com/oauth2/token` |
| Device list | `GET https://api-open.mammotion.com/v1/mowers` |
| Device detail | `GET https://api-open.mammotion.com/v1/mower/{deviceId}` |
| Saved plans | `GET https://api-open.mammotion.com/v1/mower/{deviceId}/plan` |
| Mower commands | `POST https://api-open.mammotion.com/v1/mower/action` |
| Current work parameters (unsafe; never polled automatically) | `GET https://api-open.mammotion.com/v1/mower/{deviceId}/work-params` |
| Search work reports | `POST https://api-open.mammotion.com/v1/mower/work-reports/search` |
| Summarize work reports | `POST https://api-open.mammotion.com/v1/mower/work-reports/summary` |
| Work report detail | `GET https://api-open.mammotion.com/v1/mower/{deviceId}/work-reports/{workId}` |
| Search recorded error codes | `POST https://api-open.mammotion.com/v1/mower/error-codes/search` |

The `POST` report and error-code search endpoints are queries, not mower commands. `POST /v1/mower/material/fetch` and `POST /v1/devices/subscriptions` are intentionally **not** implemented: the former triggers device upload, and the latter creates a short-lived SSE subscription. The optional history calls do not target RTK and fail independently; they cannot block basic mower status or controls. Mammotion's specification examples show API envelope code `200`, while live responses have used `0`, so all REST methods accept both. Real sanitized responses are still needed to confirm the newer model-specific shapes.

**Safety warning:** A real LUBA 2 unexpectedly started mowing after `GET /v1/mower/{deviceId}/work-params`, which returned `commandResult: true` and `"Command has been sent"`. Home Assistant therefore never calls this path automatically, including on **Refresh data**. Blade-height and work-speed entities based on it are no longer created. Existing registry entries from an older installation may remain unavailable until removed manually. Do not manually call this endpoint unless you are at the mower and prepared for it to start.

The plan endpoint supplies optional task names for the local dropdown. Empty plan lists leave the manual text input usable. A failed plan request retains the last successful list without hiding mower detail; core list or detail authentication failures still trigger reauthentication. Basic state is polled at the configured interval and refreshed after a command. The API client uses Home Assistant's shared `aiohttp` session and renews expiring tokens automatically.

## Diagnostics and privacy

From **Settings → Devices & services → Mammotion OpenAPI**, download entry or device diagnostics when reporting a problem. The diagnostic export allowlists troubleshooting fields and omits device IDs, device names, nicknames, task names, raw HTTP payloads, work-report map URLs, and authorization headers. Client ID and Client Secret are redacted. Access/refresh tokens are not included. **Review any downloaded file before sharing it publicly**, because device model, firmware, status, and signal measurements remain visible.

Do not attach Home Assistant's full configuration, logs containing credentials, or real device IDs to public issues. Use sanitized examples instead.

## Development

The API layer and HA-adapter tests use mocked responses; they never send commands to a real mower. To run the current suite in a Python environment:

```sh
python -m pip install aiohttp voluptuous
python -m unittest discover -s tests -q
```

The HA tests use local stubs rather than a full Home Assistant installation. CI also runs HACS repository validation after publication. Contributions must follow [CONTRIBUTING.md](CONTRIBUTING.md).

Real-device commands have **not** been sent as part of automated tests. A cautious manual checklist is in [TESTING.md](TESTING.md).

## License

[MIT](LICENSE) © 2026 RobertBarbo and contributors.
