"""OpenTelemetry setup (OTLP -> Phoenix/any collector) and a per-request trace recorder.

Every chat request produces:
  * OTel spans (exported when OTEL_EXPORTER_OTLP_ENDPOINT is set), and
  * a RequestTrace saved in the state DB (GET /traces/{request_id}) for the UI.
Values are PII-scrubbed before they are attached to spans or traces.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.observability.pii import scrub_obj

_provider_set = False


def setup_tracing(otlp_endpoint: str, service_name: str = "veltrix-api") -> None:
    global _provider_set
    if _provider_set:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = otlp_endpoint.rstrip("/")
        if not endpoint.endswith("/v1/traces"):
            endpoint += "/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _provider_set = True


def tracer():
    return trace.get_tracer("veltrix")


def _attr(value: Any):
    if isinstance(value, (str, bool, int, float)):
        return value
    return json.dumps(value, default=str)[:8000]


class RequestTrace:
    """Collects the steps of one chat request for the trace store, mirrored as OTel spans."""

    def __init__(self, request_id: str, session_id: str, employee_id: str):
        self.request_id = request_id
        self.session_id = session_id
        self.employee_id = employee_id
        self.started = time.perf_counter()
        self.steps: list[dict] = []
        self.llm_calls: list[dict] = []
        self.data: dict[str, Any] = {}
        self.events = None  # optional EventSink (streaming); set by the agent

    @contextmanager
    def step(self, name: str, **attrs):
        record = {"name": name, "start_ms": round((time.perf_counter() - self.started) * 1000, 1)}
        record.update(scrub_obj(attrs))
        with tracer().start_as_current_span(name) as span:
            for k, v in record.items():
                if k not in ("name", "start_ms"):
                    span.set_attribute(k, _attr(v))
            t0 = time.perf_counter()
            try:
                yield record
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                span.record_exception(exc)
                raise
            finally:
                record["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                for k, v in list(record.items()):
                    if k not in ("name", "start_ms", "duration_ms"):
                        span.set_attribute(k, _attr(scrub_obj(v)))
                self.steps.append(scrub_obj(record))

    def set(self, key: str, value: Any) -> None:
        self.data[key] = scrub_obj(value)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "employee_id": self.employee_id,
            "total_ms": round((time.perf_counter() - self.started) * 1000, 1),
            "steps": sorted(self.steps, key=lambda s: s["start_ms"]),
            "llm_calls": self.llm_calls,
            **self.data,
        }
