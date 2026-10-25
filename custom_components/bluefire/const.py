"""BlueFire integration constants."""

DOMAIN = "bluefire"
CONF_VEHICLE_ID = "vehicle_id"
CONF_J1587_EXTENDED = "j1587_extended"
CONF_J1708_STARTUP = "j1708_startup"
CONF_ENGINE_PROFILE = "engine_profile"
ENGINE_PROFILES = {
    "generic": "Standard J1587 (no selected engine)",
    "detroit_series_60_ddec_iv": "Detroit Diesel Series 60 / DDEC IV",
}
DEFAULT_VEHICLE_ID = "liberty_h3_45"
STATUS_RECEIVER_ENABLED = "receiver_enabled"
TELEMETRY_TIMEOUT = 60
J1708_POLL_INTERVAL = 60
J1708_POLL_MAX_BACKOFF = 900
J1708_POLL_TIMEOUT = 180
J1708_POLL_PIDS = (96, 194, 245, 247, 250)
J1708_READ_ACTIONS = {
    "read_fuel_level": 96,
    "read_diagnostic_codes": 194,
    "read_odometer": 245,
    "read_engine_hours": 247,
    "read_total_fuel_used": 250,
    "read_software_identification": 234,
    "read_vehicle_identification": 237,
    "read_component_identification": 243,
}
CAPTURE_SECONDS = 20
MIN_CAPTURE_SECONDS = 5
MAX_CAPTURE_SECONDS = 60
MAX_CAPTURE_NOTIFICATIONS = 5000
MQTT_PUBLISH_TIMEOUT = 15
