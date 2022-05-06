from graphql import build_ast_schema, parse
from opentelemetry.test.test_base import TestBase

try:
    from graphql import build_schema  # graphql-core>=3
except ImportError:
    def build_schema(source, no_location=False, allow_legacy_fragment_variables=False):
        return build_ast_schema(
            parse(
                source,
                no_location=no_location,
                allow_legacy_fragment_variables=allow_legacy_fragment_variables,
            )
        )


class GraphQLInstrumentationTestBase(TestBase):
    @staticmethod
    def build_schema(source):
        return build_schema(
            source, no_location=False, allow_legacy_fragment_variables=False
        )
