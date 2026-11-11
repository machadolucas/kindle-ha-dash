"""Integration defaults, shared with the offline preview."""

DOMAIN = "kindle_dash"
DEFAULT_SCHEDULE = "08:30-00:00 30\n00:00-08:30 60"
DEFAULT_ENTITIES = {
    "weather_entity": "weather.forecast_home",
    "outdoor_temperature_entity": "sensor.outdoor_sensor_temperature",
    "outdoor_humidity_entity": "sensor.outdoor_sensor_humidity",
    "indoor_temperature_entity": "sensor.average_temperature_inside",
    "prices_entity": "sensor.nordpool_fi_day_ahead",
    "tomorrow_available_entity": "binary_sensor.nordpool_tomorrow_prices_availability",
    "price_forecast_entity": "sensor.lvv_price_forecast",
    "dishwasher_entity": "sensor.dishwasher_schedule",
    "dishwasher_running_entity": "binary_sensor.dishwasher_running_2",
}
DEFAULT_OPTIONS = {
    **DEFAULT_ENTITIES,
    "schedule": DEFAULT_SCHEDULE,
    "default_interval": 60,
    "offset_seconds": 60,
    "full_refresh_every": 4,
    "grace_minutes": 120,
}
