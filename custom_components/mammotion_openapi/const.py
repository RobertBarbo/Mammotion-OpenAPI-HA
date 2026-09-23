"""Constants for the Mammotion OpenAPI integration."""

from datetime import timedelta

DOMAIN = "mammotion_openapi"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
PLATFORMS = ("lawn_mower", "sensor", "binary_sensor", "button", "text")

# One list request plus one detail request per mower on each refresh.
UPDATE_INTERVAL = timedelta(minutes=5)
MAX_CONCURRENT_DETAILS = 5
