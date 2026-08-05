import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


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
    trace.set_tracer_provider(provider)

    LoggingInstrumentor().instrument(set_logging_format=False)

    return trace.get_tracer(service_name)
