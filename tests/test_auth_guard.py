"""Tests for the production OTP-bypass startup guard in src/api/main.py."""

import logging

import pytest

from src.api import main as api_main


class TestTestAccountEnvGuard:
    def test_production_with_test_email_raises(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("TEST_ACCOUNT_EMAIL", "foo@bar.com")
        with pytest.raises(RuntimeError, match="TEST_ACCOUNT_EMAIL"):
            api_main._check_test_account_env_guard()

    def test_prod_alias_with_test_email_raises(self, monkeypatch):
        monkeypatch.setenv("ENV", "PROD")
        monkeypatch.setenv("TEST_ACCOUNT_EMAIL", "foo@bar.com")
        with pytest.raises(RuntimeError):
            api_main._check_test_account_env_guard()

    def test_development_with_test_email_succeeds_and_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("TEST_ACCOUNT_EMAIL", "foo@bar.com")
        with caplog.at_level(logging.WARNING, logger=api_main.logger.name):
            api_main._check_test_account_env_guard()
        assert any("foo@bar.com" in rec.message for rec in caplog.records)

    def test_production_without_test_email_succeeds(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        monkeypatch.delenv("TEST_ACCOUNT_EMAIL", raising=False)
        api_main._check_test_account_env_guard()  # no raise

    def test_app_startup_raises_in_production(self, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("TEST_ACCOUNT_EMAIL", "foo@bar.com")
        with pytest.raises(RuntimeError, match="TEST_ACCOUNT_EMAIL"):
            with TestClient(api_main.app):
                pass

    def test_app_startup_succeeds_in_development(self, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("TEST_ACCOUNT_EMAIL", "foo@bar.com")
        with TestClient(api_main.app):
            pass

