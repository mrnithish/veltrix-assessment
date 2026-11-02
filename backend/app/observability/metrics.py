"""Prometheus metrics exposed at GET /metrics."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

CHAT_REQUESTS = Counter("veltrix_chat_requests_total", "Chat requests by route", ["route"])
CHAT_LATENCY = Histogram(
    "veltrix_chat_latency_seconds", "End-to-end /chat latency", buckets=(0.5, 1, 2, 4, 8, 12, 16, 20, 25, 30, 45)
)
HTTP_ERRORS = Counter("veltrix_chat_http_errors_total", "4xx/5xx responses from /chat", ["status"])
TOOL_CALLS = Counter("veltrix_tool_calls_total", "Tool calls by name and status", ["tool", "status"])
LLM_CALLS = Counter("veltrix_llm_calls_total", "LLM calls by purpose and outcome", ["purpose", "outcome"])
LLM_LATENCY = Histogram(
    "veltrix_llm_latency_seconds", "LLM call latency", ["purpose"], buckets=(0.5, 1, 2, 4, 8, 12, 16, 20, 30)
)
LLM_TOKENS = Counter("veltrix_llm_tokens_total", "LLM tokens", ["purpose", "kind"])
CORPUS_TOKENS = Histogram(
    "veltrix_llm_corpus_tokens", "Corpus tokens per LLM call (budget 3000)", ["purpose"],
    buckets=(0, 250, 500, 1000, 1500, 2000, 2500, 3000),
)
SANDBOX_RUNS = Counter("veltrix_codemode_runs_total", "Code Mode sandbox executions", ["outcome"])
