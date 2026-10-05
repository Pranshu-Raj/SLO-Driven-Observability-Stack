import pytest

from shop.config import ConfigError, Settings, redact


def test_missing_required_settings_are_all_reported():
    with pytest.raises(ConfigError, match="REDIS_URL"):
        Settings.from_env("api", {})


def test_bad_number_names_the_variable():
    with pytest.raises(ConfigError, match="API_TIMEOUT_SECONDS"):
        Settings.from_env("frontend", {"API_URL": "http://api", "API_TIMEOUT_SECONDS": "two"})


def test_defaults():
    s = Settings.from_env("frontend", {"API_URL": "http://api:8000"})
    assert s.port == 8000
    assert s.api_timeout == 2.0


def test_password_never_in_repr_or_redacted_url():
    s = Settings.from_env("api", {"REDIS_URL": "redis://:hunter2@redis:6379/0"})
    assert "hunter2" not in repr(s)
    assert redact(s.redis_url) == "redis://:***@redis:6379/0"
    assert redact("redis://redis:6379/0") == "redis://redis:6379/0"
