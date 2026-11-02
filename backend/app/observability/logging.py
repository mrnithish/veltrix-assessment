"""Structured JSON logging with request context and a PII scrubber on every event."""

from __future__ import annotations

import logging
import sys

import structlog

from app.observability.pii import scrub_obj

_configured = False


def _scrub_processor(_logger, _method, event_dict):
    return scrub_obj(event_dict)


def _otel_ids(_logger, _method, event_dict):
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        if ctx and ctx.is_valid:
            event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
            event_dict.setdefault("span_id", format(ctx.span_id, "016x"))
    except Exception:  # pragma: no cover - tracing is optional
        pass
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level, logging.INFO))
    for noisy in ("httpx", "httpcore", "urllib3", "openai", "anthropic", "RapidOCR", "rapidocr"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _otel_ids,
            _scrub_processor,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "app"):
    return structlog.get_logger(name)


bind_context = structlog.contextvars.bind_contextvars
clear_context = structlog.contextvars.clear_contextvars
