from __future__ import annotations

import importlib
from collections.abc import Callable


def load_adapter(spec: str) -> Callable:
    """Load an explicit `module:function` adapter."""
    if ":" not in spec:
        raise ValueError("adapter must use module:function format")
    module_name, function_name = spec.rsplit(":", 1)
    module = importlib.import_module(module_name)
    adapter = getattr(module, function_name, None)
    if not callable(adapter):
        raise ValueError(f"adapter is not callable: {spec}")
    return adapter
