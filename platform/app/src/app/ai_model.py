"""Provider-neutral model boundary; the initial OpenAI path fails closed."""

import os
from typing import Protocol, Any


class ModelUnavailable(Exception):
    pass


class ModelAdapter(Protocol):
    name: str

    def bind_tools(self, tools: list[Any]) -> Any: ...


class OpenAIModelAdapter:
    name = "openai:gpt-6.1-sol"

    def __init__(self):
        # The endpoint alone cannot prove account eligibility or contractual terms.
        checks = ("OPENAI_EU_PROJECT_VERIFIED", "OPENAI_EU_PROCESSING_VERIFIED",
                  "OPENAI_MODIFIED_RETENTION_AMENDMENT_VERIFIED")
        if any(os.environ.get(key) != "true" for key in checks):
            raise ModelUnavailable("EU model eligibility and retention terms are not verified")
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ModelUnavailable("OpenAI API key is not configured")
        from langchain_openai import ChatOpenAI
        self.model = ChatOpenAI(
            model="gpt-6.1-sol", api_key=key,
            base_url="https://eu.api.openai.com/v1", use_responses_api=True,
            store=False, use_previous_response_id=False,
            reasoning_effort="low", max_tokens=1024,
            timeout=10, max_retries=0,
        )

    def bind_tools(self, tools):
        return self.model.bind_tools(tools, parallel_tool_calls=False)


def configured_model() -> ModelAdapter:
    provider = os.environ.get("AI_MODEL_PROVIDER", "openai")
    if provider == "openai":
        return OpenAIModelAdapter()
    raise ModelUnavailable("Configured model provider is unavailable")
