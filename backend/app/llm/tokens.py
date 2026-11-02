"""Token counting with tiktoken cl100k_base (required for the corpus budget, whatever the LLM)."""

from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _encoding():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text or "", disallowed_special=()))


def truncate_tokens(text: str, max_tokens: int) -> str:
    enc = _encoding()
    ids = enc.encode(text or "", disallowed_special=())
    return text if len(ids) <= max_tokens else enc.decode(ids[:max_tokens])
