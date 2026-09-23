"""Constants for the Mammotion OpenAPI integration."""

DOMAIN = "mammotion_openapi"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
PLATFORMS = ("lawn_mower", "sensor", "binary_sensor", "button", "text", "select")

# Keep scheduled polling conservative until official rate limits are known.
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL_MINUTES = 5
UPDATE_INTERVAL_CHOICES = (5, 10, 15)
MAX_CONCURRENT_DETAILS = 5
RTK_STATION_MODEL = "RtkRefStationV1"
