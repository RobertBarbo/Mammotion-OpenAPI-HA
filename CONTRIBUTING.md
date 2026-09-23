# Contributing

Thanks for helping make Mammotion OpenAPI safer and more useful.

Keep all communication with Mammotion devices inside the official Open API. Do not add PyMammotion, MQTT, Bluetooth, reverse-engineered endpoints, undocumented response fields, or code copied from another Mammotion integration. Link to official documentation or supply a sanitized observation when proposing a new field or action mapping.

Never commit or paste a Client ID, Client Secret, access/refresh token, Authorization header, real device ID, account data, or unredacted diagnostic export. Use fictional names and IDs in tests. Do not run action tests against live equipment as part of CI.

Before a pull request, run:

```sh
python -m pip install aiohttp voluptuous
python -m unittest discover -s tests -q
```

Describe the Home Assistant version you tested, the device category (mower or RTK reference station), and any official API evidence relevant to the change. For command changes, say whether you tested them physically near the mower; never imply a command was live-verified when it was only mocked.
