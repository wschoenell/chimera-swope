import json
import math
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from time import time

from chimera.instruments.weatherstation import WeatherStationBase
from chimera.interfaces.weatherstation import (
    WeatherHumidity,
    WeatherPressure,
    WeatherRain,
    WeatherSeeing,
    WeatherTemperature,
    WeatherWind,
)

# N 	V 	field 	format
# 1 	tm 	Datetime 	YYYY-MM-DD hh:mm:ss
# 2 	sn* 	Wind speed lull 	Mph
# 3 	sm* 	Wind speed mean 	Mph
# 4 	sx* 	Wind speed gust 	Mph
# 5 	dn* 	Wind direction min. 	degrees
# 6 	dm* 	Wind direction mean 	degrees
# 7 	dx* 	Wind direction max. 	degrees
# 8 	pa* 	Air pressure 	inHg
# 9 	ta* 	Air temperature 	Farenheit
# 10 	ua* 	Relative humidity 	percentage
# 11 	ri* 	Rain intensity 	mm/h


class SwopeWeatherStation(
    WeatherStationBase,
    WeatherTemperature,
    WeatherWind,
    WeatherPressure,
    WeatherHumidity,
    WeatherRain,
    WeatherSeeing,
):
    __config__ = {
        "model": "Swope Weather Station",
        "device": "LCO FastAPI",
        "swope_weather_host": "http://env-api.lco.cl/metrics/weather?source=swope&start_ts=",
        "swope_seeing_host": "http://env-api.lco.cl/metrics/seeing?source=dimm&start_ts=",
        "update_interval": 60.0,  # seconds - how often to fetch fresh data
    }

    def __init__(self):
        WeatherStationBase.__init__(self)
        self._status = None
        self._last_update = None
        self._seeing_status = None
        self._seeing_last_update = None
        # Set control loop frequency to update every 5 minutes
        # Hz = 1/300 seconds = 0.00333... Hz
        self.set_hz(1.0 / 300.0)

    def control(self) -> bool:
        """
        Control loop that periodically updates weather and seeing data.
        This method is called automatically by the chimera framework at the frequency
        set by set_hz() (every 5 minutes = 300 seconds).

        @return: True to continue the control loop, False to stop it
        """
        try:
            # Force update of weather data
            self.log.debug("Control loop: fetching weather data")
            self._last_update = None  # Force fresh fetch
            self.get_status()

            # Force update of seeing data
            self.log.debug("Control loop: fetching seeing data")
            self._seeing_last_update = None  # Force fresh fetch
            self.get_seeing_status()

        except Exception as e:
            self.log.error(f"Error in control loop: {e}")

        # Return True to keep the control loop running
        return True

    def _get_latest_reading(self):
        """Get the most recent weather reading from the cached status"""
        status = self.get_status()
        if not status or "results" not in status or not status["results"]:
            return None
        # Return the most recent reading (last in the list)
        return status["results"][-1]

    def get_last_measurement_time(self) -> str:
        """
        Returns the timestamp of the last measurement taken by the weather station.
        @return: The UTC time of the last measurement as a string in FITS format.
        """
        reading = self._get_latest_reading()
        if not reading or "ts" not in reading:
            raise RuntimeError("No valid weather measurement timestamp available")
        return reading["ts"]

    def temperature(self) -> float:
        """
        Returns the temperature in Celsius.
        @return: the temperature.
        """
        reading = self._get_latest_reading()
        if reading and "temperature" in reading:
            # Convert from Fahrenheit to Celsius: (F - 32) * 5/9
            fahrenheit = reading["temperature"]
            return (fahrenheit - 32) * 5.0 / 9.0
        return 0.0

    def dew_point(self) -> float:
        """
        Returns the dew point temperature in Celsius.
        Note: This is calculated from temperature and humidity since it's not directly provided.
        @return: the dew point temperature.
        """
        reading = self._get_latest_reading()
        if reading and "temperature" in reading and "relative_humidity" in reading:
            # Convert temp to Celsius first
            temp_c = self.temperature()
            humidity = reading["relative_humidity"]

            # Magnus formula approximation for dew point
            a, b = 17.27, 237.7
            alpha = ((a * temp_c) / (b + temp_c)) + math.log(humidity / 100.0)
            dew_point = (b * alpha) / (a - alpha)
            return dew_point
        return 0.0

    def humidity(self) -> float:
        """
        Returns the relative humidity in percentage.
        @return: the humidity.
        """
        reading = self._get_latest_reading()
        if reading and "relative_humidity" in reading:
            return reading["relative_humidity"]
        return 0.0

    def pressure(self) -> float:
        """
        Returns the atmospheric pressure in Pascals.
        @return: the pressure.
        """
        reading = self._get_latest_reading()
        if reading and "air_pressure" in reading:
            # Convert from inHg to Pascals: 1 inHg = 3386.389 Pa
            inhg = reading["air_pressure"]
            return inhg * 3386.389
        return 0.0

    def wind_speed(self) -> float:
        """
        Returns the wind speed in meters per second.
        @return: the wind speed.
        """
        reading = self._get_latest_reading()
        if reading and "wind_speed_avg" in reading:
            # Convert from mph to m/s: 1 mph = 0.44704 m/s
            mph = reading["wind_speed_avg"]
            return mph * 0.44704
        return 0.0

    def wind_direction(self) -> float:
        """
        Returns the wind direction in Degrees.
        @return: the wind direction.
        """
        reading = self._get_latest_reading()
        if reading and "wind_dir_avg" in reading:
            return reading["wind_dir_avg"]
        return 0.0

    def rain_rate(self) -> float:
        """
        Returns the precipitation rate in mm/hour.
        @return: the precipitation rate.
        """
        reading = self._get_latest_reading()
        if reading and "rain_intensity" in reading:
            return reading["rain_intensity"]
        return 0.0

    def is_raining(self) -> bool:
        """
        Returns True if it is raining and False otherwise
        """
        return self.rain_rate() > 0.0

    def _get_latest_seeing_reading(self):
        """Get the most recent seeing reading from the cached seeing status"""
        status = self.get_seeing_status()
        if not status or "results" not in status or not status["results"]:
            return None
        # Return the most recent reading (last in the list)
        return status["results"][-1]

    def seeing(self) -> float:
        """
        Returns the current seeing measurement in arcseconds.
        @return: the seeing value.
        """
        reading = self._get_latest_seeing_reading()
        if reading and "seeing" in reading:
            return reading["seeing"]
        return 0.0

    def seeing_at_zenith(self) -> float:
        """
        Returns the current seeing corrected for the zenith position in arcseconds.
        Uses the formula: seeing_zenith = seeing * (airmass)^(-3/5)
        @return: the seeing at zenith value.
        """
        reading = self._get_latest_seeing_reading()
        if reading and "seeing" in reading and "elevation" in reading:
            seeing_measured = reading["seeing"]
            elevation = reading["elevation"]

            # Calculate airmass from elevation using simple sec(z) approximation
            # where z is the zenith angle (90 - elevation)
            if elevation > 0:
                zenith_angle_rad = math.radians(90.0 - elevation)
                airmass = 1.0 / math.cos(zenith_angle_rad)

                # Correct seeing to zenith using the -3/5 power law
                seeing_zenith = seeing_measured * (airmass ** (-3.0 / 5.0))
                return seeing_zenith
        return 0.0

    def flux(self) -> float:
        """
        Returns the flux of the source being used for measuring seeing in counts.
        @return: the flux value.
        """
        reading = self._get_latest_seeing_reading()
        if reading and "counts" in reading:
            return reading["counts"]
        return 0.0

    def airmass(self) -> float:
        """
        Returns the airmass of the source used for measuring seeing (dimensionless).
        Calculated from elevation using sec(z) approximation.
        @return: the airmass value.
        """
        reading = self._get_latest_seeing_reading()
        if reading and "elevation" in reading:
            elevation = reading["elevation"]
            if elevation > 0:
                # Calculate airmass from elevation using simple sec(z) approximation
                # where z is the zenith angle (90 - elevation)
                zenith_angle_rad = math.radians(90.0 - elevation)
                airmass = 1.0 / math.cos(zenith_angle_rad)
                return airmass
        return 0.0

    def _validate_data(self, data, data_type, required_fields):
        """
        Generic validation for weather or seeing data.

        @param data: The data to validate
        @param data_type: Type of data ('weather' or 'seeing') for logging
        @param required_fields: List of required field names
        @return: True if valid, False otherwise
        """
        if not isinstance(data, dict):
            self.log.error(f"{data_type.capitalize()} data is not a dictionary")
            return False

        if "results" not in data:
            self.log.error(f"{data_type.capitalize()} data missing 'results' field")
            return False

        if not isinstance(data["results"], list) or not data["results"]:
            # Use warning for seeing (may be unavailable), error for weather
            log_method = self.log.warning if data_type == "seeing" else self.log.error
            log_method(
                f"{data_type.capitalize()} data 'results' is not a non-empty list"
            )
            return False

        # Check the most recent reading for required fields
        latest_reading = data["results"][-1]

        for field in required_fields:
            if field not in latest_reading:
                self.log.error(
                    f"Latest {data_type} reading missing required field: {field}"
                )
                return False

        # Validate timestamp format
        try:
            datetime.fromisoformat(latest_reading["ts"].replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            self.log.error(
                f"Invalid timestamp format in {data_type} data: {latest_reading.get('ts')}, error: {e}"
            )
            return False

        self.log.debug(f"{data_type.capitalize()} data validation passed")
        return True

    def _fetch_data(
        self,
        url_config_key,
        time_window_minutes,
        data_type,
        status_attr,
        last_update_attr,
        validator_func,
    ):
        """
        Generic method to fetch and cache data from FastAPI endpoint.

        @param url_config_key: Configuration key for the API URL
        @param time_window_minutes: How many minutes of historical data to request
        @param data_type: Type of data ('weather' or 'seeing') for logging
        @param status_attr: Name of the status attribute (e.g., '_status')
        @param last_update_attr: Name of the last update attribute (e.g., '_last_update')
        @param validator_func: Validation function to use
        @return: Cached or newly fetched data
        """
        current_time = time()

        # Get current cached values
        cached_status = getattr(self, status_attr)
        last_update = getattr(self, last_update_attr)

        # Return cached data if it's still fresh
        if (
            cached_status is not None
            and last_update is not None
            and (current_time - last_update) < self["update_interval"]
        ):
            return cached_status

        # Fetch fresh data from API
        try:
            # Create start time for the requested time window
            start_time = datetime.now(UTC) - timedelta(minutes=time_window_minutes)
            start_ts = start_time.strftime("%Y-%m-%dT%H:%M:%S")

            # Build URL with time parameter
            url = f"{self[url_config_key]}{start_ts}"

            # Make HTTP request
            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read()
                fetched_data = json.loads(data.decode("utf-8"))

            # Validate the new data before updating status
            if validator_func(fetched_data):
                # Update status and timestamp only if validation passes
                setattr(self, status_attr, fetched_data)
                setattr(self, last_update_attr, current_time)
                self.log.debug(
                    f"Successfully fetched and validated {data_type} data from {url}"
                )
            else:
                self.log.warning(
                    f"Received invalid {data_type} data from {url}, keeping previous data"
                )

        except urllib.error.URLError as e:
            self.log.error(f"Failed to fetch {data_type} data from {url}: {e}")
        except json.JSONDecodeError as e:
            self.log.error(f"Failed to parse {data_type} data JSON: {e}")
        except Exception as e:
            self.log.error(f"Unexpected error fetching {data_type} data: {e}")

        # Return current status (either updated with new valid data, or previous data)
        cached_status = getattr(self, status_attr)
        return cached_status if cached_status is not None else {}

    def _validate_weather_data(self, data):
        """Validate weather data structure and required fields."""
        required_fields = [
            "ts",
            "temperature",
            "air_pressure",
            "wind_speed_avg",
            "wind_dir_avg",
            "relative_humidity",
            "rain_intensity",
        ]
        return self._validate_data(data, "weather", required_fields)

    def get_status(self):
        """
        Fetch the most recent weather data from FastAPI endpoint and cache it.
        Only updates status if the new data passes validation checks.
        Returns cached data if it's within the update interval.
        """
        return self._fetch_data(
            url_config_key="swope_weather_host",
            time_window_minutes=5,
            data_type="weather",
            status_attr="_status",
            last_update_attr="_last_update",
            validator_func=self._validate_weather_data,
        )

    def _validate_seeing_data(self, data):
        """Validate seeing data structure and required fields."""
        required_fields = ["ts", "seeing", "counts", "azimuth", "elevation"]
        return self._validate_data(data, "seeing", required_fields)

    def get_seeing_status(self):
        """
        Fetch the most recent seeing data from FastAPI endpoint and cache it.
        Only updates status if the new data passes validation checks.
        Returns cached data if it's within the update interval.
        """
        return self._fetch_data(
            url_config_key="swope_seeing_host",
            time_window_minutes=24 * 60,  # 24 hours
            data_type="seeing",
            status_attr="_seeing_status",
            last_update_attr="_seeing_last_update",
            validator_func=self._validate_seeing_data,
        )

    def get_metadata(self, request):
        """
        Get metadata including weather station data and seeing measurement timestamp.
        Extends the base class metadata with SEEDATE keyword.
        """
        # Get base metadata from WeatherStationBase
        md = WeatherStationBase.get_metadata(self, request)

        # Add seeing measurement timestamp if seeing data is available
        if self.features("WeatherSeeing"):
            reading = self._get_latest_seeing_reading()
            if reading and "ts" in reading:
                md += [
                    (
                        "SEEDATE",
                        reading["ts"],
                        "Seeing measurement date/time",
                    )
                ]

        return md
