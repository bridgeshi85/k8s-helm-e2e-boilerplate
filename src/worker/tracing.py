import os

from opentelemetry import baggage as otel_baggage
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Baggage keys that should be copied onto every span as an attribute (e.g. so
# Tempo/Grafana can filter traces by "which k6 load-test run produced this").
# Kept in sync with src/backend/tracing.py's copy of this processor.
_BAGGAGE_SPAN_ATTRIBUTE_KEYS = {"test.load_test_id"}


class BaggageToAttributesSpanProcessor(SpanProcessor):
    """Copies selected OTel Baggage entries onto every span as attributes.

    The backend injects baggage into the RabbitMQ message headers alongside
    the trace context (`propagate.inject`); this processor promotes it back
    into span attributes here too, so the worker's spans stay tagged/filterable
    the same way as the backend's.
    """

    def on_start(self, span, parent_context: Context | None = None) -> None:
        for key, value in otel_baggage.get_all(parent_context).items():
            if key in _BAGGAGE_SPAN_ATTRIBUTE_KEYS:
                span.set_attribute(key, value)

    def on_end(self, span: ReadableSpan) -> None:
        pass


def setup_tracing(default_service_name: str) -> trace.Tracer:
    """Initialize the OTel TracerProvider + OTLP exporter.

    Also injects otelTraceID/otelSpanID into every log record so Loki logs
    can be correlated to Tempo traces (see logging_config.py format string).
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    # OTEL_SERVICE_NAME（标准 OTel 环境变量）优先于调用方传入的默认值
    service_name = os.getenv("OTEL_SERVICE_NAME", default_service_name)

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    provider.add_span_processor(BaggageToAttributesSpanProcessor())
    trace.set_tracer_provider(provider)

    LoggingInstrumentor().instrument(set_logging_format=False)

    return trace.get_tracer(service_name)
