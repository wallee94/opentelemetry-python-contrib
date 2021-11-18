from typing import Optional, Callable, Any, Dict, Type

import graphql
import wrapt

from opentelemetry import trace
from opentelemetry.instrumentation.graphql.context import (
    OTEL_PATCHED_ATTR,
    OTEL_GRAPHQL_DATA_ATTR,
    OTELGraphQLData,
)
from opentelemetry.instrumentation.graphql.utils import (
    Config,
    path_to_list,
    create_field_if_not_exists,
    get_parent_field,
    ProcessedArgs,
    create_execute_span,
)


def _wrap_execute(tracer, config, response_hook=None):
    # pylint: disable=R0912
    def wrapper(wrapped, _, args, kwargs):
        processed_args = _wrap_execute_args(tracer, config, *args, **kwargs)
        span = create_execute_span(tracer, config, processed_args)

        setattr(
            processed_args.context_value,
            OTEL_GRAPHQL_DATA_ATTR,
            OTELGraphQLData(
                source=processed_args.document, span=span, fields={}
            ),
        )
        with trace.use_span(span=span) as _span:
            res = wrapped(**processed_args._asdict())
            if callable(response_hook):
                response_hook(span, res)

            return res

    return wrapper


def wrap_field_resolver(tracer, config: Config, resolver: Callable):
    @wrapt.decorator
    def _wrap_field_resolver(wrapped, _, args, kwargs):
        def _resolver(root: Any, info: graphql.GraphQLResolveInfo, *args_):
            if not hasattr(info.context, OTEL_GRAPHQL_DATA_ATTR):
                return wrapped(*args_, **kwargs)

            path = path_to_list(config.merge_items, info.path)

            depth = len(path)
            should_end_span = False
            if depth > config.depth >= 0:
                field = get_parent_field(info.context, path)
            else:
                field, should_end_span = create_field_if_not_exists(
                    tracer, config, info, path
                )

            with trace.use_span(span=field.span, end_on_exit=should_end_span):
                return wrapped(*args_, **kwargs)

        return _resolver(*args, **kwargs)

    wrapped_field_resolver = _wrap_field_resolver(resolver)
    setattr(wrapped_field_resolver, OTEL_PATCHED_ATTR, True)
    return wrapped_field_resolver


def wrap_fields(typ: graphql.GraphQLObjectType, tracer, config: Config) -> None:
    """
    Walks through the typ fields recursively, wrapping their resolvers
    """
    if not typ or not typ.fields or getattr(typ, OTEL_PATCHED_ATTR, False):
        return

    setattr(typ, OTEL_PATCHED_ATTR, True)
    for field in typ.fields.values():
        if field.resolve:
            field.resolve = wrap_field_resolver(tracer, config, field.resolve)

        if field.type:
            unwrapped_type = field.type
            while isinstance(unwrapped_type, graphql.GraphQLWrappingType):
                unwrapped_type = field.type.of_type

            wrap_fields(unwrapped_type, tracer, config)


def _wrap_execute_args(
    tracer,
    config: Config,
    schema: graphql.GraphQLSchema,
    document: graphql.DocumentNode,
    root_value: Any = None,
    context_value: Any = None,
    variable_values: Optional[Dict[str, Any]] = None,
    operation_name: Optional[str] = None,
    field_resolver: Optional[graphql.GraphQLFieldResolver] = None,
    type_resolver: Optional[graphql.GraphQLTypeResolver] = None,
    middleware: Optional[graphql.Middleware] = None,
    execution_context_class: Optional[Type[graphql.ExecutionContext]] = None,
    is_awaitable: Optional[Callable[[Any], bool]] = None,
) -> ProcessedArgs:
    """
    Wraps `field_resolver` and walks the schema to wrap also the inner fields and
    resolvers, returning a ProcessedArgs namedtuple with the args wrapped.

    Beside `tracer` and `schema`, it takes the same args that graphql.execute
    """
    if not context_value:
        context_value = {}

    processed_args = ProcessedArgs(
        schema,
        document,
        root_value,
        context_value,
        variable_values,
        operation_name,
        field_resolver,
        type_resolver,
        middleware,
        execution_context_class,
        is_awaitable,
    )
    if hasattr(context_value, OTEL_GRAPHQL_DATA_ATTR):
        return processed_args

    if callable(field_resolver) and not hasattr(
        field_resolver, OTEL_PATCHED_ATTR
    ):
        field_resolver = wrap_field_resolver(tracer, config, field_resolver)

    if schema:
        wrap_fields(schema.query_type, tracer, config)
        wrap_fields(schema.mutation_type, tracer, config)

    processed_args = processed_args._replace(field_resolver=field_resolver)
    return processed_args
