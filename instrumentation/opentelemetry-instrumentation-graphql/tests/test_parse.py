from opentelemetry.trace import SpanKind

import opentelemetry.instrumentation.graphql
from opentelemetry.instrumentation.graphql import GraphQLInstrumentator
from tests import GraphQLInstrumentationTestBase


class TestGraphQLParseIntegration(GraphQLInstrumentationTestBase):
    q = "query Q { a }"

    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        GraphQLInstrumentator().instrument()
        
        from graphql import parse
        self.parse = parse

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            GraphQLInstrumentator().uninstrument()

    def test_instrumentor(self):
        self.assertEqual(len(self.get_finished_spans()), 0)

        self.parse(self.q)
        spans_list = self.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        span = spans_list[0]
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.graphql
        )

        GraphQLInstrumentator().uninstrument()
        self.parse(self.q)
        self.assertEqual(len(self.get_finished_spans()), 1)

    def test_span(self):
        self.parse(self.q)

        span = self.get_finished_spans()[0]
        self.assertEqual(span.name, "graphql.parse")
        self.assertEqual(span.parent, None)
        self.assertEqual(span.kind, SpanKind.INTERNAL)

    def test_attributes(self):
        self.parse(self.q)
        span = self.get_finished_spans()[0]
        self.assertEqual(span.attributes["graphql.source"], self.q)
