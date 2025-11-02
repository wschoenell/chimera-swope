import pytest
from chimera.core.proxy import Proxy


class TestFilterWheels:
    """Test suite for Henrietta filter wheel functionality."""

    # Configuration for different wheel types
    WHEEL_CONFIGS = {
        "slit_wheel": {
            "proxy_path": "127.0.0.1:6379/HenriettaSlitWheel/slit_wheel",
            "filters": [
                "calibration",
                "10",
                "20",
                "10+wings",
                "20+wings",
                "15+wings",
                "focusing",
                "none",
            ],
        },
        "grism_wheel": {
            "proxy_path": "127.0.0.1:6379/HenriettaGrismWheel/grism_wheel",
            "filters": ["R-J", "open", "Y-H", "J-K", "closed"],
        },
        "diffuser_wheel": {
            "proxy_path": "127.0.0.1:6379/HenriettaDiffuserWheel/diffuser_wheel",
            "filters": ["R-J+eng", "R-J+cil", "J-K+eng", "J-K+cil", "open"],
        },
        "filter_wheel": {
            "proxy_path": "127.0.0.1:6379/HenriettaFilterWheel/filter_wheel",
            "filters": ["R-J", "open", "Y-H", "J-K", "closed"],
        },
        "slide_wheel": {
            "proxy_path": "127.0.0.1:6379/HenriettaSlideWheel/slide_wheel",
            "filters": ["Out", "In", "Wobble"],
        },
    }

    @pytest.fixture(params=WHEEL_CONFIGS.keys())
    def wheel_config(self, request):
        """Parametrized fixture that provides configuration for each wheel type."""
        wheel_name = request.param
        config = self.WHEEL_CONFIGS[wheel_name].copy()
        config["name"] = wheel_name
        return config

    @pytest.fixture
    def filter_wheel(self, wheel_config):
        """Create a proxy to the filter wheel for testing."""
        return Proxy(wheel_config["proxy_path"])

    def test_set_filter(self, filter_wheel, wheel_config):
        """Test setting each available filter position for each wheel."""
        for filter_name in wheel_config["filters"]:
            filter_wheel.set_filter(filter_name)
            assert filter_wheel.get_filter() == filter_name

    def test_set_filter_case_insensitive(self, filter_wheel, wheel_config):
        """Test that filter names are case insensitive."""
        for filter_name in wheel_config["filters"]:
            # Test with uppercase
            filter_wheel.set_filter(filter_name.upper())
            current_filter = filter_wheel.get_filter()
            assert current_filter.lower() == filter_name.upper().lower()

            # Test with lowercase
            filter_wheel.set_filter(filter_name.lower())
            current_filter = filter_wheel.get_filter()
            assert current_filter.lower() == filter_name.lower()

    def test_set_invalid_filter(self, filter_wheel, wheel_config):
        """Test that setting an invalid filter raises an appropriate error."""
        with pytest.raises(Exception) as exc_info:
            filter_wheel.set_filter("invalid_filter_name")
        # Verify that the underlying error is ValueError or IndexError
        assert "ValueError" in str(exc_info.value) or "IndexError" in str(
            exc_info.value
        )

    def test_filter_sequence(self, filter_wheel, wheel_config):
        """Test moving through a sequence of filters."""
        filters = wheel_config["filters"]

        # Test sequence: first, middle, last filters
        test_sequence = [filters[0], filters[len(filters) // 2], filters[-1]]

        for filter_name in test_sequence:
            filter_wheel.set_filter(filter_name)
            assert filter_wheel.get_filter() == filter_name

    def test_get_current_filter(self, filter_wheel, wheel_config):
        """Test getting the current filter position."""
        current_filter = filter_wheel.get_filter()
        # Should return a valid filter name
        assert current_filter in wheel_config["filters"]
