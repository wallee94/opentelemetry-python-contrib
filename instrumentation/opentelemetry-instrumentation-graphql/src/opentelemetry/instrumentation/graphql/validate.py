from typing import cast

from opentelemetry.trace import SpanKind, Span

from opentelemetry.instrumentation.graphql.names import SpanName


def _wrap_validate(tracer):
    # pylint: disable=R0912
    def wrapper(wrapped, _, args, kwargs):
        if len(args) >= 2:
            document_ast = args[1]
        else:
            document_ast = kwargs["document_ast"]

        with tracer.start_as_current_span(
            SpanName.VALIDATE,
            kind=SpanKind.INTERNAL,
        ) as span:
            span = cast(Span, span)
            errors = wrapped(*args, **kwargs)
            if not document_ast.loc:
                span.update_name(SpanName.SCHEMA_VALIDATE)

            for err in errors:
                span.record_exception(err)
            return errors

    return wrapper
