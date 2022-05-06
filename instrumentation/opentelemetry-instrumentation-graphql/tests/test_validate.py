from graphql import (
    GraphQLSchema,
    GraphQLObjectType,
    GraphQLString,
    GraphQLField,
    parse,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind

import opentelemetry.instrumentation.graphql
from opentelemetry.instrumentation.graphql import GraphQLInstrumentator


class TestGraphQLValidateIntegration(TestBase):
    q = """
        query Q { a }
        mutation M { c }
        subscription S { a }
    """

    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        GraphQLInstrumentator().instrument()

        self.schema = GraphQLSchema(
            GraphQLObjectType("Q", {"a": GraphQLField(GraphQLString)}),
            GraphQLObjectType("M", {"c": GraphQLField(GraphQLString)}),
            GraphQLObjectType("S", {"a": GraphQLField(GraphQLString)}),
        )
        self.document = parse("query Q { a }")
        self.invalid_doc = parse("query Q { a err }")

        from graphql import validate
        self.validate = validate

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            GraphQLInstrumentator().uninstrument()

    def test_instrumentor(self):
        self.assertEqual(len(self.get_finished_spans()), 0)

        self.validate(self.schema, self.document)
        spans_list = self.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        span = spans_list[0]
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.graphql
        )

        GraphQLInstrumentator().uninstrument()
        self.validate(self.schema, self.document)
        self.assertEqual(len(self.get_finished_spans()), 1)

    def test_span(self):
        self.validate(self.schema, self.document)

        span = self.get_finished_spans()[0]
        self.assertEqual(span.name, "graphql.validate")
        self.assertEqual(span.parent, None)
        self.assertEqual(span.kind, SpanKind.INTERNAL)

    def test_record_exception(self):
        self.validate(self.schema, self.invalid_doc)
        spans = self.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(len(span.events), 1)

        event = span.events[0]
        self.assertEqual(event.name, "exception")
        self.assertEqual(event.attributes["exception.type"], "GraphQLError")
        self.assertEqual(event.attributes["exception.stacktrace"], "NoneType: None\n")
        self.assertEqual(event.attributes["exception.escaped"], "False")
        self.assertEqual(
            event.attributes["exception.message"],
            "Cannot query field 'err' on type 'Q'.\n\nGraphQL request:1:13\n1 "
            "| query Q { a err }\n  |             ^"
        )
