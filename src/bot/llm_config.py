"""
Provider configuration for the LLM strategy layer.

Priority order:
1. prediction_bot/config/llm_providers.json (active provider)
2. credentials.json (gitignored) at project root
3. .env settings defaults
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS_FILE = _ROOT / "credentials.json"
_PB_LLM_CONFIG = _ROOT / "prediction_bot" / "config" / "llm_providers.json"

# Default model string and base_url per provider.
# base_url is empty for cloud providers; non-empty for local/compatible endpoints.
PROVIDER_DEFAULTS: dict[str, dict] = {
    "anthropic": {"model": "claude-sonnet-4-6", "base_url": ""},
    "openai":    {"model": "gpt-4o",            "base_url": ""},
    "azure":     {"model": "azure/model-router", "base_url": ""},
    "gemini":    {"model": "gemini/gemini-2.0-flash", "base_url": ""},
    "ollama":    {"model": "ollama/llama3.2",    "base_url": "http://localhost:11434"},
    "deepseek":  {"model": "deepseek/deepseek-chat", "base_url": ""},
    "qwen":      {"model": "openai/qwen-turbo",  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
}

SUPPORTED_PROVIDERS = list(PROVIDER_DEFAULTS.keys())

# Providers whose model strings must carry a specific prefix for LiteLLM routing.
_REQUIRED_PREFIXES: dict[str, str] = {
    "ollama":   "ollama/",
    "deepseek": "deepseek/",
    "gemini":   "gemini/",
    "azure":    "azure/",
}


@dataclass
class ProviderConfig:
    provider: str   # one of SUPPORTED_PROVIDERS
    model: str      # litellm model string, e.g. "gpt-4o" or "azure/model-router"
    api_key: str    # empty string for Ollama (no key needed)
    base_url: str   # non-empty for Ollama, Qwen, and Azure; empty for other cloud providers
    api_version: str = ""     # required for Azure OpenAI endpoints
    temperature: float = 0.3

    def __post_init__(self):
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"provider must be one of {SUPPORTED_PROVIDERS}, got {self.provider!r}")
        # Ensure the model string carries the provider prefix LiteLLM needs.
        prefix = _REQUIRED_PREFIXES.get(self.provider)
        if prefix and not self.model.startswith(prefix):
            self.model = f"{prefix}{self.model}"


def _resolve_env(value: str) -> str:
    if isinstance(value, str) and value.startswith("$"):
        return os.environ.get(value[1:], "")
    return value


def _load_from_prediction_bot() -> "ProviderConfig | None":
    """Load active provider from prediction_bot/config/llm_providers.json."""
    if not _PB_LLM_CONFIG.exists():
        return None
    try:
        cfg = json.loads(_PB_LLM_CONFIG.read_text(encoding="utf-8"))
        active_name = cfg.get("active", "")
        p = cfg.get("providers", {}).get(active_name)
        if not p:
            return None
        litellm_model = p["litellm_model"]
        provider_type = p.get("provider_type", "")
        if provider_type == "azure_openai" or litellm_model.startswith("azure/"):
            provider = "azure"
        elif litellm_model.startswith("openai/") or "gpt" in litellm_model:
            provider = "openai"
        else:
            provider = "anthropic"
        return ProviderConfig(
            provider=provider,
            model=litellm_model,
            api_key=_resolve_env(p.get("api_key", "")),
            base_url=p.get("api_base", ""),
            api_version=p.get("api_version", ""),
            temperature=p.get("temperature", 0.3),
        )
    except Exception as e:
        logger.warning("prediction_bot llm_providers.json unreadable (%s) — skipping", e)
        return None


def load_provider_config() -> ProviderConfig:
    """Load provider config: prediction_bot config → credentials.json → .env defaults."""
    from src.config.settings import settings

    pb_config = _load_from_prediction_bot()
    if pb_config is not None:
        logger.info("Using LLM provider from prediction_bot config: %s/%s", pb_config.provider, pb_config.model)
        return pb_config

    if CREDENTIALS_FILE.exists():
        try:
            data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
            return ProviderConfig(
                provider=data.get("provider", "anthropic"),
                model=data.get("model", settings.CLAUDE_MODEL),
                api_key=data.get("api_key", settings.ANTHROPIC_API_KEY),
                base_url=data.get("base_url", ""),
                api_version=data.get("api_version", ""),
                temperature=data.get("temperature", 0.3),
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
    try:
        CREDENTIALS_FILE.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"Failed to save credentials to {CREDENTIALS_FILE}: {e}") from e
