"""
Forgiving JSON extraction for small-model output.

A 2B model asked for "JSON only" still routinely returns one of:
  * ```json fenced blocks
  * a friendly sentence before the JSON ("Sure! Here are the locations:")
  * trailing commas
  * single-quoted keys
  * Python-style True/False/None
  * a bare object when an array was requested

None of these are model failures worth discarding an answer over.  Each repair
is recorded so the verification report can state the TRUE raw-compliance rate
separately from the post-repair usability rate.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Tuple[Optional[Any], List[str]]:
    """Return (parsed_object_or_None, list_of_repairs_applied)."""
    repairs: List[str] = []
    if not text or not text.strip():
        return None, ["empty_response"]

    # 1. strip markdown fences
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
        repairs.append("stripped_markdown_fence")

    # 2. exact parse first — a clean answer must not be marked as repaired
    try:
        return json.loads(text), repairs
    except json.JSONDecodeError:
        pass

    candidate = _slice_balanced(text)
    if candidate is None:
        return None, repairs + ["no_balanced_json_found"]
    if candidate != text.strip():
        repairs.append("trimmed_surrounding_prose")

    try:
        return json.loads(candidate), repairs
    except json.JSONDecodeError:
        pass

    fixed = candidate
    # 3. trailing commas
    new = re.sub(r",\s*([}\]])", r"\1", fixed)
    if new != fixed:
        fixed = new
        repairs.append("removed_trailing_comma")
    # 4. python literals
    for a, b in ((r"\bTrue\b", "true"), (r"\bFalse\b", "false"), (r"\bNone\b", "null")):
        new = re.sub(a, b, fixed)
        if new != fixed:
            fixed = new
            repairs.append("python_literal_to_json")
    # 5. smart quotes
    if any(c in fixed for c in "\u201c\u201d\u2018\u2019"):
        fixed = (fixed.replace("\u201c", '"').replace("\u201d", '"')
                      .replace("\u2018", "'").replace("\u2019", "'"))
        repairs.append("normalised_smart_quotes")
    try:
        return json.loads(fixed), repairs
    except json.JSONDecodeError:
        pass

    # 6. single-quoted keys/strings
    try:
        import ast
        val = ast.literal_eval(fixed)
        repairs.append("ast_literal_eval_fallback")
        return val, repairs
    except Exception:
        return None, repairs + ["unparseable"]


def _slice_balanced(text: str) -> Optional[str]:
    """Return the first balanced {...} or [...] span, ignoring braces in strings."""
    start = None
    opener = closer = ""
    for i, ch in enumerate(text):
        if ch in "[{":
            start = i
            opener, closer = ch, ("]" if ch == "[" else "}")
            break
    if start is None:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start:j + 1]
    return text[start:]  # truncated but may still be salvageable


def coerce_place_list(obj: Any) -> List[Dict[str, Any]]:
    """Accept the several shapes a model may return and normalise to a list."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for key in ("places", "locations", "landmarks", "results", "data", "markers",
                    "items", "points"):
            if isinstance(obj.get(key), list):
                return [x for x in obj[key] if isinstance(x, dict)]
        # single place object?
        if any(k in obj for k in ("lat", "latitude")):
            return [obj]
        # {"1": {...}, "2": {...}}
        vals = [v for v in obj.values() if isinstance(v, dict)]
        if vals:
            return vals
    return []


# Field aliases small models invent instead of following the schema.
_LAT_KEYS = ("lat", "latitude", "Lat", "Latitude", "纬度", "y")
_LON_KEYS = ("lon", "lng", "long", "longitude", "Lon", "Lng", "Longitude", "经度", "x")
_NAME_KEYS = ("name", "Name", "english_name", "name_en", "title")
_NAME_ZH_KEYS = ("name_zh", "nameZh", "chinese_name", "zh_name", "中文名", "名称")
_DESC_KEYS = ("description", "desc", "Description", "summary", "描述", "简介")
_CAT_KEYS = ("category", "type", "kind", "类别", "分类")


def _first(d: Dict[str, Any], keys) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def normalise_place(d: Dict[str, Any]) -> Dict[str, Any]:
    """Map a model-produced dict onto the canonical place schema."""
    return {
        "name": str(_first(d, _NAME_KEYS) or "").strip(),
        "name_zh": str(_first(d, _NAME_ZH_KEYS) or "").strip(),
        "lat": _num(_first(d, _LAT_KEYS)),
        "lon": _num(_first(d, _LON_KEYS)),
        "description": str(_first(d, _DESC_KEYS) or "").strip(),
        "category": str(_first(d, _CAT_KEYS) or "other").strip().lower(),
    }


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-+]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None
