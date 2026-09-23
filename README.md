# Mammotion OpenAPI for Home Assistant

An early-stage Home Assistant custom integration using **only Mammotion's official Open API**. It does not use PyMammotion, MQTT, Bluetooth, reverse-engineered protocols, or another Mammotion integration's code. This is a community project, not an official Mammotion product.

The integration supports multiple devices on one Mammotion account. An observed `RtkRefStationV1` reference station is registered as a device with available diagnostics, but it does **not** receive mower controls.

## Before installing

- Obtain a Mammotion Open API Client ID and Client Secret through Mammotion's developer program.
- Link your devices to the account used for those credentials in the official Mammotion app.
- Use a Home Assistant version with the `lawn_mower` platform. The integration has been tried on Home Assistant Core 2026.9.2; older releases have not yet been verified end-to-end. Native Stop support is feature-detected where available, and the custom Stop action remains available otherwise.
- Treat this as an early-stage integration. Only `PAUSE` and `RESUME` have been confirmed against a real mower so far; the other exposed commands should be tested carefully at the device.

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

The same seven actions are available as mower-targeted Home Assistant actions (`mammotion_openapi.cmd_start`, `start_task`, `pause`, `resume`, `stop`, `return_to_dock`, and `cancel_return`). `start_task` requires `task_name`. No action should be tested unless someone is physically near the mower and can stop it safely.

The raw `status` and numeric `chargeStatus` values are kept visible rather than assigning undocumented meanings to them. `Mowing` maps to Mowing; `TaskPaused` maps to Paused. An observed docked mower reported `status: "Standby"` and `chargeStatus: 2`; only that combination is mapped to Docked. Other states stay unmapped where their meaning is unconfirmed. The active network sensor displays Wi-Fi for [documented code `"1"` and Cellular for `"2"`](https://developer.mammotion.com/docs/get-device-informations), and retains any unknown code as-is.

In the integration's **Configure** menu, choose a polling interval of **5, 10, or 15 minutes** (default: 5). Changing this option reloads the integration, so the local task selection/text will be cleared. The refresh button can be used between scheduled polls. Mammotion's API rate limits have not been confirmed.

## Official API surface

The integration uses only these confirmed endpoints:

| Purpose | Method and endpoint |
| --- | --- |
| OAuth client credentials | `POST https://id.mammotion.com/oauth2/token` |
| Device list | `GET https://api-open.mammotion.com/v1/mowers` |
| Device detail | `GET https://api-open.mammotion.com/v1/mower/{deviceId}` |
| Saved plans | `GET https://api-open.mammotion.com/v1/mower/{deviceId}/plan` |
| Mower commands | `POST https://api-open.mammotion.com/v1/mower/action` |

The plan endpoint supplies optional task names for the local dropdown. Empty plan lists leave the manual text input usable. A failed plan request retains the last successful list without hiding mower detail; authentication failures still trigger reauthentication. State is polled at the configured interval and refreshed after a command. The API client uses Home Assistant's shared `aiohttp` session and renews expiring tokens automatically.

## Diagnostics and privacy

From **Settings → Devices & services → Mammotion OpenAPI**, download entry or device diagnostics when reporting a problem. The diagnostic export allowlists troubleshooting fields and omits device IDs, device names, nicknames, task names, raw HTTP payloads, and authorization headers. Client ID and Client Secret are redacted. Access/refresh tokens are not included. **Review any downloaded file before sharing it publicly**, because device model, firmware, status, and signal measurements remain visible.

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
