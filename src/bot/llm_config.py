"""
Provider configuration for the LLM strategy layer.

Loads from credentials.json (gitignored) at project root.
Falls back to .env settings if the file is absent or malformed.
"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = Path("credentials.json")

# Default model string and base_url per provider.
# base_url is empty for cloud providers; non-empty for local/compatible endpoints.
PROVIDER_DEFAULTS: dict[str, dict] = {
    "anthropic": {"model": "claude-sonnet-4-6", "base_url": ""},
    "openai":    {"model": "gpt-4o",            "base_url": ""},
    "gemini":    {"model": "gemini/gemini-2.0-flash", "base_url": ""},
    "ollama":    {"model": "ollama/llama3.2",    "base_url": "http://localhost:11434"},
    "deepseek":  {"model": "deepseek/deepseek-chat", "base_url": ""},
    "qwen":      {"model": "openai/qwen-turbo",  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
}

SUPPORTED_PROVIDERS = list(PROVIDER_DEFAULTS.keys())


@dataclass
class ProviderConfig:
    provider: str   # one of SUPPORTED_PROVIDERS
    model: str      # litellm model string, e.g. "gpt-4o" or "ollama/llama3.2"
    api_key: str    # empty string for Ollama (no key needed)
    base_url: str   # non-empty for Ollama and Qwen; empty for other cloud providers


def load_provider_config() -> ProviderConfig:
    """Read credentials.json; fall back to .env/settings defaults if absent or malformed."""
    from src.config.settings import settings

    if CREDENTIALS_FILE.exists():
        try:
            data = json.loads(CREDENTIALS_FILE.read_text())
            return ProviderConfig(
                provider=data.get("provider", "anthropic"),
                model=data.get("model", settings.CLAUDE_MODEL),
                api_key=data.get("api_key", settings.ANTHROPIC_API_KEY),
                base_url=data.get("base_url", ""),
            )
        except Exception as e:
            logger.warning("credentials.json malformed (%s) — using .env defaults", e)

    return ProviderConfig(
        provider="anthropic",
        model=settings.CLAUDE_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        base_url="",
    )


def save_provider_config(config: ProviderConfig) -> None:
    """Write provider config to credentials.json."""
    CREDENTIALS_FILE.write_text(json.dumps(asdict(config), indent=2))
