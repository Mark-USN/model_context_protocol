from __future__ import annotations

import json
import os
from dataclasses import dataclass

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


def normalize_youtube_query(search_string: str) -> NormalizedQuery:
    # Use YOUR prompt generator to create the content
    prompt_messages = youtube_query_normalizer_prompt(search_string=search_string)

    # Convert your Message objects into OpenAI "input" messages if needed
    # (Assuming Message has .content and maybe a role; if not, adapt this part.)
    input_messages = [{"role": "user", "content": prompt_messages[0].content}]

    resp = _get_openai_client().responses.create(
        model="gpt-5.2",
        input=input_messages,
        text=YOUTUBE_QUERY_SCHEMA,  # enforce schema
    )

    data = json.loads(resp.output_text)
    return NormalizedQuery(**data)


def post_filter(
    results: list[YouTubeResult],
    normalized: NormalizedQuery,
) -> list[YouTubeResult]:
    filtered: list[YouTubeResult] = []

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

