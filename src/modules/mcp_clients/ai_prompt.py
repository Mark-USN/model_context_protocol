from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Annotated,Iterable
from openai import OpenAI
from modules.utils.api_keys import api_vault



def _get_openai_client():
    vault = api_vault()
    openai_key = vault.get_value(key="OPENAI_KEY")
    if not openai_key:
        raise RuntimeError("Missing OPENAI_KEY from api_vault()")
    return OpenAI(api_key=openai_key)

@dataclass(slots=True)
class NormalizedQuery:
    query: str
    includes: list[str]
    excludes: list[str]
    phrases: list[str]
    channels: list[str]
    notes: str


YOUTUBE_QUERY_SCHEMA = {
    "name": "youtube_query_normalized",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string"},
            "includes": {"type": "array", "items": {"type": "string"}},
            "excludes": {"type": "array", "items": {"type": "string"}},
            "phrases": {"type": "array", "items": {"type": "string"}},
            "channels": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
        },
        "required": ["query", "includes", "excludes", "phrases", "channels", "notes"],
    },
    "strict": True,
}


@dataclass(slots=True)
class LlmMessage:
    role: str
    content: str


def _coerce_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    # TextContent(...) with .text
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text

    # If your MCP ever returns a list of parts, join text parts
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            t = getattr(part, "text", None)
            if isinstance(t, str):
                parts.append(t)
        if parts:
            return "\n".join(parts)

    raise TypeError(f"Unsupported content type for OpenAI: {type(content)!r}")

def _get(obj: Any, name: str) -> Any:
    """Read field `name` from dict-like OR attribute-like objects."""
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)



def mcp_messages_to_openai(messages: list[Any]) -> list[dict[str,str]]:
    return [{"role": str(m.role), "content": _coerce_content_to_text(m.content)} for m in messages]


def prompt_result_messages_to_llm(messages: Any) -> list[LlmMessage]:
    """
    Normalize `PromptResult.messages` into a stable `list[LlmMessage]`.

    Handles FastMCP return shapes:
      - messages is str  -> one user message
      - messages is list -> each element may be dict-like or attribute-like
    """
    # FastMCP docs: PromptResult.messages can be str or list[Message]. :contentReference[oaicite:1]{index=1}
    if isinstance(messages, str):
        return [LlmMessage(role="user", content=messages)]

    if not isinstance(messages, Iterable):
        raise TypeError(f"Expected messages to be str or iterable, got {type(messages)!r}")

    out: list[LlmMessage] = []
    for m in messages:
        role = str(_get(m, "role"))
        content = _coerce_content_to_text(_get(m, "content"))
        out.append(LlmMessage(role=role, content=content))

    return out

def _messages_to_openai_input(messages: list[LlmMessage]) -> list[dict[str, Any]]:
    """
    Convert internal messages to OpenAI Responses API input items.

    This uses a simple pattern: one 'message' item per LlmMessage.
    """
    return [
        {
            "role": m.role,
            "content": [{"type": "input_text", "text": m.content}],
        }
        for m in messages
    ]


def normalize_youtube_query(messages: list[LlmMessage]) -> NormalizedQuery:
    resp = _get_openai_client().responses.create(
        model="gpt-5.2",
        input=_messages_to_openai_input(messages),
        # If you want stricter behavior, you can add:
        # temperature=0,
    )

    # Most reliable: treat model output as JSON string and validate locally.
    raw = resp.output_text.strip()
    data = json.loads(raw)

    # Construct the typed result (dataclass/pydantic/etc.)
    return NormalizedQuery(
        query=str(data["query"]),
        includes=list(data.get("includes", [])),
        excludes=list(data.get("excludes", [])),
        phrases=list(data.get("phrases", [])),
        channels=list(data.get("channels", [])),
        notes=str(data.get("notes", "")),
    )


def post_filter(
    results: list[dict[str, Any]],
    normalized: NormalizedQuery,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []

    for r in results:
        title = r.title.lower()
        description = (r.description or "").lower()

        text = f"{title} {description}"

        # required terms
        if not all(term.lower() in text for term in normalized.includes):
            continue

        # excluded terms
        if any(term.lower() in text for term in normalized.excludes):
            continue

        # phrases
        if not all(phrase.lower() in text for phrase in normalized.phrases):
            continue

        # channel name check (if needed)
        if normalized.channels:
            if r.channel_title not in normalized.channels:
                continue

        filtered.append(r)

    return filtered



if __name__ == "__main__":
    nq = normalize_youtube_query(
        'python list comprehension OR "lambda functions" -shorts channel:"Corey Schafer"'
    )
    print(nq.query)
    print(nq)

