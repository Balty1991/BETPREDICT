#!/usr/bin/env python3
"""BetPredict accumulator_engine v8.1 — clean source shipped as numbered parts.

Why parts: GitHub MCP push size limits. The `.partNN` files are plain UTF-8
slices of the full readable engine (not zlib). Concatenate in order to recover:

    cat src/accumulator_engine.part* > /tmp/accumulator_engine_full.py

At runtime this module loads those parts into its namespace (identical behavior).
"""
from __future__ import annotations
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PARTS = sorted(_HERE.glob("accumulator_engine.part*"))
if not _PARTS:
    raise ImportError("missing src/accumulator_engine.part* source slices")
exec(compile("".join(p.read_text(encoding="utf-8") for p in _PARTS), __file__, "exec"), globals())
