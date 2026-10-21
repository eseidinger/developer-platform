"""Provider-neutral model boundary; the initial OpenAI path fails closed."""

import os
from typing import Any, Protocol

from . import ai_pricing


class ModelUnavailable(Exception):
    pass


class ModelAdapter(Protocol):
    name: str

    def bind_tools(self, tools: list[Any], *, allow_tools: bool = True) -> Any: ...

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float: ...

    def reserve_cost_usd(self, input_tokens: int) -> float: ...


class OpenAIModelAdapter:
    name = "openai:gpt-6.1-sol"

    def __init__(self):
        # Explicit global acceptance never implies verified EU eligibility.
        region = os.environ.get("OPENAI_DATA_REGION", "eu")
        if region == "global":
            if os.environ.get("OPENAI_GLOBAL_PROCESSING_ACCEPTED") != "true":
                raise ModelUnavailable("Global model processing is not accepted")
            base_url = "https://api.openai.com/v1"
            self.regional_cost_multiplier = 1.0
        elif region == "eu":
            checks = (
                "OPENAI_EU_PROJECT_VERIFIED",
                "OPENAI_EU_PROCESSING_VERIFIED",
                "OPENAI_MODIFIED_RETENTION_AMENDMENT_VERIFIED",
            )
            if any(os.environ.get(key) != "true" for key in checks):
                raise ModelUnavailable(
                    "EU model eligibility and retention terms are not verified"
                )
            base_url = "https://eu.api.openai.com/v1"
            self.regional_cost_multiplier = 1.1
        else:
            raise ModelUnavailable("Configured OpenAI data region is unsupported")
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ModelUnavailable("OpenAI API key is not configured")
        from langchain_openai import ChatOpenAI

        self.model = ChatOpenAI(
            model="gpt-6.1-sol",
            api_key=key,
            base_url=base_url,
            use_responses_api=True,
            store=False,
            use_previous_response_id=False,
            reasoning_effort="low",
            max_tokens=1024,
            service_tier="default",
            timeout=30,
            max_retries=0,
        )

    def bind_tools(self, tools, *, allow_tools=True):
        options = {} if allow_tools else {"tool_choice": "none"}
        return self.model.bind_tools(tools, parallel_tool_calls=False, **options)

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return ai_pricing.estimate(
            self.name,
            {"input_tokens": input_tokens, "output_tokens": output_tokens},
            self.regional_cost_multiplier,
        ).usd

    def estimate_usage(self, usage):
        return ai_pricing.estimate(self.name, usage, self.regional_cost_multiplier)

    def reserve_cost_usd(self, input_tokens: int) -> float:
        return self.estimate_cost_usd(input_tokens, 1024)


def configured_model() -> ModelAdapter:
    provider = os.environ.get("AI_MODEL_PROVIDER", "openai")
    if provider == "openai":
        return OpenAIModelAdapter()
    raise ModelUnavailable("Configured model provider is unavailable")
