from __future__ import annotations

from api.config import Settings, get_settings


def test_settings_aliases_origins_and_database_escaping(monkeypatch):
    settings = Settings(api_bearer_token="x", db_user="a@b", db_password="p /?",
                        s3_access_key_id="a", s3_secret_access_key="b", s3_public_endpoint="http://a",
                        s3_internal_endpoint="http://b", cors_allowed_origins=" http://a, https://b ")
    assert settings.cors_allowed_origins == ["http://a", "https://b"]
    assert "a%40b" in settings.database_url and "p+%2F%3F" in settings.database_url
    assert settings.route_distance_m > 0 and settings.presigned_url_ttl_seconds > 0 and settings.extraction_concurrency >= 1


def test_settings_accepts_list_origins():
    settings = Settings(api_bearer_token="x", db_password="p", s3_access_key_id="a",
                        s3_secret_access_key="b", s3_public_endpoint="http://a",
                        s3_internal_endpoint="http://b", cors_allowed_origins=["http://a"])
    assert settings.cors_allowed_origins == ["http://a"]


def test_get_settings_cache_isolated(monkeypatch):
    get_settings.cache_clear(); monkeypatch.setenv("API_BEARER_TOKEN", "one")
    assert get_settings().api_bearer_token == "one"
    get_settings.cache_clear(); monkeypatch.setenv("API_BEARER_TOKEN", "two")
    assert get_settings().api_bearer_token == "two"
    get_settings.cache_clear()
