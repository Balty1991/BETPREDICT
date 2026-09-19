#!/usr/bin/env python3
"""pyramid_staking v8.1 — source in pyramid_staking.part* (readable UTF-8 slices)."""
from __future__ import annotations
from pathlib import Path
_HERE = Path(__file__).resolve().parent
_PARTS = sorted(_HERE.glob("pyramid_staking.part*"))
if not _PARTS:
    raise ImportError("missing pyramid_staking.part*")
exec(compile("".join(p.read_text(encoding="utf-8") for p in _PARTS), __file__, "exec"), globals())
