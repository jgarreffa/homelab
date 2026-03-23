import requests
from datadog_checks.base import AgentCheck

__version__ = "1.0.0"


class WeatherCheck(AgentCheck):
    """
    Custom Datadog Agent check that fetches current weather from OpenWeatherMap
    and submits the following metrics:

      - weather.temperature       (°C)
      - weather.feels_like        (°C)
      - weather.temp_min          (°C)
      - weather.temp_max          (°C)
      - weather.humidity          (%)
      - weather.wind_speed        (m/s)
      - weather.cloud_cover       (%)
      - weather.visibility        (metres)

    And a service check:
      - weather.api.can_connect   (OK / CRITICAL)
    """

    SERVICE_CHECK_NAME = "weather.api.can_connect"
    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    def check(self, instance):
        api_key = instance.get("api_key")
        city    = instance.get("city", "Eltham,AU")
        tags    = instance.get("tags", []) + [f"city:{city}"]

        if not api_key:
            self.service_check(
                self.SERVICE_CHECK_NAME,
                AgentCheck.CRITICAL,
                tags=tags,
                message="Missing api_key in weather_check.yaml",
            )
            return

        try:
            response = requests.get(
                self.BASE_URL,
                params={
                    "q":     city,
                    "appid": api_key,
                    "units": "metric",   # Celsius
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            main  = data.get("main", {})
            wind  = data.get("wind", {})
            clouds = data.get("clouds", {})

            self.gauge("weather.temperature",  main.get("temp"),       tags=tags)
            self.gauge("weather.feels_like",   main.get("feels_like"), tags=tags)
            self.gauge("weather.temp_min",     main.get("temp_min"),   tags=tags)
            self.gauge("weather.temp_max",     main.get("temp_max"),   tags=tags)
            self.gauge("weather.humidity",     main.get("humidity"),   tags=tags)
            self.gauge("weather.wind_speed",   wind.get("speed"),      tags=tags)
            self.gauge("weather.cloud_cover",  clouds.get("all"),      tags=tags)
            self.gauge("weather.visibility",   data.get("visibility"), tags=tags)

            self.service_check(self.SERVICE_CHECK_NAME, AgentCheck.OK, tags=tags)

        except requests.exceptions.HTTPError as e:
            self.service_check(
                self.SERVICE_CHECK_NAME,
                AgentCheck.CRITICAL,
                tags=tags,
                message=f"HTTP error fetching weather: {e}",
            )
        except Exception as e:
            self.service_check(
                self.SERVICE_CHECK_NAME,
                AgentCheck.CRITICAL,
                tags=tags,
                message=str(e),
            )
