"""uniparser2: a declarative, deterministic, serializable text parsing engine.

The design notes are in ``docs/specs/`` (``0NN-*.md``; index and conventions in ``docs/README.md``).

Importing this package registers the built-in operators automatically (``uniparser2.ops``); the
core, ``uniparser2.core``, depends on no third-party library and performs no IO (invariant I1 of
design doc 01 §1.1).
"""

from __future__ import annotations

import logging

from . import ops as _ops  # noqa: F401  register built-in operators (explicit registry)
from .core import (
    CODES,
    CompiledField,
    CompiledStory,
    Diagnostic,
    Failed,
    JsonValue,
    Materializer,
    Missing,
    Ok,
    Opaque,
    Outcome,
    Ref,
    Scope,
    StoryRun,
    StoryStep,
    TypeConstructionError,
    TypeConstructor,
    UnknownTypeError,
    Up2Error,
    Value,
    compile_field,
    compile_stage,
    compile_story,
    dumps,
    eval_field,
    get_type,
    loads,
    pack,
    parse_ref,
    register_type,
    start,
    type_names,
    unregister_type,
)
from .core.udfs import get_udf, register_udf, udf_names, unregister_udf
from .host import load_entry_point_udfs

__version__ = "0.4.0"
"""The single source of the version: ``[tool.hatch.version]`` in ``pyproject.toml`` reads it."""

logger = logging.getLogger("uniparser2")
# Do not take over the host's logging configuration (essence §C library logging rules).
logger.addHandler(logging.NullHandler())

# Discover the user-defined functions the host declares through entry points (the IO lives in the
# host layer, so core stays IO-free).
_ENV_UDFS = load_entry_point_udfs()
"""The names registered from the ``entry_points`` group ``uniparser2.udfs`` during this import."""

__all__ = [
    "CODES",
    "CompiledField",
    "CompiledStory",
    "Diagnostic",
    "Failed",
    "JsonValue",
    "Materializer",
    "Missing",
    "Ok",
    "Opaque",
    "Outcome",
    "Ref",
    "Scope",
    "StoryRun",
    "StoryStep",
    "TypeConstructionError",
    "TypeConstructor",
    "UnknownTypeError",
    "Up2Error",
    "Value",
    "__version__",
    "compile_field",
    "compile_stage",
    "compile_story",
    "dumps",
    "eval_field",
    "get_type",
    "get_udf",
    "load_entry_point_udfs",
    "loads",
    "logger",
    "pack",
    "parse_ref",
    "register_type",
    "register_udf",
    "start",
    "type_names",
    "udf_names",
    "unregister_type",
    "unregister_udf",
]
