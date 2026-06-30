"""Multi-provider model factory: (provider, model, api_key) -> a pydantic-ai Model.

Provider choice is data, not code — agent files name a default provider/model, and users
configure keys (and optional model overrides) from the UI. SDKs are imported lazily so a
missing optional provider only fails if actually selected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic_ai.models import Model

from quorum_core.core.config import get_settings


@dataclass(frozen=True)
class ReasoningSpec:
    """Describes a provider's *raw* reasoning knob and which models support it.

    `kind` selects the pydantic-ai `model_settings` shape:
    - "effort"          -> {settings_key: "<one of efforts>"}  (OpenAI, Groq)
    - "thinking_budget" -> {settings_key: {"type"/"thinking_budget": <budget>}}  (Anthropic, Google)
    - "none"            -> the provider exposes no reasoning control
    `model_pattern` is a regex matched (case-insensitively) against a catalog model id to decide
    whether that specific model exposes the knob.
    """

    kind: Literal["effort", "thinking_budget", "none"] = "none"
    settings_key: str = ""
    efforts: tuple[str, ...] = ()  # for kind="effort"
    budget_min: int = 0  # for kind="thinking_budget"
    budget_max: int = 0  # for kind="thinking_budget"
    budget_default: int = 0  # suggested budget when enabled
    model_pattern: str = ""  # regex; which catalog model ids support reasoning

    def supports_model(self, model_id: str) -> bool:
        if self.kind == "none" or not self.model_pattern:
            return False
        return re.search(self.model_pattern, model_id, re.IGNORECASE) is not None


_NO_REASONING = ReasoningSpec()


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    default_model: str
    suggested_models: tuple[str, ...]
    settings_attr: str  # attribute on Settings holding the env fallback key
    reasoning: ReasoningSpec = _NO_REASONING


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        "anthropic",
        "Anthropic",
        "claude-sonnet-4-6",
        ("claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"),
        "anthropic_api_key",
        ReasoningSpec(
            kind="thinking_budget",
            settings_key="anthropic_thinking",
            budget_min=1024,
            budget_max=64000,
            budget_default=8000,
            # Extended thinking: Claude 4.x families and the 3.7 line.
            model_pattern=r"(opus-4|sonnet-4|haiku-4|-3-7-)",
        ),
    ),
    "openai": ProviderSpec(
        "openai",
        "OpenAI",
        "gpt-4o",
        ("gpt-4o", "gpt-4o-mini", "o3-mini"),
        "openai_api_key",
        ReasoningSpec(
            kind="effort",
            settings_key="openai_reasoning_effort",
            efforts=("minimal", "low", "medium", "high"),
            # Reasoning models: o-series and gpt-5 family.
            model_pattern=r"^(o[134]|gpt-5)",
        ),
    ),
    "google": ProviderSpec(
        "google",
        "Google Gemini",
        "gemini-2.0-flash",
        ("gemini-2.0-flash", "gemini-1.5-pro"),
        "google_api_key",
        ReasoningSpec(
            kind="thinking_budget",
            settings_key="google_thinking_config",
            budget_min=0,
            budget_max=24576,
            budget_default=4096,
            model_pattern=r"gemini-2\.5",
        ),
    ),
    "groq": ProviderSpec(
        "groq",
        "Groq",
        "llama-3.3-70b-versatile",
        ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
        "groq_api_key",
        ReasoningSpec(
            kind="effort",
            settings_key="groq_reasoning_effort",
            efforts=("none", "default", "low", "medium", "high"),
            # Reasoning-capable Groq families.
            model_pattern=r"(qwen3|gpt-oss|deepseek-r1)",
        ),
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


def build_reasoning_settings(provider: str, model: str, raw: str | None) -> dict:
    """Translate a stored raw reasoning value into a pydantic-ai `model_settings` fragment.

    `raw` is the user's per-provider knob as stored on `ProviderSetting.reasoning`: an effort
    string (e.g. "high") for kind="effort", or a token budget (as a string) for
    kind="thinking_budget". Returns `{}` when the provider has no reasoning control, the value is
    blank/"none", or the selected model doesn't support reasoning.
    """
    spec = PROVIDERS.get((provider or "").lower())
    if spec is None or not raw:
        return {}
    rs = spec.reasoning
    if not rs.supports_model(model or ""):
        return {}

    if rs.kind == "effort":
        value = raw.strip().lower()
        if value in ("", "none", "off") and value not in rs.efforts:
            return {}
        if value not in rs.efforts:
            return {}
        return {rs.settings_key: value}

    if rs.kind == "thinking_budget":
        try:
            budget = int(raw)
        except (TypeError, ValueError):
            return {}
        if budget <= 0:
            return {}
        budget = max(rs.budget_min, min(budget, rs.budget_max))
        if rs.settings_key == "anthropic_thinking":
            return {rs.settings_key: {"type": "enabled", "budget_tokens": budget}}
        if rs.settings_key == "google_thinking_config":
            return {rs.settings_key: {"thinking_budget": budget, "include_thoughts": False}}
        return {rs.settings_key: {"budget_tokens": budget}}

    return {}


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
    model_settings: dict = field(default_factory=dict)


def resolve_runtime_model(
    *,
    default_provider: str,
    default_model: str,
    configured: dict[str, dict],
    is_chairman: bool = False,
) -> RuntimeModel:
    """Pick the provider/model/key for an agent.

    Prefers the agent's own default provider when a key is available; otherwise falls back
    to the first enabled configured provider with a key. `configured` maps provider ->
    {"api_key", "default_model", "reasoning", "chairman_model", "chairman_reasoning",
    "enabled"} (decrypted), typically built from the user's settings plus env fallbacks.

    Model selection is per role: the Chairman uses the provider's `chairman_model` (and
    `chairman_reasoning`) when configured, otherwise the agent's own default model — it is never
    downgraded to the council-member `default_model`. Council members use `default_model`.
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
        agent_default = default_model if prov == default_provider else spec.default_model
        if is_chairman:
            model = cfg.get("chairman_model") or agent_default
            reasoning_raw = cfg.get("chairman_reasoning")
        else:
            model = cfg.get("default_model") or agent_default
            reasoning_raw = cfg.get("reasoning")
        reasoning = build_reasoning_settings(prov, model, reasoning_raw)
        return RuntimeModel(provider=prov, model=model, api_key=key, model_settings=reasoning)

    # Nothing configured — return the agent's defaults with no key so the caller can
    # surface a clear "configure a provider key" error at run time.
    return RuntimeModel(provider=default_provider, model=default_model, api_key=None)
