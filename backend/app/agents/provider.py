"""Multi-provider model factory: (provider, model, api_key) -> a pydantic-ai Model.

Provider choice is data, not code — agent files name a default provider/model, and users
configure keys (and optional model overrides) from the UI. SDKs are imported lazily so a
missing optional provider only fails if actually selected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai.models import Model

from app.core.config import get_settings


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    default_model: str
    suggested_models: tuple[str, ...]
    settings_attr: str  # attribute on Settings holding the env fallback key


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        "anthropic",
        "Anthropic",
        "claude-sonnet-4-6",
        ("claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"),
        "anthropic_api_key",
    ),
    "openai": ProviderSpec(
        "openai",
        "OpenAI",
        "gpt-4o",
        ("gpt-4o", "gpt-4o-mini", "o3-mini"),
        "openai_api_key",
    ),
    "google": ProviderSpec(
        "google",
        "Google Gemini",
        "gemini-2.0-flash",
        ("gemini-2.0-flash", "gemini-1.5-pro"),
        "google_api_key",
    ),
    "groq": ProviderSpec(
        "groq",
        "Groq",
        "llama-3.3-70b-versatile",
        ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
        "groq_api_key",
    ),
    "mistral": ProviderSpec(
        "mistral",
        "Mistral",
        "mistral-large-latest",
        ("mistral-large-latest", "mistral-small-latest"),
        "mistral_api_key",
    ),
    "cohere": ProviderSpec(
        "cohere",
        "Cohere",
        "command-r-plus",
        ("command-r-plus", "command-r"),
        "cohere_api_key",
    ),
}


class ProviderError(RuntimeError):
    """Raised for an unknown provider or a missing provider SDK."""


def list_provider_specs() -> list[ProviderSpec]:
    return list(PROVIDERS.values())


def build_model(provider: str, model_name: str, api_key: str | None = None) -> Model:
    """Construct a pydantic-ai Model for the given provider/model with an explicit key."""
    p = provider.lower()
    if p not in PROVIDERS:
        raise ProviderError(f"unknown provider '{provider}'; known: {sorted(PROVIDERS)}")

    try:
        if p == "anthropic":
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            prov = AnthropicProvider(api_key=api_key) if api_key else AnthropicProvider()
            return AnthropicModel(model_name, provider=prov)
        if p == "openai":
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            prov = OpenAIProvider(api_key=api_key) if api_key else OpenAIProvider()
            return OpenAIChatModel(model_name, provider=prov)
        if p == "google":
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider

            prov = GoogleProvider(api_key=api_key) if api_key else GoogleProvider()
            return GoogleModel(model_name, provider=prov)
        if p == "groq":
            from pydantic_ai.models.groq import GroqModel
            from pydantic_ai.providers.groq import GroqProvider

            prov = GroqProvider(api_key=api_key) if api_key else GroqProvider()
            return GroqModel(model_name, provider=prov)
        if p == "mistral":
            from pydantic_ai.models.mistral import MistralModel
            from pydantic_ai.providers.mistral import MistralProvider

            prov = MistralProvider(api_key=api_key) if api_key else MistralProvider()
            return MistralModel(model_name, provider=prov)
        if p == "cohere":
            from pydantic_ai.models.cohere import CohereModel
            from pydantic_ai.providers.cohere import CohereProvider

            prov = CohereProvider(api_key=api_key) if api_key else CohereProvider()
            return CohereModel(model_name, provider=prov)
    except ImportError as exc:  # pragma: no cover - depends on optional SDKs
        raise ProviderError(f"provider '{p}' SDK is not installed: {exc}") from exc

    raise ProviderError(f"provider '{p}' has no builder")  # pragma: no cover


@dataclass
class RuntimeModel:
    """The resolved provider/model/key an agent will actually run with."""

    provider: str
    model: str
    api_key: str | None = field(repr=False, default=None)


def resolve_runtime_model(
    *,
    default_provider: str,
    default_model: str,
    configured: dict[str, dict],
) -> RuntimeModel:
    """Pick the provider/model/key for an agent.

    Prefers the agent's own default provider when a key is available; otherwise falls back
    to the first enabled configured provider with a key. `configured` maps provider ->
    {"api_key", "default_model", "enabled"} (decrypted), typically built from the user's
    settings plus env fallbacks.
    """
    settings = get_settings()
    order = [default_provider, *[k for k in PROVIDERS if k != default_provider]]

    for prov in order:
        spec = PROVIDERS.get(prov)
        if spec is None:
            continue
        cfg = configured.get(prov, {})
        if cfg.get("enabled") is False:
            continue
        key = cfg.get("api_key") or getattr(settings, spec.settings_attr, None)
        if not key:
            continue
        if prov == default_provider:
            model = cfg.get("default_model") or default_model
        else:
            model = cfg.get("default_model") or spec.default_model
        return RuntimeModel(provider=prov, model=model, api_key=key)

    # Nothing configured — return the agent's defaults with no key so the caller can
    # surface a clear "configure a provider key" error at run time.
    return RuntimeModel(provider=default_provider, model=default_model, api_key=None)
