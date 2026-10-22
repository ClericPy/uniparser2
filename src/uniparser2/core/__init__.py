"""The core layer: no hard third-party dependency, no IO, no coroutines.

That is invariants I1/I2 of design doc 01 §1.1. The division of labor between submodules is in
01 §1.2. This module only **re-exports public names** and introduces no extra behavior.
"""

from __future__ import annotations

from .ast import CompiledField, CompiledStage, Lit, Param, Ref, Stage, dumps, loads
from .compile import compile_field, compile_field_map, compile_stage
from .conformance import ConformanceReport, check
from .errors import CODES, Diagnostic, Failed, Missing, Ok, Outcome, Up2Error, diag
from .evaluator import eval_field, resolve_params
from .export import ProductDifference, compare_products, pack, render_difference
from .limits import MAX_MATERIALIZE_BYTES, MAX_MATERIALIZE_ITEMS, MAX_STEPS_PER_FIELD
from .materialize import HTML, JSON, XML, Materialize, MaterializedArtifact, Materializer
from .refs import Scope, is_ref_text, parse_path_text, parse_ref
from .story import CompiledStory, StoryRun, StoryStep, compile_story, start
from .trace import (
    EFFECT_BATCH,
    EFFECT_CALL,
    EFFECT_REQUEST,
    PREVIEW_LIMIT,
    STATE_FAILED,
    STATE_MISSING,
    STATE_OK,
    Trace,
    TraceEvent,
    ValueView,
    value_view,
)
from .types import (
    BUILTIN_TYPES,
    TypeConstructionError,
    TypeConstructor,
    UnknownTypeError,
    get_type,
    register_type,
    type_names,
    unregister_type,
)
from .values import JsonValue, Opaque, Value, is_json_value, is_opaque, preview, type_name

__all__ = [
    "BUILTIN_TYPES",
    "CODES",
    "EFFECT_BATCH",
    "EFFECT_CALL",
    "EFFECT_REQUEST",
    "HTML",
    "JSON",
    "MAX_MATERIALIZE_BYTES",
    "MAX_MATERIALIZE_ITEMS",
    "MAX_STEPS_PER_FIELD",
    "MISSING",
    "PREVIEW_LIMIT",
    "STATE_FAILED",
    "STATE_MISSING",
    "STATE_OK",
    "XML",
    "CompiledField",
    "CompiledStage",
    "CompiledStory",
    "ConformanceReport",
    "Diagnostic",
    "Failed",
    "JsonValue",
    "Lit",
    "Materialize",
    "MaterializedArtifact",
    "Materializer",
    "Missing",
    "Ok",
    "Opaque",
    "Outcome",
    "Param",
    "ProductDifference",
    "Ref",
    "Scope",
    "Stage",
    "StoryRun",
    "StoryStep",
    "Trace",
    "TraceEvent",
    "TypeConstructionError",
    "TypeConstructor",
    "UnknownTypeError",
    "Up2Error",
    "Value",
    "ValueView",
    "check",
    "compare_products",
    "compile_field",
    "compile_field_map",
    "compile_stage",
    "compile_story",
    "diag",
    "dumps",
    "eval_field",
    "get_type",
    "is_json_value",
    "is_opaque",
    "is_ref_text",
    "loads",
    "pack",
    "parse_path_text",
    "parse_ref",
    "preview",
    "register_type",
    "render_difference",
    "resolve_params",
    "start",
    "type_name",
    "type_names",
    "unregister_type",
    "value_view",
]
