from typing import Optional, Dict

from opentelemetry.trace import Span

try:
    from graphql import DocumentNode
except ImportError:
    from graphql.language.ast import Document as DocumentNode


OTEL_PATCHED_ATTR = "otel_patched"
OTEL_GRAPHQL_DATA_ATTR = "otel_graphql_data"


class OTELGraphQLField:
    """Composition to store in context the span and error related to a GraphQL path"""
    parent: Optional["OTELGraphQLField"]
    error: Optional[Exception]
    span: Span

    def __init__(self, parent, span, error=None):
        self.parent = parent
        self.span = span
        self.error = error


class OTELGraphQLData:
    """An instance of this class is stored in the GraphQL execution context, in
    the attr `OTEL_GRAPHQL_DATA_ATTR`"""
    span: Span
    fields: Dict[str, OTELGraphQLField]
    source: DocumentNode

    def __init__(self, span, source, fields=None):
        if fields is None:
            fields = {}

        self.span = span
        self.fields = fields
        self.source = source
