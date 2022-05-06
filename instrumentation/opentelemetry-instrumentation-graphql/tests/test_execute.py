from graphql import (
    GraphQLSchema,
    GraphQLObjectType,
    GraphQLString,
    GraphQLField,
    parse,
)

from opentelemetry.instrumentation.graphql import GraphQLInstrumentator
from opentelemetry.instrumentation.graphql.utils import is_v2
from tests import GraphQLInstrumentationTestBase


class TestGraphQLExecuteIntegration(GraphQLInstrumentationTestBase):
    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        GraphQLInstrumentator().instrument()

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            GraphQLInstrumentator().uninstrument()

    def execute_schema(self, schema, query, data):
        from graphql import execute

        document = parse(query)
        return execute(schema, document, data)

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
        self.assertEqual(result.data, {"a": "b"})
        self.assertEqual(len(self.get_finished_spans()), 1)

        GraphQLInstrumentator().uninstrument()
        result = self.execute_schema(schema, query, data)
        self.assertEqual(result.data, {"a": "b"})
        self.assertEqual(len(self.get_finished_spans()), 1)

    def graphql_field(self, typ, resolver):
        if is_v2:
            return GraphQLField(typ, resolver=resolver)
        return GraphQLField(typ, resolve=resolver)

    def test_resolve_span(self):
        self.assertEqual(len(self.get_finished_spans()), 0)

        def resolver(root, info, **args):
            return "Lucas Lee"

        schema = GraphQLSchema(
            GraphQLObjectType("Query", {
                "withResolver": GraphQLField(
                    GraphQLObjectType("M", {
                        "lee": self.graphql_field(GraphQLString, resolver)
                    })
                ),
            })
        )
        data = {"withResolver": {}}
        query = "query { withResolver { lee } }"

        result = self.execute_schema(schema, query, data)
        self.assertEqual(result.data, {"withResolver": {"lee": "Lucas Lee"}})
        spans = self.get_finished_spans()
        self.assertEqual(len(spans), 2)

        resolve = spans[0]
        execute = spans[1]
        self.assertEqual(resolve.name, "graphql.resolve")
        self.assertEqual(execute.name, "graphql.execute")
        self.assertEqual(resolve.parent.span_id, execute.context.span_id)

        self.assertSpanHasAttributes(resolve, {
            "graphql.field.name": "lee",
            "graphql.field.path": "withResolver.lee",
            "graphql.field.type": "String",
            "graphql.source": "lee",
        })

    def test_schema_with_wrapping_type(self):
        self.assertEqual(len(self.get_finished_spans()), 0)

        def resolver(root, info, **args):
            return ["Scott Pilgrim", "Kim Pine", "Lucas Lee"]

        data = {}
        query = "query { wrappingType }"
        schema = self.build_schema("""
            type Query {
                wrappingType: [String!]!
            }
            schema {
                query: Query
            }
        """)
        if is_v2:
            schema._type_map["Query"].fields["wrappingType"].resolver = resolver
        else:
            schema.type_map["Query"].fields["wrappingType"].resolve = resolver

        result = self.execute_schema(schema, query, data)
        self.assertEqual(
            result.data, {"wrappingType": ["Scott Pilgrim", "Kim Pine", "Lucas Lee"]}
        )
        spans = self.get_finished_spans()
        self.assertEqual(len(spans), 2)

    def test_nested_resolvers(self):
        self.assertEqual(len(self.get_finished_spans()), 0)

        def a_resolver(root, info, **args):
            return {"secondResolver": {"c": None}}

        def b_resolver(root, info, **args):
            return "Lucas Lee"

        schema = GraphQLSchema(
            GraphQLObjectType("Query", {
                "firstResolver": self.graphql_field(
                    GraphQLObjectType("A", {
                        "secondResolver": GraphQLField(
                            GraphQLObjectType("B", {
                                "c": self.graphql_field(
                                    GraphQLString, resolver=b_resolver
                                )
                            })
                        )
                    }),
                    resolver=a_resolver
                )
            })
        )
        data = {"firstResolver": {}}
        query = "query { firstResolver { secondResolver { c } } }"

        result = self.execute_schema(schema, query, data)
        self.assertEqual(
            result.data,
            {"firstResolver": {"secondResolver": {"c": "Lucas Lee"}}}
        )

        spans = self.get_finished_spans()
        self.assertEqual(len(spans), 3)

        first, second, execute = spans
        self.assertEqual(second.name, "graphql.resolve")
        self.assertEqual(second.parent.span_id, first.context.span_id)

        self.assertEqual(first.name, "graphql.resolve")
        self.assertEqual(first.parent.span_id, execute.context.span_id)

        self.assertEqual(execute.name, "graphql.execute")
