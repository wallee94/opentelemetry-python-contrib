from collections import namedtuple
from typing import Optional, List, Any, Tuple

import graphql
from opentelemetry.trace import Span, Tracer, set_span_in_context

from opentelemetry.instrumentation.graphql.context import (
    OTEL_GRAPHQL_DATA_ATTR,
    OTELGraphQLField,
)
from opentelemetry.instrumentation.graphql.names import AttributeName, SpanName

ProcessedArgs = namedtuple(
    "ProcessedArgs",
    (
        "schema",
        "document",
        "root_value",
        "context_value",
        "variable_values",
        "operation_name",
        "field_resolver",
        "type_resolver",
        "middleware",
        "execution_context_class",
        "is_awaitable",
    ),
)

Config = namedtuple("Config", ("allow_values", "merge_items", "depth"))


def resolver_span(
    tracer: Tracer,
    config: Config,
    info: graphql.GraphQLResolveInfo,
    path: List[str],
    parent_span: Optional[Span],
) -> Span:
    context = None
    if parent_span:
        context = set_span_in_context(parent_span)

    span = tracer.start_span(
        name=SpanName.RESOLVE,
        context=context,
        attributes={
            AttributeName.FIELD_NAME: info.field_name,
            AttributeName.FIELD_PATH: ".".join(path),
            AttributeName.FIELD_TYPE: str(info.return_type),
        },
    )

    otel_graphql_data = getattr(info.context, OTEL_GRAPHQL_DATA_ATTR)
    document = otel_graphql_data.source
    for field_node in info.field_nodes:
        if field_node.kind == "field":
            start = end = None
            if field_node.loc:
                start, end = field_node.loc.start, field_node.loc.end

            add_span_source(
                span, document.loc, config.allow_values, start, end
            )
            break

    return span


def add_field(context: Any, path: List[str], field: OTELGraphQLField) -> None:
    otel_graphql_data = getattr(context, OTEL_GRAPHQL_DATA_ATTR)
    otel_graphql_data.fields[".".join(path)] = field


def get_field(context: Any, path: List[str]) -> Optional[OTELGraphQLField]:
    """
    If an OTELGraphQLField with an open span was already set in the context for
    this path, return it
    """
    otel_graphql_data = getattr(context, OTEL_GRAPHQL_DATA_ATTR)
    return otel_graphql_data.fields.get(".".join(path))


def get_parent_field(context: Any, path: List[str]) -> OTELGraphQLField:
    """
    Search for any parent OTELGraphQLField in the path that has been stored in
    the context. If none is found, a new OTELGraphQLField is returned with parent None
    and the main execution span
    """
    for i in range(len(path), -1, -1):
        field = get_field(context, path[:i])
        if field:
            return field

    otel_graphql_data = getattr(context, OTEL_GRAPHQL_DATA_ATTR)
    return OTELGraphQLField(parent=None, span=otel_graphql_data.span)


def create_field_if_not_exists(
    tracer: Tracer,
    config: Config,
    info: graphql.GraphQLResolveInfo,
    path: List[str],
) -> Tuple[OTELGraphQLField, bool]:
    """
    A convenience method for looking up an object with the given path.
    Returns a tuple of (field, created), where field is the retrieved or created field
    and created is a boolean specifying whether a new field was created.
    """
    span_added = False
    field = get_field(info.context, path)
    if not field:
        span_added = True
        parent = get_parent_field(info.context, path)
        span = resolver_span(tracer, config, info, path, parent.span)
        field = OTELGraphQLField(parent, span, None)

        add_field(info.context, path, field)

    return field, span_added


def path_to_list(
    merge_items: bool, path: graphql.pyutils.path.Path
) -> List[str]:
    """
    Converts a GraphQL path into a list. If `merge_items` is False, the same field in
    a different element in a list are treated as diff fields with diff spans.
    """
    flattened = []
    cur = path
    while cur:
        key = path.key
        if merge_items and isinstance(key, int):
            key = "*"
        flattened.append(str(key))
        cur = cur.prev

    flattened.reverse()
    return flattened


def get_operation(
    document: graphql.DocumentNode, operation_name: Optional[str] = None
) -> Optional[graphql.OperationDefinitionNode]:
    """
    Returns the operation DefinitionNode in `document`. If `operation_name` is
    provided, the operation's name must match
    """
    if not document or not document.definitions:
        return None

    for definition in document.definitions:
        if isinstance(definition, graphql.OperationDefinitionNode):
            if operation_name is None:
                return definition
            elif definition.name and definition.name.value == operation_name:
                return definition

    return None


def add_span_source(
    span: Span, loc: graphql.Location, allow_values: bool, start=None, end=None
) -> None:
    src = _get_source_from_loc(loc, allow_values, start, end)
    span.set_attribute(AttributeName.SOURCE, src)


def _get_source_from_loc(
    loc: graphql.Location, allow_values, start, end
) -> str:
    src = ""
    if not loc or not loc.start_token:
        return src

    start = start or loc.start
    end = end or loc.end

    prev_line = -1
    nxt = loc.start_token.next
    kinds_to_remove = [
        graphql.TokenKind.FLOAT,
        graphql.TokenKind.STRING,
        graphql.TokenKind.INT,
        graphql.TokenKind.BLOCK_STRING,
    ]
    while nxt:
        if nxt.start < start:
            nxt = nxt.next
            prev_line = nxt.line if nxt else None
            continue
        if nxt.end > end:
            nxt = nxt.next
            prev_line = nxt.line if nxt else None
            continue

        space = ""
        value = nxt.value or nxt.kind
        if not allow_values and nxt.kind in kinds_to_remove:
            value = "****"
        if nxt.kind == graphql.TokenKind.STRING:
            value = '"' + value + '"'
        if nxt.kind == graphql.TokenKind.EOF:
            value = ""

        if nxt.line > prev_line:
            src += "\n" * (nxt.line - prev_line)
            prev_line = nxt.line
            space = " " * (nxt.column - 1)
        elif nxt.prev and nxt.line == nxt.prev.line:
            space = " " * (nxt.start - (nxt.prev.end or 0))

        src += space + value
        if nxt:
            nxt = nxt.next

    return src


def create_execute_span(tracer, config: Config, processed_args: ProcessedArgs):
    operation = get_operation(
        processed_args.document,
        processed_args.operation_name,
    )
    span = tracer.start_span(name=SpanName.EXECUTE)
    if operation:
        name = operation.operation.name
        if name:
            span.set_attribute(AttributeName.OPERATION, str(name))

    else:
        # Invalid operation name
        name = ""
        if processed_args.operation_name:
            name = f'"{processed_args.operation_name}" '

        name = f"Operation {name}not supported"
        span.set_attribute(AttributeName.OPERATION, name)

    if processed_args.document and processed_args.document.loc:
        add_span_source(span, processed_args.document.loc, config.allow_values)

    if processed_args.variable_values and config.allow_values:
        for k, v in processed_args.variable_values.items():
            span.set_attribute(f"{AttributeName.VARIABLES}{k}", str(v))

    return span
