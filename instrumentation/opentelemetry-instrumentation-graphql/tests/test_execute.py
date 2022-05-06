from graphql import (
    GraphQLSchema,
    GraphQLObjectType,
    GraphQLString,
    GraphQLField,
    parse,
)
from opentelemetry.test.test_base import TestBase

from opentelemetry.instrumentation.graphql import GraphQLInstrumentator


class TestGraphQLExecuteIntegration(TestBase):
    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        GraphQLInstrumentator().instrument()

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            GraphQLInstrumentator().uninstrument()

    def execute_schema(self, schema, query, data):
        from graphql import execute_sync

        document = parse(query)
        return execute_sync(schema, document, data)

    def test_instrumentor(self):
        self.assertEqual(len(self.get_finished_spans()), 0)

        schema = GraphQLSchema(
            GraphQLObjectType("Q", {"a": GraphQLField(GraphQLString)}),
            GraphQLObjectType("M", {"c": GraphQLField(GraphQLString)}),
            GraphQLObjectType("S", {"a": GraphQLField(GraphQLString)}),
        )
        query = "query Q { a }"
        data = {"a": "b"}

        # This creates a single span because the schema doesn't have resolvers
        result = self.execute_schema(schema, query, data)
        self.assertEqual(result, ({"a": "b"}, None))
        self.assertEqual(len(self.get_finished_spans()), 1)

        GraphQLInstrumentator().uninstrument()
        result = self.execute_schema(schema, query, data)
        self.assertEqual(result, ({"a": "b"}, None))
        self.assertEqual(len(self.get_finished_spans()), 1)

    def test_resolve_span(self):
        self.assertEqual(len(self.get_finished_spans()), 0)

        def resolver(root, info, **args):
            return "Lucas Lee"

        schema = GraphQLSchema(
            GraphQLObjectType("Query", {
                "withResolver": GraphQLObjectType("M", {
                    "c": GraphQLField(GraphQLString, resolve=resolver)
                }),
            })
        )
        data = {"withResolver": {}}
        query = "query { withResolver { c } }"

        result = self.execute_schema(schema, query, data)
        self.assertEqual(result, ({"withResolver": {"c": "Lucas Lee"}}, None))
        spans = self.get_finished_spans()
        self.assertEqual(len(spans), 2)

        resolve = spans[0]
        execute = spans[1]
        self.assertEqual(resolve.name, "graphql.resolve")
        self.assertEqual(execute.name, "graphql.execute")
        self.assertEqual(resolve.parent.span_id, execute.context.span_id)

        self.assertSpanHasAttributes(resolve, {
            "graphql.field.name": "c",
            "graphql.field.path": "withResolver.c",
            "graphql.field.type": "String",
            "graphql.source": " c",
        })

    def test_nested_resolvers(self):
        self.assertEqual(len(self.get_finished_spans()), 0)

        def a_resolver(root, info, **args):
            return {"secondResolver": {"c": None}}

        def b_resolver(root, info, **args):
            return "Lucas Lee"

        schema = GraphQLSchema(
            GraphQLObjectType("Query", {
                "firstResolver": GraphQLField(
                    GraphQLObjectType("A", {
                        "secondResolver": GraphQLObjectType("B", {
                            "c": GraphQLField(GraphQLString, resolve=b_resolver)
                        })
                    }),
                    resolve=a_resolver
                )
            })
        )
        data = {"firstResolver": {}}
        query = "query { firstResolver { secondResolver { c } } }"

        result = self.execute_schema(schema, query, data)
        self.assertEqual(
            result,
            ({"firstResolver": {"secondResolver": {"c": "Lucas Lee"}}}, None)
        )

        spans = self.get_finished_spans()
        self.assertEqual(len(spans), 3)

        first, second, execute = spans
        self.assertEqual(second.name, "graphql.resolve")
        self.assertEqual(second.parent.span_id, first.context.span_id)

        self.assertEqual(first.name, "graphql.resolve")
        self.assertEqual(first.parent.span_id, execute.context.span_id)

        self.assertEqual(execute.name, "graphql.execute")
