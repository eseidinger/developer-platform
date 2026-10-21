"""Bounded workload trace metadata shared by ingress and project-scoped reads."""

import math
import re

MAX_ATTRIBUTES = 16
OPERATIONS = frozenset(
    {
        "chat",
        "text_completion",
        "generate_content",
        "embeddings",
        "execute_tool",
        "invoke_agent",
        "create_agent",
        "retrieval",
    }
)
AI_NAMES = frozenset(
    {"application.ai." + operation for operation in OPERATIONS}
    | {"application.ai.service"}
)
ATTRIBUTE_KEYS = frozenset(
    {
        "http.request.method",
        "http.response.status_code",
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.response.model",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.request.max_tokens",
        "gen_ai.request.temperature",
        "gen_ai.request.top_p",
        "gen_ai.response.finish_reasons",
        "gen_ai.tool.name",
        "error.type",
        "platform.instrumentation.name",
        "platform.ai.framework",
    }
)
ALIASES = {
    "gen_ai.provider.name": "gen_ai.system",
    "gen_ai.usage.input_tokens": "gen_ai.usage.prompt_tokens",
    "gen_ai.usage.output_tokens": "gen_ai.usage.completion_tokens",
}
INPUT_KEYS = ATTRIBUTE_KEYS | frozenset(ALIASES.values())
_IDENTIFIER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:/@$-]{0,127}\Z")
_SCOPE = re.compile(r"[A-Za-z@][A-Za-z0-9_.@/-]{0,127}\Z")
_VERSION = re.compile(r"[0-9][A-Za-z0-9_.+-]{0,31}\Z")
_LANGCHAIN4J = re.compile(r"(?:^|[./@-])langchain4j(?:$|[./@-])")
_FINISH = frozenset(
    {
        "stop",
        "length",
        "tool_calls",
        "function_call",
        "content_filter",
        "error",
        "other",
        "unknown",
    }
)
METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def identifier(value):
    return (
        isinstance(value, str)
        and bool(_IDENTIFIER.fullmatch(value))
        and "://" not in value
    )


def instrumentation(name, version=""):
    """Instrumentation identifiers are metadata, never verified workload identity."""
    name = (
        name
        if isinstance(name, str) and _SCOPE.fullmatch(name)
        else "platform-verified-workload"
    )
    version = (
        version if isinstance(version, str) and _VERSION.fullmatch(version) else ""
    )
    return name, version


def attributes(source, scope_name="", original_name="", exception_type=None):
    """Discard unknown keys and malformed values rather than stringify/truncate them."""
    safe = {}
    method, status = (
        source.get("http.request.method"),
        source.get("http.response.status_code"),
    )
    if isinstance(method, str) and method in METHODS:
        safe["http.request.method"] = method
    if type(status) is int and 100 <= status <= 599:
        safe["http.response.status_code"] = status
    operation = source.get("gen_ai.operation.name")
    if isinstance(operation, str) and operation in OPERATIONS:
        safe["gen_ai.operation.name"] = operation
    for key in (
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.response.model",
        "gen_ai.tool.name",
    ):
        value = source.get(key, source.get(ALIASES.get(key)))
        if identifier(value):
            safe[key] = (
                ("openai" if value.lower() == "open_ai" else value.lower())
                if key == "gen_ai.provider.name"
                else value
            )
    for key in (
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.request.max_tokens",
    ):
        value = source.get(key, source.get(ALIASES.get(key)))
        if type(value) is int and 0 <= value <= 2**63 - 1:
            safe[key] = value
    for key, maximum in (
        ("gen_ai.request.temperature", 2),
        ("gen_ai.request.top_p", 1),
    ):
        value = source.get(key)
        if (
            type(value) in {int, float}
            and math.isfinite(value)
            and 0 <= value <= maximum
        ):
            safe[key] = value
    reasons = source.get("gen_ai.response.finish_reasons")
    if isinstance(reasons, str):
        reasons = [reasons]  # Quarkus LangChain4j emits a scalar enum.
    if isinstance(reasons, list) and 0 < len(reasons) <= 4:
        normalized = [
            "tool_calls" if reason.lower() == "tool_execution" else reason.lower()
            for reason in reasons
            if isinstance(reason, str)
        ]
        if len(normalized) == len(reasons) and all(
            reason in _FINISH for reason in normalized
        ):
            safe["gen_ai.response.finish_reasons"] = normalized
    error = source.get("error.type", exception_type)
    if identifier(error):
        safe["error.type"] = error
    name, _ = instrumentation(scope_name)
    if name != "platform-verified-workload":
        safe["platform.instrumentation.name"] = name
    if (
        source.get("platform.ai.framework") == "langchain4j"
        or _LANGCHAIN4J.search(name.lower())
        or original_name.startswith("langchain4j.")
    ):
        safe["platform.ai.framework"] = "langchain4j"
    # Older listeners named completion spans but omitted gen_ai.operation.name.
    if (
        "gen_ai.operation.name" not in safe
        and safe.get("gen_ai.request.model")
        and original_name == "completion " + safe["gen_ai.request.model"]
    ):
        safe["gen_ai.operation.name"] = "chat"
    assert len(safe) <= MAX_ATTRIBUTES
    return safe


def span_name(safe, original=""):
    operation = safe.get("gen_ai.operation.name")
    if operation in OPERATIONS:
        return "application.ai." + operation
    if original in AI_NAMES:
        return original
    if safe.get("platform.ai.framework") == "langchain4j":
        return "application.ai.service"
    return "application.span"


def protobuf_value(value):
    kind = value.WhichOneof("value")
    if kind in {"string_value", "int_value", "double_value"}:
        return getattr(value, kind)
    if (
        kind == "array_value"
        and len(value.array_value.values) <= 4
        and all(
            v.WhichOneof("value") == "string_value" for v in value.array_value.values
        )
    ):
        return [v.string_value for v in value.array_value.values]
    return None


def json_value(value):
    if not isinstance(value, dict) or len(value) != 1:
        return None
    if "stringValue" in value:
        return value["stringValue"] if isinstance(value["stringValue"], str) else None
    if "intValue" in value:
        raw = value["intValue"]
        if (
            type(raw) is int
            or isinstance(raw, str)
            and re.fullmatch(r"-?[0-9]{1,19}", raw)
        ):
            return int(raw)
    if "doubleValue" in value and type(value["doubleValue"]) in {int, float}:
        return value["doubleValue"]
    array = value.get("arrayValue", {})
    if (
        isinstance(array, dict)
        and isinstance(array.get("values"), list)
        and len(array["values"]) <= 4
    ):
        return [json_value(item) for item in array["values"]]
    return None
