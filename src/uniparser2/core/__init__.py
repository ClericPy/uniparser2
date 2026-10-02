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
from .export import pack
from .limits import MAX_STEPS_PER_FIELD
from .refs import Scope, is_ref_text, parse_path_text, parse_ref
from .story import CompiledStory, StoryRun, StoryStep, compile_story, start
from .values import MISSING, JsonValue, Opaque, Value, is_json_value, is_opaque, preview, type_name

__all__ = [
    "CODES",
    "MAX_STEPS_PER_FIELD",
    "MISSING",
    "CompiledField",
    "CompiledStage",
    "CompiledStory",
    "ConformanceReport",
    "Diagnostic",
    "Failed",
    "JsonValue",
    "Lit",
    "Missing",
    "Ok",
    "Opaque",
    "Outcome",
    "Param",
    "Ref",
    "Scope",
    "Stage",
    "StoryRun",
    "StoryStep",
    "Up2Error",
    "Value",
    "check",
    "compile_field",
    "compile_field_map",
    "compile_stage",
    "compile_story",
    "diag",
    "dumps",
    "eval_field",
    "is_json_value",
    "is_opaque",
    "is_ref_text",
    "loads",
    "pack",
    "parse_path_text",
    "parse_ref",
    "preview",
    "resolve_params",
    "start",
    "type_name",
]
