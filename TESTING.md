# Cautious real-device test checklist

Automated tests use mocked responses only. Do not run command tests unless you are physically near the mower, can stop it safely, and the mowing area is clear. Never share real device IDs, credentials, tokens, or unredacted logs in a public issue.

For each command, record the mower's raw `status`, `chargeStatus`, `online`, and Home Assistant lawn-mower activity before and after. Test the following one at a time, only when its starting state is safe:

| Command | Current evidence | What to verify locally |
| --- | --- | --- |
| `PAUSE` | Confirmed on a real LUBA 2 via the official Open API | HA button pauses an active task; note returned status. |
| `RESUME` | Confirmed on a real LUBA 2 via the official Open API | HA button resumes a paused task; note returned status. |
| `CMD_START` | Not live-confirmed here | Default start behavior and resulting status. |
| `START` | Confirmed on a real LUBA 2 with a saved task name (`taskName`); no confirmation without one | Returned plan name starts the intended saved task. |
| `STOP` | Confirmed on a real LUBA 2 via the official Open API | Stops task without an unintended return. |
| `RETURN` | Confirmed on a real LUBA 2 via the official Open API | Returns to dock; note statuses during return and on dock. |
| `CANCEL_RETURN` | Not live-confirmed here | Cancels return without unintended movement. |

Observed on the real LUBA 2: `Mowing` while mowing, `TaskPaused` while paused or charging, `Returning` while heading to the dock, and `Standby` after `STOP`. `chargeStatus: 0` was observed off dock; `chargeStatus: 2` while docked/charging.

**Safety:** `GET /v1/mower/{deviceId}/work-params` unexpectedly started mowing on the real LUBA 2. Do not treat it as a safe read-only call; automatic polling and Refresh data must not call it. Verify commands cautiously at the mower and share only sanitized observations.
