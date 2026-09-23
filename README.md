# Mammotion OpenAPI for Home Assistant

An early-stage Home Assistant custom integration using **only Mammotion's official Open API**. It does not use PyMammotion, MQTT, Bluetooth, reverse-engineered protocols, or another Mammotion integration's code. This is a community project, not an official Mammotion product.

The integration supports multiple devices on one Mammotion account. An observed `RtkRefStationV1` reference station is registered as a device with available diagnostics, but it does **not** receive mower controls.

## Before installing

- Obtain a Mammotion Open API Client ID and Client Secret through Mammotion's developer program.
- Link your devices to the account used for those credentials in the official Mammotion app.
- Use a Home Assistant version with the `lawn_mower` platform. The integration has been tried on Home Assistant Core 2026.9.2; older releases have not yet been verified end-to-end. Native Stop/Idle support is feature-detected where available, and the custom Stop action remains available otherwise.
- Treat this as a pre-release integration. Only `PAUSE` and `RESUME` have been confirmed against a real mower so far; the other exposed commands should be tested carefully at the device.

## Install

### Manually

Copy `custom_components/mammotion_openapi` into your Home Assistant configuration's `custom_components/` directory, restart Home Assistant, then go to **Settings → Devices & services → Add integration → Mammotion OpenAPI**. Enter your Client ID and Client Secret there. Never paste them into an issue or a public repository.

### HACS custom repository

Once this project is published at `RobertBarbo/Mammotion-OpenAPI-HA`, add that GitHub URL as a **custom repository** in HACS with category **Integration**. Install Mammotion OpenAPI from HACS, restart Home Assistant, and add the integration through **Settings → Devices & services**. HACS distribution is being prepared; the repository and releases have not been published by this README.

## What appears in Home Assistant

- One `lawn_mower` entity per mower, with the supported HA controls.
- Battery/status sensors and observed network/charge diagnostic sensors when the API supplies values.
- Online/network binary sensors where data is present. The RTK reference station currently has an Online diagnostic binary sensor when reported by the API.
- Seven buttons on each mower's device page for the known Open API actions: `CMD_START`, `START`, `PAUSE`, `RESUME`, `STOP`, `RETURN`, and `CANCEL_RETURN`.
- A local task-name text input used by the `START` button. Enter the exact saved task name first. This text is not sent when edited and is cleared when the integration reloads.

The same seven actions are available as mower-targeted Home Assistant actions (`mammotion_openapi.cmd_start`, `start_task`, `pause`, `resume`, `stop`, `return_to_dock`, and `cancel_return`). `start_task` requires `task_name`. No action should be tested unless someone is physically near the mower and can stop it safely.

The raw `status` and numeric `chargeStatus` values are kept visible rather than assigning undocumented meanings to them. An observed docked mower reported `status: "Standby"` and `chargeStatus: 2`; only that combination is mapped to Docked.

## Official API surface

The integration uses only these confirmed endpoints:

| Purpose | Method and endpoint |
| --- | --- |
| OAuth client credentials | `POST https://id.mammotion.com/oauth2/token` |
| Device list | `GET https://api-open.mammotion.com/v1/mowers` |
| Device detail | `GET https://api-open.mammotion.com/v1/mower/{deviceId}` |
| Saved plans | `GET https://api-open.mammotion.com/v1/mower/{deviceId}/plan` |
| Mower commands | `POST https://api-open.mammotion.com/v1/mower/action` |

The plan endpoint is implemented in the standalone API layer; no HA plan entity is exposed yet. State is polled every five minutes and refreshed after a command. The API client uses Home Assistant's shared `aiohttp` session and renews expiring tokens automatically.

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

## License

[MIT](LICENSE) © 2026 RobertBarbo and contributors.
