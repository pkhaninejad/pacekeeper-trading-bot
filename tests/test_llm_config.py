"""Tests for src/bot/llm_config.py."""

import json
import pytest
from src.bot.llm_config import ProviderConfig, load_provider_config, save_provider_config


@pytest.fixture(autouse=True)
def patch_credentials_file(tmp_path, monkeypatch):
    """Redirect CREDENTIALS_FILE to a temp path for every test."""
    creds = tmp_path / "credentials.json"
    monkeypatch.setattr("src.bot.llm_config.CREDENTIALS_FILE", creds)
    return creds


class TestLoadProviderConfig:
    def test_falls_back_to_anthropic_when_file_absent(self):
        config = load_provider_config()
        assert config.provider == "anthropic"

    def test_falls_back_when_file_is_malformed_json(self, patch_credentials_file):
        patch_credentials_file.write_text("not { valid json }")
        config = load_provider_config()
        assert config.provider == "anthropic"
        from src.config.settings import settings
        assert config.model == settings.CLAUDE_MODEL
        assert config.api_key == settings.ANTHROPIC_API_KEY

    def test_loads_saved_provider(self, patch_credentials_file):
        patch_credentials_file.write_text(json.dumps({
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test",
            "base_url": "",
        }))
        config = load_provider_config()
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.api_key == "sk-test"

    def test_loads_ollama_with_base_url(self, patch_credentials_file):
        patch_credentials_file.write_text(json.dumps({
            "provider": "ollama",
            "model": "ollama/llama3.2",
            "api_key": "",
            "base_url": "http://localhost:11434",
        }))
        config = load_provider_config()
        assert config.provider == "ollama"
        assert config.base_url == "http://localhost:11434"
        assert config.api_key == ""


class TestSaveProviderConfig:
    def test_writes_valid_json(self, patch_credentials_file):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek/deepseek-chat",
            api_key="ds-key",
            base_url="",
        )
        save_provider_config(config)
        data = json.loads(patch_credentials_file.read_text())
        assert data["provider"] == "deepseek"
        assert data["model"] == "deepseek/deepseek-chat"
        assert data["api_key"] == "ds-key"
        assert data["base_url"] == ""

    def test_roundtrip(self, patch_credentials_file):
        original = ProviderConfig(
            provider="gemini",
            model="gemini/gemini-2.0-flash",
            api_key="gm-key",
            base_url="",
        )
        save_provider_config(original)
        loaded = load_provider_config()
        assert loaded.provider == original.provider
        assert loaded.model == original.model
        assert loaded.api_key == original.api_key
        assert loaded.base_url == original.base_url


class TestProviderConfigValidation:
    def test_rejects_unknown_provider(self):
        with pytest.raises(ValueError, match="provider must be one of"):
            ProviderConfig(provider="badprovider", model="x", api_key="", base_url="")

    def test_accepts_all_supported_providers(self):
        from src.bot.llm_config import SUPPORTED_PROVIDERS, PROVIDER_DEFAULTS
        for provider in SUPPORTED_PROVIDERS:
            defaults = PROVIDER_DEFAULTS[provider]
            api_key = "" if provider == "ollama" else "test-key"
            config = ProviderConfig(
                provider=provider,
                model=defaults["model"],
                api_key=api_key,
                base_url=defaults["base_url"],
            )
            assert config.provider == provider
