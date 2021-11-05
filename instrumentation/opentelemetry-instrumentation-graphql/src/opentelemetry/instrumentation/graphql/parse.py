from opentelemetry.trace import SpanKind

from opentelemetry.instrumentation.graphql.names import SpanName
from opentelemetry.instrumentation.graphql.utils import (
    get_operation,
    add_span_source,
)


def _wrap_parse(tracer, allow_values: bool = False):
    # pylint: disable=R0912
    def wrapper(wrapped, _, args, kwargs):
        with tracer.start_as_current_span(
            SpanName.PARSE,
            kind=SpanKind.INTERNAL,
        ) as span:
            res = wrapped(*args, **kwargs)
            operation = get_operation(res)
            if not operation:
                span.update_name(SpanName.SCHEMA_PARSE)
            else:
                add_span_source(span, res.loc, allow_values)
            return res

    return wrapper
