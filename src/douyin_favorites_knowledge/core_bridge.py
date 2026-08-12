"""Bound to the pinned douyin-knowledge-core wheel.

Public Skills may carry a hash-pinned core wheel. This module is the only import
boundary so Favorites never depends on a sibling Skill private package.
"""

from __future__ import annotations

REQUIRED_CORE_VERSION = "0.2.0"

try:
    import douyin_knowledge_core as _core
    from douyin_knowledge_core import (
        ProfileRegistry,
        atomic_write_json,
        atomic_write_text,
        canonical_json,
        file_sha256,
        profile_lock,
        sha256_bytes,
    )
except ImportError as exc:  # pragma: no cover - exercised in packaging smoke
    raise ImportError(
        "douyin-knowledge-core is required. Install the pinned wheel first:\n"
        "  python -m pip install "
        "./vendor/wheels/douyin_knowledge_core-0.2.0-py3-none-any.whl\n"
        "Then install this package."
    ) from exc

CORE_VERSION = getattr(_core, "__version__", "")
if CORE_VERSION != REQUIRED_CORE_VERSION:
    raise ImportError(
        f"douyin-knowledge-core {REQUIRED_CORE_VERSION} required, found {CORE_VERSION or 'unknown'}"
    )

__all__ = [
    "CORE_VERSION",
    "REQUIRED_CORE_VERSION",
    "ProfileRegistry",
    "atomic_write_json",
    "atomic_write_text",
    "canonical_json",
    "file_sha256",
    "profile_lock",
    "sha256_bytes",
]
