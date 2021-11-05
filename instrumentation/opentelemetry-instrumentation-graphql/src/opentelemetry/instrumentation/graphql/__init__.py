from logging import getLogger
from typing import Collection, Optional

import graphql
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import get_tracer
from wrapt import wrap_function_wrapper as _wrap

from opentelemetry.instrumentation.graphql.execute import _wrap_execute
from opentelemetry.instrumentation.graphql.package import _instruments
from opentelemetry.instrumentation.graphql.parse import _wrap_parse
from opentelemetry.instrumentation.graphql.utils import (
    add_span_source,
    Config,
)
from opentelemetry.instrumentation.graphql.validate import _wrap_validate
from opentelemetry.instrumentation.graphql.version import __version__

logger = getLogger(__name__)


class GraphQLInstrumentator(BaseInstrumentor):
    """An instrumentor for graphql-core
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(
        self,
        allow_values=False,
        merge_items=False,
        depth: Optional[int] = None,
        **kwargs
    ):
        """
        Instruments graphql module
        """
        config = Config(allow_values, merge_items, depth)
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(__name__, __version__, tracer_provider)
        response_hook = kwargs.get("response_hook")

        _wrap(
            graphql,
            "execute",
            _wrap_execute(tracer, config, response_hook=response_hook),
        )
        _wrap(
            graphql,
            "parse",
            _wrap_parse(tracer, allow_values),
        )
        _wrap(
            graphql,
            "validate",
            _wrap_validate(tracer),
        )

    def _uninstrument(self, **kwargs):
        unwrap(graphql, "parse")
        unwrap(graphql, "execute")
        unwrap(graphql, "validate")
