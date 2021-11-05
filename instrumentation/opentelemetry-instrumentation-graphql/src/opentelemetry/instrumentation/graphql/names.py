class AttributeName:
    COMPONENT = "graphql"
    SOURCE = "graphql.source"
    FIELD_NAME = "graphql.field.name"
    FIELD_PATH = "graphql.field.path"
    FIELD_TYPE = "graphql.field.type"
    OPERATION = "graphql.operation.name"
    VARIABLES = "graphql.variables."
    ERROR_VALIDATION_NAME = "graphql.validation.error"


class SpanName:
    EXECUTE = "graphql.execute"
    PARSE = "graphql.parse"
    RESOLVE = "graphql.resolve"
    VALIDATE = "graphql.validate"
    SCHEMA_VALIDATE = "graphql.validate_schema"
    SCHEMA_PARSE = "graphql.parse_schema"
