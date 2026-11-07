"""Prices the OpenCode Go entries from LiteLLM's cost map at proxy start.

Go is a flat subscription, so nothing is billed per token; spend is still computed
from the cost map entry for the backend model a deployment dispatches to -
openai/<id> here, because Go is not a native provider - and that key never exists,
so every call bills 0 while the OpenRouter fallback hop shows a real number.

LiteLLM loads that map at import (fetched from upstream main, the bundled backup
when the fetch fails) and it carries an opencode_go/<id> row for each of these
models, so copy every row onto its openai/<id> dispatch key: the estimate then
follows the map instead of a table maintained here.

The copy keeps litellm_provider=openai on purpose. get_model_info only accepts a
cost map entry whose litellm_provider matches the provider the call dispatches as
(utils._check_provider_match), and the opencode_go rows declare that
non-dispatchable provider.
"""

import litellm
from litellm.integrations.custom_logger import CustomLogger

SOURCE_PREFIX = "opencode_go/"
TARGET_PREFIX = "openai/"


def mirror_pricing() -> int:
    """Register every opencode_go row under the openai key the proxy dispatches to."""
    rows = {
        TARGET_PREFIX + key[len(SOURCE_PREFIX) :]: {**row, "litellm_provider": "openai"}
        for key, row in litellm.model_cost.items()
        if key.startswith(SOURCE_PREFIX) and isinstance(row, dict)
    }
    if not rows:
        return 0
    litellm.register_model(rows, persist_across_reloads=True)
    return len(rows)


class PricingMirror(CustomLogger):
    """Boot hook; the callbacks list has to name an instance, not the class."""

    def __init__(self):
        super().__init__()
        registered = mirror_pricing()
        if registered == 0:
            # The bundled fallback map carries no opencode_go rows, so an offline
            # start lands here. Still serve inference, but say why spend reads 0.
            litellm.verbose_logger.warning(
                "no opencode_go/* rows in the model cost map; OpenCode Go spend stays 0"
            )


proxy_handler_instance = PricingMirror()
