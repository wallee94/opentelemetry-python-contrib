from logging import getLogger
from typing import Collection, Optional

import graphql
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import get_tracer
from wrapt import wrap_object, FunctionWrapper

from opentelemetry.instrumentation.graphql.execute import _wrap_execute
from opentelemetry.instrumentation.graphql.package import _instruments
from opentelemetry.instrumentation.graphql.parse import _wrap_parse
from opentelemetry.instrumentation.graphql.utils import (
    add_span_source,
    Config,
    is_v2,
)
from opentelemetry.instrumentation.graphql.validate import _wrap_validate
from opentelemetry.instrumentation.graphql.version import __version__

logger = getLogger(__name__)


class GraphQLInstrumentator(BaseInstrumentor):
    """An instrumentor for graphql-core
    See `BaseInstrumentor`
    """

    _enabled = True

    @classmethod
    def enabled(cls):
        return cls._enabled

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

        GraphQLInstrumentator._enabled = True
        wrap_object(
            graphql,
            "execute",
            FunctionWrapper,
            args=(_wrap_execute(tracer, config, response_hook=response_hook),),
            kwargs={"enabled": self.enabled}
        )
        wrap_object(
            graphql,
            "parse",
            FunctionWrapper,
            args=(_wrap_parse(tracer, allow_values),),
            kwargs={"enabled": self.enabled}
        )
        wrap_object(
            graphql,
            "validate",
            FunctionWrapper,
            args=(_wrap_validate(tracer),),
            kwargs={"enabled": self.enabled}
        )
        if not is_v2:
            wrap_object(
                graphql,
                "execute_sync",
                FunctionWrapper,
                args=(_wrap_execute(tracer, config, response_hook=response_hook),),
                kwargs={"enabled": self.enabled}
            )

    def _uninstrument(self, **kwargs):
        GraphQLInstrumentator._enabled = False
        unwrap(graphql, "parse")
        unwrap(graphql, "execute")
        unwrap(graphql, "validate")
        if not is_v2:
            unwrap(graphql, "execute_sync")
