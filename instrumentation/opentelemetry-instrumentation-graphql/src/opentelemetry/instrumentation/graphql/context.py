from typing import Optional, Dict

import graphql
from opentelemetry.trace import Span

OTEL_PATCHED_ATTR = "otel_patched"
OTEL_GRAPHQL_DATA_ATTR = "otel_graphql_data"


class OTELGraphQLField:
    parent: Optional["OTELGraphQLField"]
    error: Optional[Exception]
    span: Span

    def __init__(self, parent, span, error=None):
        self.parent = parent
        self.span = span
        self.error = error


class OTELGraphQLData:
    span: Span
    fields: Dict[str, OTELGraphQLField]
    source: graphql.DocumentNode

    def __init__(self, span, source, fields=None):
        if fields is None:
            fields = {}

        self.span = span
        self.fields = fields
        self.source = source
