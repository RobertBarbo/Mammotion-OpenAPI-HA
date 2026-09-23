# Cautious real-device test checklist

Automated tests use mocked responses only. Do not run command tests unless you are physically near the mower, can stop it safely, and the mowing area is clear. Never share real device IDs, credentials, tokens, or unredacted logs in a public issue.

For each command, record the mower's raw `status`, `chargeStatus`, `online`, and Home Assistant lawn-mower activity before and after. Test the following one at a time, only when its starting state is safe:

| Command | Current evidence | What to verify locally |
| --- | --- | --- |
| `PAUSE` | Confirmed via shell | HA button pauses an active task; note returned status. |
| `RESUME` | Confirmed via shell | HA button resumes a paused task; note returned status. |
| `CMD_START` | Not live-confirmed here | Default start behavior and resulting status. |
| `START` | Payload documented with `taskName`; not live-confirmed here | Returned plan name or manual fallback starts the intended saved task. |
| `STOP` | Not live-confirmed here | Stops task without an unintended return. |
| `RETURN` | Not live-confirmed here | Returns to dock; note statuses during return and on dock. |
| `CANCEL_RETURN` | Not live-confirmed here | Cancels return without unintended movement. |

Also verify that an empty plan list keeps the manual task-name field usable, changing the polling interval reloads the integration, Refresh data does not activate a mower, and RTK has diagnostics/refresh but no mower controls. Please report only sanitized observations; we will add status mappings after real evidence.
